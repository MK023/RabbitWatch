import pika
import json
import yaml
import logging
import sys
import argparse
from pymongo import MongoClient, errors as mongo_errors
from logging.handlers import RotatingFileHandler
from typing import Any, Dict
import socket
import os
import threading
import time

# --- Config: caricamento e validazione --- #
def load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"[FATAL] Errore nel caricamento config '{path}': {e}")
        sys.exit(1)

def validate_config(config: dict) -> None:
    keys = ["mongodb", "rabbitmq", "logging"]
    for k in keys:
        if k not in config:
            logging.critical(f"[FATAL] Configurazione mancante: '{k}'")
            sys.exit(1)

# --- Logging: file + console, rotazione --- #
def setup_logger(conf: dict, to_console: bool = False):
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, conf.get("log_level", "INFO").upper(), logging.INFO))
    hostname = socket.gethostname()
    pid = os.getpid()
    formatter = logging.Formatter(
        f"%(asctime)s [%(levelname)s] [host:{hostname}] [pid:{pid}] %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    handler = RotatingFileHandler(
        conf.get("consumer_logfile", "metrics_consumer.log"),
        maxBytes=conf.get("log_max_bytes", 1048576),
        backupCount=conf.get("log_backup_count", 3)
    )
    handler.setFormatter(formatter)
    logger.handlers = [handler]
    if to_console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

# --- Mongo --- #
def mongo_connect(mongo_conf: dict):
    try:
        client = MongoClient(mongo_conf["uri"])
        db = client[mongo_conf["database"]]
        logging.info(f"[OK] Connessione a MongoDB riuscita: uri='{mongo_conf['uri']}', database='{mongo_conf['database']}'")
        return client, db
    except Exception as e:
        logging.critical(f"[FATAL] Errore connessione MongoDB: {e}, uri='{mongo_conf['uri']}'")
        sys.exit(1)

def save_to_mongo(db, collection_name: str, message: dict) -> bool:
    try:
        db[collection_name].insert_one(message)
        logging.info(f"[OK] Documento salvato su MongoDB: collection='{collection_name}', body={message}")
        return True
    except mongo_errors.PyMongoError as e:
        logging.error(f"[ERROR] Fallito salvataggio su MongoDB: collection='{collection_name}', errore={e}, body={message}")
        return False

# --- RabbitMQ --- #
def rabbit_connect(rabbit_conf: dict, host_override=None):
    host = host_override if host_override else rabbit_conf["host"]
    credentials = pika.PlainCredentials(rabbit_conf["username"], rabbit_conf["password"])
    parameters = pika.ConnectionParameters(
        host=host,
        port=rabbit_conf.get("port", 5672),
        virtual_host=rabbit_conf.get("vhost", "/"),
        credentials=credentials,
        heartbeat=60,
    )
    connection = None
    channel = None
    for attempt in range(1, 6):
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            logging.info(f"[OK] Connessione a RabbitMQ riuscita: host='{host}' (tentativo {attempt})")
            return connection, channel
        except Exception as e:
            logging.error(f"[RECONNECT] Errore connessione RabbitMQ: {e}, host='{host}', tentativo={attempt}")
            time.sleep(min(10 * attempt, 60))
    logging.critical(f"[FATAL] Impossibile connettere a RabbitMQ dopo 5 tentativi.")
    return None, None

# --- Queue polling thread (Best Practice: connessione dedicata) --- #
def poll_queues(rabbit_conf, queue_map, interval_sec=30, host_override=None):
    def poll():
        polling_conn, polling_ch = rabbit_connect(rabbit_conf, host_override)
        if not polling_conn or not polling_ch:
            logging.error("[POLL_ERROR] Impossibile avviare polling su RabbitMQ")
            return
        while True:
            for queue in queue_map.keys():
                try:
                    q = polling_ch.queue_declare(queue=queue, passive=True)
                    msg_count = q.method.message_count
                    logging.info(f"[POLL] queue='{queue}', messages_in_queue={msg_count}")
                except Exception as e:
                    logging.error(f"[POLL_ERROR] Errore polling queue='{queue}': {e}")
            time.sleep(interval_sec)
    t = threading.Thread(target=poll, daemon=True)
    t.start()

# --- Callback factory --- #
def make_callback(db, collection_name: str):
    def callback(ch, method, properties, body):
        logging.debug(f"[DEBUG] Ricevuto messaggio su queue='{collection_name}', delivery_tag={method.delivery_tag}")
        try:
            msg = json.loads(body)
            logging.info(f"[INFO] Parsing JSON riuscito su queue='{collection_name}', body={msg}")
        except Exception as e:
            logging.error(f"[ERROR] Errore nel parsing JSON: errore={e}, raw_body={body}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        ok = save_to_mongo(db, collection_name, msg)
        if ok:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logging.debug(f"[DEBUG] Ack inviato su queue='{collection_name}', delivery_tag={method.delivery_tag}")
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            logging.warning(f"[WARN] Nack inviato su queue='{collection_name}', delivery_tag={method.delivery_tag}")
    return callback

def setup_pidfile(pid_file_path):
    try:
        with open(pid_file_path, "w") as f:
            f.write(str(os.getpid()))
        logging.info(f"[INFO] PID scritto su file: {pid_file_path}")
    except Exception as e:
        logging.error(f"[WARN] Impossibile scrivere PID su file: {e}")

def cleanup(pid_file_path, connection, client):
    try:
        if connection:
            connection.close()
        if client:
            client.close()
        logging.info("[INFO] Connessioni chiuse.")
    except Exception:
        pass
    try:
        os.remove(pid_file_path)
        logging.info(f"[INFO] File PID rimosso: {pid_file_path}")
    except Exception as e:
        logging.warning(f"[WARN] Impossibile rimuovere file PID: {e}")

# --- Consumo RabbitMQ con auto-reconnect --- #
def rabbit_consume_with_reconnect(rabbit_conf, queue_map, db, polling_conf, host_override, pid_file):
    connection = None
    channel = None
    while True:
        connection, channel = rabbit_connect(rabbit_conf, host_override)
        if not connection or not channel:
            logging.error("[FATAL] RabbitMQ non raggiungibile, retry tra 60s...")
            time.sleep(60)
            continue

        # RIMOSSO: channel.add_on_close_callback(on_channel_closed)

        for queue in queue_map.keys():
            try:
                channel.queue_declare(queue=queue, durable=True)
                logging.info(f"[INFO] Queue dichiarata: '{queue}'")
            except Exception as e:
                logging.error(f"[ERROR] Errore dichiarazione queue '{queue}': {e}")

        if polling_conf.get("enabled", False):
            poll_queues(rabbit_conf, queue_map, interval_sec=polling_conf.get("interval_sec", 30), host_override=host_override)

        for queue, collection in queue_map.items():
            cb = make_callback(db, collection)
            channel.basic_consume(queue=queue, on_message_callback=cb, auto_ack=False)
            logging.info(f"[INFO] Callback attivata su queue: '{queue}'")

        logging.info(f"[READY] Consumer in ascolto su RabbitMQ: code={list(queue_map.keys())}")
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            logging.info("[STOP] Consumer interrotto manualmente (CTRL+C).")
            cleanup(pid_file, connection, db.client)
            sys.exit(0)
        except Exception as e:
            logging.error(f"[RECONNECT] Connessione persa o errore consumer: {e} -- retry tra 10s")
            try:
                if connection:
                    connection.close()
            except Exception:
                pass
            time.sleep(10)  # backoff breve su errore
        # Loop riparte per riconnettere e riprendere consumo!

# --- Main --- #
def main():
    parser = argparse.ArgumentParser(description="RabbitMQ → MongoDB metrics consumer (auto-reconnect, best practice pika)")
    parser.add_argument("-c", "--config", default="consumer_config.yaml", help="Percorso file YAML di configurazione")
    parser.add_argument("--console-log", action="store_true", help="Abilita log su console")
    parser.add_argument("--rabbit-host", default=None, help="Override IP RabbitMQ (tipicamente IP VPN)")
    args = parser.parse_args()

    config = load_config(args.config)
    validate_config(config)
    setup_logger(config["logging"], to_console=args.console_log)

    pid_file = "/home/ubuntu/consumer_nas_to_mongodb/consumer.pid"
    setup_pidfile(pid_file)

    client, db = mongo_connect(config["mongodb"])
    queue_map = {
        config["rabbitmq"]["queue_info"]: config["mongodb"]["collection_info"],
        config["rabbitmq"]["queue_warning"]: config["mongodb"]["collection_warning"]
    }
    polling_conf = config.get("polling", {})
    try:
        rabbit_consume_with_reconnect(config["rabbitmq"], queue_map, db, polling_conf, args.rabbit_host, pid_file)
    finally:
        cleanup(pid_file, None, client)

if __name__ == "__main__":
    main()
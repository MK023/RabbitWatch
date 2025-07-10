import pika
import json
import yaml
import logging
from logging.handlers import RotatingFileHandler
from pymongo import MongoClient, errors as mongo_errors
import sys
import argparse
from typing import Any, Dict

# ==========================
# Funzione per caricare la configurazione YAML
# ==========================
def load_config(path: str) -> Dict[str, Any]:
    """
    Carica il file YAML di configurazione.
    In caso di problemi, logga l'errore e termina il programma.
    """
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"Errore caricamento config '{path}': {e}")
        sys.exit(1)

# ==========================
# Setup logging (file + console opzionale)
# ==========================
def setup_logger(logfile: str, max_bytes: int, backup_count: int, log_to_console: bool = False) -> None:
    """
    Imposta il logging:
    - Scrive su file a rotazione (rotating log)
    - Opzionalmente logga anche su console
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler = RotatingFileHandler(logfile, maxBytes=max_bytes, backupCount=backup_count)
    handler.setFormatter(formatter)
    logger.handlers = []
    logger.addHandler(handler)
    if log_to_console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

# ==========================
# Funzione per il salvataggio su MongoDB
# ==========================
def save_to_mongo(db, collection_name: str, message: dict) -> bool:
    """
    Salva il messaggio nella collezione MongoDB indicata.
    Ritorna True se il salvataggio è andato a buon fine, False altrimenti.
    """
    try:
        db[collection_name].insert_one(message)
        logging.info(f"Salvato su MongoDB: {collection_name}")
        return True
    except mongo_errors.PyMongoError as e:
        logging.error(f"Errore MongoDB ({collection_name}): {e} - Body: {message}")
        return False

# ==========================
# Callback dinamiche per ogni coda RabbitMQ
# ==========================
def get_callbacks(db, mongo_conf: dict, queue_map: dict):
    """
    Genera dinamicamente le callback da assegnare alle code RabbitMQ.
    Ogni callback esegue:
    - Parsing del messaggio JSON
    - Salvataggio su MongoDB
    - Gestione ack/nack in base all'esito
    """
    def make_callback(collection_name: str):
        def callback(ch, method, properties, body):
            try:
                msg = json.loads(body)  # parsing del messaggio
            except Exception as e:
                logging.error(f"Errore parsing JSON: {e} - Body: {body}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return
            ok = save_to_mongo(db, collection_name, msg)
            if ok:
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return callback
    return {queue: make_callback(col) for queue, col in queue_map.items()}

# ==========================
# Validazione della configurazione minima
# ==========================
def validate_config(config: dict) -> None:
    """
    Verifica che tutte le chiavi fondamentali siano presenti nel file di configurazione.
    """
    keys = ["mongodb", "rabbitmq", "logging"]
    for k in keys:
        if k not in config:
            logging.critical(f"Chiave mancante nella configurazione: {k}")
            sys.exit(1)

# ==========================
# Main: setup, connessioni, loop consumer
# ==========================
def main():
    # Parser argomenti da linea di comando
    parser = argparse.ArgumentParser(description="RabbitMQ → MongoDB consumer")
    parser.add_argument("-c", "--config", default="config_all.yaml", help="Percorso file di configurazione YAML")
    parser.add_argument("--console-log", action="store_true", help="Attiva log anche su console")
    args = parser.parse_args()

    # Carica e valida configurazione
    config = load_config(args.config)
    validate_config(config)
    logconf = config.get("logging", {})
    setup_logger(
        logconf.get("consumer_logfile", "metrics_consumer.log"),
        logconf.get("log_max_bytes", 1048576),
        logconf.get("log_backup_count", 3),
        log_to_console=args.console_log
    )
    mongo_conf = config["mongodb"]
    rabbit_conf = config["rabbitmq"]

    # Connessione a MongoDB
    try:
        client = MongoClient(mongo_conf["uri"])
        db = client[mongo_conf["database"]]
    except Exception as e:
        logging.critical(f"Errore connessione MongoDB: {e}")
        sys.exit(1)

    # Connessione a RabbitMQ
    credentials = pika.PlainCredentials(rabbit_conf["username"], rabbit_conf["password"])
    parameters = pika.ConnectionParameters(
        host=rabbit_conf["host"],
        port=rabbit_conf.get("port", 5672),
        virtual_host=rabbit_conf.get("vhost", "/"),
        credentials=credentials,
        heartbeat=60
    )
    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
    except Exception as e:
        logging.critical(f"Errore connessione RabbitMQ: {e}")
        sys.exit(1)

    # Mapping code Rabbit → collezioni Mongo (espandibile)
    queue_map = {
        rabbit_conf["queue_info"]: mongo_conf["collection_info"],
        rabbit_conf["queue_warning"]: mongo_conf["collection_warning"]
    }
    # Dichiara tutte le code (idempotente: se esistono, non fa nulla)
    for queue in queue_map.keys():
        channel.queue_declare(queue=queue, durable=True)

    # Callback dinamiche per ogni coda
    callbacks = get_callbacks(db, mongo_conf, queue_map)
    for queue, cb in callbacks.items():
        channel.basic_consume(queue=queue, on_message_callback=cb, auto_ack=False)

    logging.info(f"In ascolto su RabbitMQ ({', '.join(queue_map)})...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logging.info("Consumer interrotto manualmente.")
    except Exception as e:
        logging.critical(f"Errore fatale consumer: {e}")
    finally:
        # Chiusura connessioni in uscita
        try:
            connection.close()
            client.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
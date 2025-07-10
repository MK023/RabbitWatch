import yaml
import time
import logging
from logging.handlers import RotatingFileHandler
import requests
import pika
import json
import re
import sys
import argparse
from typing import Dict, Any, List, Union, Optional

def load_config(path: str) -> Dict[str, Any]:
    """Carica la configurazione YAML dal percorso fornito, esce se fallisce."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"Errore caricamento config '{path}': {e}")
        sys.exit(1)

def validate_config(config: dict) -> None:
    """Verifica che tutte le chiavi fondamentali siano presenti nella configurazione."""
    required = [
        "rabbitmq", "metrics", "node_exporter_url", "retry"
    ]
    for key in required:
        if key not in config:
            logging.critical(f"Chiave mancante nella configurazione: {key}")
            sys.exit(1)
    for queue in ["queue_info", "queue_warning"]:
        if queue not in config["rabbitmq"]:
            logging.critical(f"Chiave mancante in rabbitmq: {queue}")
            sys.exit(1)
    for rk in ["attempts", "delay_seconds"]:
        if rk not in config["retry"]:
            logging.critical(f"Chiave mancante in retry: {rk}")
            sys.exit(1)

def setup_logger(logfile: str, max_bytes: int, backup_count: int, log_to_console: bool = False) -> None:
    """Configura il logger rotativo e opzionalmente la console."""
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

def match_metric(line: str, patterns: List[str]) -> bool:
    """True se la linea corrisponde ad almeno uno dei pattern/regex forniti."""
    for pattern in patterns:
        try:
            if any(x in pattern for x in "^$.*+?[](){}|"):
                if re.match(pattern, line):
                    return True
            else:
                if line.startswith(pattern):
                    return True
        except re.error:
            if line.startswith(pattern):
                return True
    return False

def get_metrics(node_exporter_url: str, metrics: Union[list, str], attempts: int, delay: int) -> Dict[str, Any]:
    """
    Recupera e filtra le metriche da Node Exporter.
    Supporta sia 'all' (tutte le metriche), sia una lista di nomi/regEx.
    """
    for attempt in range(1, attempts+1):
        try:
            resp = requests.get(node_exporter_url, timeout=5)
            resp.raise_for_status()
            data = resp.text
            result: Dict[str, Any] = {}

            # Prendi tutte le righe valide (no commenti o vuote)
            all_lines = [l for l in data.splitlines() if l and not l.startswith("#")]

            # Modalità 'all'
            if metrics == "all":
                for line in all_lines:
                    parts = line.split()
                    if len(parts) == 2:
                        key, value = parts
                        try:
                            result[key] = float(value)
                        except Exception:
                            continue
                return result

            # Modalità lista
            for metric in metrics:
                lines = [l for l in all_lines if match_metric(l, [metric])]
                if not lines:
                    logging.warning(f"Metrica '{metric}' non trovata in Node Exporter")
                    continue

                if re.match(r"^node_cpu_seconds_total", metric):
                    try:
                        idle = sum(float(re.findall(r"\s(\d+\.\d+)$", l)[0]) for l in lines if 'mode="idle"' in l)
                        total = sum(float(re.findall(r"\s(\d+\.\d+)$", l)[0]) for l in lines)
                        cpu_usage = 100 * (1 - idle/total) if total > 0 else 0
                        result["cpu_usage_percent"] = round(cpu_usage, 2)
                    except Exception as e:
                        logging.warning(f"Parsing CPU fallito: {e}")

                elif metric in ["node_memory_MemAvailable_bytes", "node_memory_MemFree_bytes"]:
                    field = "mem_available" if "Available" in metric else "mem_free"
                    try:
                        value = float(lines[0].split()[-1])
                        result[field] = value
                    except Exception:
                        logging.warning(f"Parsing fallito per {metric}")

                elif metric in ["node_filesystem_avail_bytes", "node_filesystem_size_bytes"]:
                    root = [l for l in lines if 'mountpoint="/"' in l]
                    if root:
                        key = "disk_avail" if "avail" in metric else "disk_size"
                        try:
                            result[key] = float(root[0].split()[-1])
                        except Exception:
                            logging.warning(f"Parsing fallito per {metric}")

            # Percentuali RAM/disco
            mem_total_line = next((l for l in all_lines if l.startswith("node_memory_MemTotal_bytes")), None)
            if "mem_available" in result and mem_total_line:
                try:
                    mem_total = float(mem_total_line.split()[-1])
                    used = 100 * (1 - result["mem_available"] / mem_total)
                    result["memory_usage_percent"] = round(used, 2)
                except Exception:
                    pass
            elif "mem_free" in result and mem_total_line:
                try:
                    mem_total = float(mem_total_line.split()[-1])
                    used = 100 * (1 - result["mem_free"] / mem_total)
                    result["memory_usage_percent"] = round(used, 2)
                except Exception:
                    pass
            if "disk_avail" in result and "disk_size" in result:
                try:
                    free = 100 * (result["disk_avail"] / result["disk_size"])
                    result["disk_free_percent"] = round(free, 2)
                except Exception:
                    pass
            return result
        except Exception as e:
            logging.error(f"Errore recupero metriche Node Exporter (tentativo {attempt}): {e}")
            time.sleep(delay)
    logging.error("Impossibile recuperare metriche da Node Exporter dopo vari tentativi")
    return {}

def send_to_rabbitmq(rabbit_conf: dict, queue: str, message: dict, attempts: int, delay: int, log_level=logging.INFO) -> bool:
    """
    Invia un messaggio a RabbitMQ nella coda specificata.
    Riprova in caso di errore.
    """
    for attempt in range(1, attempts+1):
        try:
            credentials = pika.PlainCredentials(rabbit_conf["username"], rabbit_conf["password"])
            parameters = pika.ConnectionParameters(
                host=rabbit_conf["host"],
                port=rabbit_conf.get("port", 5672),
                virtual_host=rabbit_conf.get("vhost", "/"),
                credentials=credentials,
                heartbeat=30
            )
            with pika.BlockingConnection(parameters) as connection:
                channel = connection.channel()
                channel.queue_declare(queue=queue, durable=True)
                channel.basic_publish(
                    exchange='',
                    routing_key=queue,
                    body=json.dumps(message)
                )
            logging.log(log_level, f"Messaggio inviato a RabbitMQ su '{queue}': {message}")
            return True
        except Exception as e:
            logging.error(f"Errore invio a RabbitMQ '{queue}' (tentativo {attempt}): {e}")
            time.sleep(delay)
    logging.error(f"Impossibile inviare messaggio a RabbitMQ '{queue}' dopo vari tentativi")
    return False

def check_anomalies(metrics: dict, thresholds: dict) -> Dict[str, Any]:
    """
    Controlla quali metriche superano le soglie di allarme.
    Per 'free' (RAM/disco): allarme se < soglia. Per le altre: allarme se > soglia.
    """
    anomalies = {}
    for key, threshold in thresholds.items():
        value = metrics.get(key)
        if value is not None:
            if "free" in key:
                if value < threshold:
                    anomalies[key] = value
            else:
                if value > threshold:
                    anomalies[key] = value
    return anomalies

def metrics_changed(current: dict, previous: Optional[dict]) -> bool:
    """True se almeno una metrica è cambiata rispetto alla raccolta precedente."""
    if previous is None:
        return True
    return any(current.get(k) != previous.get(k) for k in current)

def main():
    parser = argparse.ArgumentParser(description="Producer metrics RabbitMQ")
    parser.add_argument("-c", "--config", default="config_all.yaml", help="Percorso file configurazione YAML")
    parser.add_argument("--console-log", action="store_true", help="Attiva log anche su console")
    args = parser.parse_args()

    config = load_config(args.config)
    validate_config(config)
    logconf = config.get("logging", {})
    setup_logger(
        logconf.get("producer_logfile", "metrics_producer.log"),
        logconf.get("log_max_bytes", 1048576),
        logconf.get("log_backup_count", 3),
        log_to_console=args.console_log
    )

    prev_metrics: Optional[dict] = None
    poll_interval = config.get("poll_interval_seconds") or config.get("producer", {}).get("push_interval_seconds", 60)
    while True:
        metrics = get_metrics(
            config["node_exporter_url"],
            config["metrics"],
            config["retry"]["attempts"],
            config["retry"]["delay_seconds"]
        )
        if not metrics:
            logging.warning("Nessuna metrica raccolta, salta invio.")
            time.sleep(poll_interval)
            continue

        if metrics_changed(metrics, prev_metrics):
            send_to_rabbitmq(
                config["rabbitmq"],
                config["rabbitmq"]["queue_info"],
                {
                    "type": "metrics",
                    "payload": metrics
                },
                config["retry"]["attempts"],
                config["retry"]["delay_seconds"],
                log_level=logging.INFO
            )
            prev_metrics = metrics.copy()
        anomalies = check_anomalies(metrics, config.get("anomaly_thresholds", {}))
        if anomalies:
            send_to_rabbitmq(
                config["rabbitmq"],
                config["rabbitmq"]["queue_warning"],
                {
                    "type": "alert",
                    "payload": anomalies
                },
                config["retry"]["attempts"],
                config["retry"]["delay_seconds"],
                log_level=logging.WARNING
            )
        time.sleep(poll_interval)

if __name__ == "__main__":
    main()
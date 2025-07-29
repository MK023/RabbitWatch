# ===============================
# Producer NAS Monitoring - Migliorie best practice e robustezza
# ===============================

import yaml
import time
import logging
import requests
import pika
import json
import sys
import argparse
import re
import uuid
import signal
import threading
import csv
from typing import Dict, Any, Optional, Tuple, List

# --- Configurazione e logging ---

def load_config(path: str) -> Dict[str, Any]:
    """Carica la configurazione YAML."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.critical(f"Errore caricamento config '{path}': {e}", exc_info=True)
        sys.exit(1)

def setup_logger(logfile: Optional[str] = None):
    """Setup logging: su file se specificato, altrimenti su console."""
    handlers = [logging.StreamHandler()]
    if logfile:
        handlers.append(logging.FileHandler(logfile))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers
    )

# --- Parsing metriche ---

def parse_labels(labels_str: str) -> Dict[str, str]:
    """Parsa labels Prometheus (gestisce virgole/uguali nei valori)."""
    if not labels_str:
        return {}
    # Usa csv reader per parsing robusto di label="value"
    reader = csv.reader([labels_str], delimiter=',', quotechar='"')
    labels = {}
    for parts in reader:
        for part in parts:
            if '=' in part:
                k, v = part.split('=', 1)
                labels[k.strip()] = v.strip().strip('"')
    return labels

def parse_metric_line(line: str) -> Optional[Tuple[str, Dict[str, str], float]]:
    """Parsa una linea di metrica Prometheus in: nome, labels, valore."""
    metric_re = re.compile(
        r'^([a-zA-Z0-9_:]+)(\{([^}]*)\})?\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)$'
    )
    match = metric_re.match(line.strip())
    if not match:
        return None
    name = match.group(1)
    labels = parse_labels(match.group(3))
    value = float(match.group(4))
    return (name, labels, value)

def get_all_metrics(node_exporter_url: str, extra_metrics: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Scarica tutte le metriche da Node Exporter, restituisce dict."""
    result: Dict[str, float] = {}
    try:
        resp = requests.get(node_exporter_url, timeout=5)
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if line and not line.startswith("#"):
                parsed = parse_metric_line(line)
                if parsed is None:
                    continue
                name, labels, value = parsed
                if labels:
                    label_str = ",".join([f'{k}="{v}"' for k, v in sorted(labels.items())])
                    full_key = f'{name}{{{label_str}}}'
                    result[full_key] = value
                # Aggiungi chiave semplice solo se non già presente
                if name not in result:
                    result[name] = value
        # Eventuali metriche aggiuntive custom
        if extra_metrics:
            result.update(extra_metrics)
    except Exception as e:
        logging.error(f"Errore recupero metriche Node Exporter: {e}", exc_info=True)
    return result

# --- Batching e gestione payload ---

FRAME_MAX = 131072  # Limite di RabbitMQ (128KB), default

def chunk_dict(metrics: Dict[str, float], max_bytes: int = FRAME_MAX) -> List[Dict[str, float]]:
    """
    Suddivide un dict di metriche in batch con payload JSON < max_bytes.
    Restituisce lista di batch.
    """
    items = list(metrics.items())
    batches = []
    batch = {}
    for k, v in items:
        batch[k] = v
        payload = json.dumps(batch, separators=(',', ':')).encode('utf-8')
        if len(payload) > max_bytes:
            batch.pop(k)
            if batch:
                batches.append(batch.copy())
            batch = {k: v}
    if batch:
        payload = json.dumps(batch, separators=(',', ':')).encode('utf-8')
        if len(payload) <= max_bytes:
            batches.append(batch.copy())
        else:
            logging.warning(f"Batch singolo troppo grande, scartato: chiave {list(batch.keys())[:1]}")
    return batches

def generate_batch_id() -> str:
    """Genera batch_id univoco per ogni batch."""
    return str(uuid.uuid4())

def log_batch_discarded(batch_id: str, reason: str, batch: dict):
    """Logga batch scartato su file o console."""
    logging.warning(
        f"BATCH SCARTATO: batch_id={batch_id}, motivo={reason}, size={len(json.dumps(batch))}"
    )

# --- Invio RabbitMQ ottimizzato (connessione persistente con retry) ---

class RabbitMQSender:
    def __init__(self, rabbit_conf: dict, attempts: int = 3, delay_seconds: int = 5):
        self.rabbit_conf = rabbit_conf
        self.attempts = attempts
        self.delay_seconds = delay_seconds
        self.connection = None
        self.channel = None

    def connect(self):
        heartbeat = self.rabbit_conf.get("heartbeat", 60)
        for attempt in range(1, self.attempts + 1):
            try:
                credentials = pika.PlainCredentials(self.rabbit_conf["username"], self.rabbit_conf["password"])
                parameters = pika.ConnectionParameters(
                    host=self.rabbit_conf["host"],
                    port=self.rabbit_conf.get("port", 5672),
                    virtual_host=self.rabbit_conf.get("vhost", "/"),
                    credentials=credentials,
                    heartbeat=heartbeat
                )
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                # Dichiara le code all'avvio
                self.channel.queue_declare(queue=self.rabbit_conf["queue_info"], durable=True)
                self.channel.queue_declare(queue=self.rabbit_conf["queue_warning"], durable=True)
                logging.info("Connessione RabbitMQ stabilita.")
                return True
            except Exception as e:
                logging.error(f"Errore connessione RabbitMQ: {e}, tentativo={attempt}", exc_info=True)
                time.sleep(self.delay_seconds)
        logging.critical("Fallita la connessione RabbitMQ dopo tutti i tentativi.")
        return False

    def send(self, queue: str, message: dict, batch_id: str, extra_headers: Optional[dict] = None):
        if not self.channel or self.connection.is_closed:
            logging.warning("Connessione RabbitMQ persa, provo a riconnettere...")
            if not self.connect():
                logging.error(f"Impossibile riconnettere per invio batch_id={batch_id}")
                return False
        try:
            headers = {"batch_id": batch_id}
            if extra_headers:
                headers.update(extra_headers)
            props = pika.BasicProperties(headers=headers)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=json.dumps(message, separators=(',', ':')),
                properties=props
            )
            logging.info(f"Batch inviato: batch_id={batch_id}, queue={queue}, size={len(json.dumps(message))}")
            return True
        except Exception as e:
            logging.error(f"Errore invio a RabbitMQ '{queue}': {e}, batch_id={batch_id}", exc_info=True)
            # Prova a riconnettere e ritenta una volta
            self.connect()
            try:
                self.channel.basic_publish(
                    exchange='',
                    routing_key=queue,
                    body=json.dumps(message, separators=(',', ':')),
                    properties=props
                )
                logging.info(f"Batch inviato dopo riconnessione: batch_id={batch_id}, queue={queue}")
                return True
            except Exception as e2:
                logging.error(f"Fallito invio dopo riconnessione: {e2}, batch_id={batch_id}", exc_info=True)
                return False

    def close(self):
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
                logging.info("Connessione RabbitMQ chiusa.")
        except Exception as e:
            logging.error(f"Errore chiusura connessione RabbitMQ: {e}", exc_info=True)

# --- Gestione anomalie e soglie ---

def parse_threshold_key(th_key: str) -> Tuple[str, Dict[str, str]]:
    """Parsa una chiave soglia: es 'metric{label="x"}'."""
    m = re.match(r'^([^{]+)(\{(.*)\})?$', th_key.strip())
    if not m:
        return (th_key, {})
    name = m.group(1)
    labels = parse_labels(m.group(3))
    return (name, labels)

def match_metric(metrics: Dict[str, float], name: str, labels: Dict[str, str]) -> Optional[Tuple[str, float]]:
    """Trova la metrica corrispondente a nome+labels."""
    if labels:
        label_str = ",".join([f'{k}="{v}"' for k, v in sorted(labels.items())])
        key = f'{name}{{{label_str}}}'
        if key in metrics:
            return (key, metrics[key])
    if name in metrics:
        return (name, metrics[name])
    return None

def check_anomalies(metrics: dict, thresholds: dict) -> Dict[str, Any]:
    """Verifica anomalie sulle metriche rispetto alle soglie."""
    anomalies = {}
    for th_key, threshold in thresholds.items():
        name, labels = parse_threshold_key(th_key)
        matched = match_metric(metrics, name, labels)
        if not matched:
            continue
        key, value = matched
        # Soglie invertite per alcune metriche
        if ("disk_free_percent" in key or
            "entropy_available_bits" in key or
            "filefd_maximum" in key):
            if value < threshold:
                anomalies[key] = value
        else:
            if value > threshold:
                anomalies[key] = value
        if ("network_up" in key or "up" in key) and value == threshold:
            anomalies[key] = value
    return anomalies

# --- Main loop ottimizzato, shutdown sicuro ---

class GracefulKiller:
    """Gestisce SIGINT/SIGTERM per uno shutdown pulito."""
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True
        logging.info("Ricevuto segnale di terminazione, esco...")

def run_metrics_producer(config: dict, config_path: str):
    poll_interval = config.get("poll_interval_seconds", 180)
    node_exporter_url = config["node_exporter_url"]
    extra_metrics = config.get("extra_metrics", None)
    logging.info(f"User config file: {config_path}")
    logging.info(f"Node Exporter URL: {node_exporter_url}")
    logging.info(f"RabbitMQ Host: {config['rabbitmq']['host']} Port: {config['rabbitmq'].get('port',5672)}")

    attempts = config.get("retry", {}).get("attempts", 3)
    delay_seconds = config.get("retry", {}).get("delay_seconds", 5)

    sender = RabbitMQSender(config["rabbitmq"], attempts=attempts, delay_seconds=delay_seconds)
    if not sender.connect():
        logging.critical("Impossibile stabilire connessione RabbitMQ: esco.")
        sys.exit(2)

    killer = GracefulKiller()
    try:
        while not killer.kill_now:
            metrics = get_all_metrics(node_exporter_url, extra_metrics=extra_metrics)
            if not metrics:
                logging.warning("Nessuna metrica raccolta, salta invio.")
            else:
                # --- Invio metriche: batching ---
                batches = chunk_dict(metrics, FRAME_MAX)
                for batch in batches:
                    batch_id = generate_batch_id()
                    payload = {
                        "type": "metrics",
                        "payload": batch
                    }
                    size_bytes = len(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
                    if size_bytes <= FRAME_MAX:
                        ok = sender.send(
                            config["rabbitmq"]["queue_info"],
                            payload,
                            batch_id,
                            extra_headers={
                                "timestamp": int(time.time()),
                                "source": "producer_nas"
                            }
                        )
                        if not ok:
                            logging.error(f"Invio batch non riuscito: batch_id={batch_id}")
                    else:
                        log_batch_discarded(batch_id, "batch troppo grande (metrics)", batch)

                # --- Invio anomalie (alert): batching ---
                anomalies = check_anomalies(metrics, config.get("anomaly_thresholds", {}))
                if anomalies:
                    anomaly_batches = chunk_dict(anomalies, FRAME_MAX)
                    for anomaly_batch in anomaly_batches:
                        batch_id = generate_batch_id()
                        payload = {
                            "type": "alert",
                            "payload": anomaly_batch
                        }
                        size_bytes = len(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
                        if size_bytes <= FRAME_MAX:
                            ok = sender.send(
                                config["rabbitmq"]["queue_warning"],
                                payload,
                                batch_id,
                                extra_headers={
                                    "timestamp": int(time.time()),
                                    "source": "producer_nas"
                                }
                            )
                            if not ok:
                                logging.error(f"Invio alert non riuscito: batch_id={batch_id}")
                        else:
                            log_batch_discarded(batch_id, "batch troppo grande (anomalies)", anomaly_batch)

            for _ in range(poll_interval):
                if killer.kill_now:
                    break
                time.sleep(1)
    finally:
        sender.close()

# --- Avvio main ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Producer metrics RabbitMQ NAS ottimizzato (label-aware, batching, header, logging, retry, connessione persistente, shutdown sicuro)")
    parser.add_argument("-c", "--config", default="config_producer.yaml", help="Percorso file configurazione YAML")
    parser.add_argument("--logfile", default=None, help="File di log (opzionale)")
    args = parser.parse_args()

    setup_logger(args.logfile)
    config = load_config(args.config)
    run_metrics_producer(config, args.config)
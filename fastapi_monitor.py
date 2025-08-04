#=====IMPORT NECESSARI=====#
import os
import sys
import signal
import logging
import json
import requests
import yaml
from fastapi import FastAPI
from pymongo import MongoClient
from requests.auth import HTTPBasicAuth

#=====COSTANTE FILE DI CONFIGURAZIONE=====#
SETTINGS_FILE = "monitor_settings.yaml"

#=====FUNZIONE PER IL LOGGING=====#
def log_event(level, message, **kwargs):
    extra = kwargs if kwargs else None
    if level == "info":
        logger.info(message, extra=extra)
    elif level == "warning":
        logger.warning(message, extra=extra)
    elif level == "error":
        logger.error(message, extra=extra)
    elif level == "debug":
        logger.debug(message, extra=extra)
    else:
        logger.info(message, extra=extra)

#=====FUNZIONE PER CARICARE LA CONFIGURAZIONE=====#
def load_config(filename):
    """
    Carica la configurazione YAML dal file specificato.
    """
    try:
        with open(filename, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        log_event("error", f"Errore nel caricamento della configurazione: {e}")
        return {}

#=====CARICAMENTO DELLA CONFIGURAZIONE=====#
CONFIG = load_config(SETTINGS_FILE)

#=====CREAZIONE DELL'OGGETTO FASTAPI=====#
app = FastAPI()

#=====DEFINIZIONE DEL PATH DEL FILE PID=====#
PID_FILE = "/home/ubuntu/monitoring/pid.txt"

#=====SETUP LOGGING AVANZATO (FORMATO JSON PER FILEBEAT)=====#
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.args and isinstance(record.args, dict):
            log_record.update(record.args)
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

logger = logging.getLogger("fastapi_monitor")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
# Se vuoi loggare anche su file, decommenta le 2 righe sotto:
# file_handler = logging.FileHandler("/home/ubuntu/monitoring/monitor.log")
# file_handler.setFormatter(JsonFormatter()); logger.addHandler(file_handler)

#=====FUNZIONE PER SCRIVERE IL PID DEL PROCESSO IN UN FILE=====#
def write_pid_file(pid_file=PID_FILE):
    """
    Scrive il PID del processo corrente in un file.
    """
    pid = os.getpid()
    with open(pid_file, "w") as f:
        f.write(str(pid))
    log_event("info", "PID file scritto", pid=pid, path=pid_file)

#=====FUNZIONE PER TERMINARE IL PROCESSO USANDO IL PID NEL FILE=====#
def terminate_process_by_pidfile(pid_file=PID_FILE):
    """
    Termina il processo il cui PID è scritto nel pid_file con SIGKILL -9.
    Utile per killare il processo da riga di comando.
    """
    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGKILL)
        log_event("info", "Processo terminato con SIGKILL -9", pid=pid)
    except Exception as e:
        log_event("error", "Errore terminazione processo", error=str(e), pid_file=pid_file)

#=====FUNZIONE CHECK HTTP GENERICA=====#
def check_http(url, auth=None, timeout=3):
    """
    Effettua una richiesta HTTP GET e solleva eccezione se la risposta non è 2xx.
    """
    resp = requests.get(url, auth=auth, timeout=timeout)
    resp.raise_for_status()
    return True   

#=====FUNZIONE CHECK MONGODB=====#
def check_mongodb(uri, timeout=3):
    """
    Verifica la raggiungibilità di MongoDB tramite il driver pymongo.
    """
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout*1000)
        client.server_info()
        return True
    except Exception:
        return False

#=====CHECK RABBITMQ (API HTTP CON AUTENTICAZIONE BASE)=====#
def verifica_rabbitmq(status):
    """
    Controlla lo stato di RabbitMQ tramite API HTTP.
    """
    try:
        check_http(
            CONFIG["rabbitmq_api"],
            auth=HTTPBasicAuth(CONFIG["rabbitmq_user"], CONFIG["rabbitmq_pass"])
        )
        status["rabbitmq"] = "ok"
    except Exception as e:
        status["rabbitmq"] = "error"
        status["rabbitmq_detail"] = str(e)

#=====CHECK PROMETHEUS=====#
def verifica_prometheus(status):
    """
    Controlla lo stato di Prometheus.
    """
    try:
        check_http(CONFIG["prometheus"])
        status["prometheus"] = "ok"
    except Exception as e:
        status["prometheus"] = "error"
        status["prometheus_detail"] = str(e)

#=====CHECK GRAFANA=====#
def verifica_grafana(status):
    """
    Controlla lo stato di Grafana.
    """
    try:
        check_http(CONFIG["grafana"])
        status["grafana"] = "ok"
    except Exception as e:
        status["grafana"] = "error"
        status["grafana_detail"] = str(e)

#=====CHECK PORTAINER=====#
def verifica_portainer(status):
    """
    Controlla lo stato di Portainer.
    """
    try:
        check_http(CONFIG["portainer"])
        status["portainer"] = "ok"
    except Exception as e:
        status["portainer"] = "error"
        status["portainer_detail"] = str(e)

#=====ENDPOINT FASTAPI: HOME=====#
@app.get("/")
def home():
    """
    Endpoint base.
    """
    return {"message": "Home RabbitWatch"}

#=====ENDPOINT FASTAPI: HEALTHCHECK=====#
@app.get("/health")
def healthcheck():
    """
    Effettua i check di stato di tutti i servizi monitorati.
    """
    log_event("info", "Healthcheck richiesto.")
    status = {}
    verifica_rabbitmq(status)
    verifica_prometheus(status)
    verifica_grafana(status)
    verifica_portainer(status)
    return status

#=====BLOCCO PRINCIPALE: AVVIO O KILL=====#
if __name__ == "__main__":
    #=====GESTIONE DA TERMINALE: KILL SE SPECIFICATO=====#
    if len(sys.argv) > 1 and sys.argv[1] == "kill":
        terminate_process_by_pidfile()
        sys.exit(0)
    #=====AVVIO NORMALE DEL MONITOR=====#
    write_pid_file(PID_FILE)
    log_event("info", "Monitor avviato.", mode="main")
    #=====AVVIO DEL SERVER UVICORN (SOLO SE L'APPLICAZIONE È LANCIATA DIRETTAMENTE)=====#
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)
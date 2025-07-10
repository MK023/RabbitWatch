"""
Monitoraggio servizi con FastAPI + thread automatico:
- Espone endpoint API REST per controllo e stato servizi (/monitor)
- Esegue i check in automatico ogni N secondi, tentando recovery se necessario
- In caso di servizio giù, chiama il Control Plane (CPController) per recovery/escalation
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import threading
import time
import socket
import requests
from pymongo import MongoClient
from requests.auth import HTTPBasicAuth
import yaml

# --- INTEGRAZIONE CONTROL PLANE ---
from cp_core.controller import CPController
cp = CPController()
# -----------------------------------

SETTINGS_FILE = "monitor_settings.yaml"

def load_config(filename):
    """
    Carica la configurazione YAML dal file specificato.
    """
    with open(filename, "r") as f:
        return yaml.safe_load(f)

# Carica la configurazione all'avvio dell'applicazione
CONFIG = load_config(SETTINGS_FILE)

# Istanzia l'applicazione FastAPI
app = FastAPI()

def check_tcp(host, port, timeout=3):
    """
    Verifica la raggiungibilità TCP di un host/porta.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def check_http(url, auth=None, timeout=3):
    """
    Effettua una richiesta HTTP GET.
    """
    try:
        resp = requests.get(url, auth=auth, timeout=timeout)
        if resp.status_code == 200:
            return True
        return False
    except Exception:
        return False

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

def send_to_cp(source, status, extra=None):
    """
    Costruisce un evento e lo invia al CPController per decidere se intervenire e gestire recovery/escalation.
    """
    event = {
        "source": source,
        "status": "ok" if status == "ok" else "critical"  # Mappa "ko" su "critical"
    }
    if extra:
        event.update(extra)
    result = cp.receive_event(event)
    print(f"[CP] {source} => {result}")
    return result

def monitor_services():
    """
    Esegue tutti i check definiti nella config.
    In caso di problemi, invia evento al Control Plane.
    Ritorna lo stato aggregato di tutti i servizi.
    """
    status = {}

    # VPN (TCP check)
    s = "ok" if check_tcp(CONFIG["vpn_host"], CONFIG["vpn_port"]) else "ko"
    status["vpn"] = s
    if s != "ok":
        send_to_cp("vpn", s)

    # NAS (HTTP check)
    s = "ok" if check_http(CONFIG["nas_url"]) else "ko"
    status["nas"] = s
    if s != "ok":
        send_to_cp("nas", s)

    # RabbitMQ (API HTTP check con autenticazione base)
    s = "ok" if check_http(
        CONFIG["rabbitmq_api"], 
        auth=HTTPBasicAuth(CONFIG["rabbitmq_user"], CONFIG["rabbitmq_pass"])
    ) else "ko"
    status["rabbitmq"] = s
    if s != "ok":
        send_to_cp("rabbitmq", s)

    # Prometheus (HTTP check, non critico)
    s = "ok" if check_http(CONFIG["prometheus_url"]) else "ko"
    status["prometheus"] = s
    if s != "ok":
        send_to_cp("prometheus", s)

    # Grafana (HTTP check, non critico)
    s = "ok" if check_http(CONFIG["grafana_url"]) else "ko"
    status["grafana"] = s
    if s != "ok":
        send_to_cp("grafana", s)

    # Portainer (HTTP check, non critico)
    s = "ok" if check_http(CONFIG["portainer_url"]) else "ko"
    status["portainer"] = s
    if s != "ok":
        send_to_cp("portainer", s)

    # MongoDB (connessione driver)
    s = "ok" if check_mongodb(CONFIG["mongodb_uri"]) else "ko"
    status["mongodb"] = s
    if s != "ok":
        send_to_cp("mongodb", s)

    # EC2 (TCP check)
    s = "ok" if check_tcp(CONFIG["ec2_host"], CONFIG["ec2_port"]) else "ko"
    status["ec2_tcp"] = s
    if s != "ok":
        send_to_cp("ec2", s)

    # EC2 (HTTP check opzionale, se specificato in config)
    if CONFIG.get("ec2_http_url"):
        s = "ok" if check_http(CONFIG["ec2_http_url"]) else "ko"
        status["ec2_http"] = s
        if s != "ok":
            send_to_cp("ec2", s, extra={"check": "http"})

    # Verifica se tutti i servizi critici sono OK
    critical = ["vpn", "nas", "rabbitmq", "mongodb", "ec2_tcp"]
    all_critical_ok = all(status.get(s) == "ok" for s in critical)
    status["all_critical_ok"] = all_critical_ok

    return status

@app.get("/monitor")
def monitor():
    """
    Endpoint API per vedere lo stato servizi (e triggerare controllo manuale).
    """
    status = monitor_services()
    return JSONResponse(content=status)

def scheduler_loop(interval=60):
    """
    Thread di monitoraggio automatico: esegue i check ogni 'interval' secondi.
    """
    while True:
        print("[MONITOR] Controllo automatico...")
        monitor_services()
        time.sleep(interval)

if __name__ == "__main__":
    # Avvia il thread del monitor automatico all'avvio del servizio
    t = threading.Thread(target=scheduler_loop, args=(60,), daemon=True)  # ogni 60 secondi
    t.start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
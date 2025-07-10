"""
cp_core/recovery.py

RecoveryManager: gestisce la recovery automatica specifica per ogni servizio critico.
- MongoDB su Atlas: tenta connessione e controlla dimensione database, usando parametri da config YAML.
- RabbitMQ in Docker: restart container (nome da config).
- EC2 consumer: recovery non automatica (solo log/messaggio).
- NAS: recovery fittizia/manuale.
- VPN: recovery non automatica/manuale.
- Portainer in Docker: restart container (nome da config).
- Prometheus in Docker: restart container (nome da config).

Tutte le recovery producono log dettagliati e restituiscono esito (success, dettaglio).

Autore: MK023 + Copilot
"""

import subprocess
from pymongo import MongoClient

class RecoveryManager:
    def __init__(self, config):
        """
        Accetta la configurazione (dict) già caricata da config_all.yaml.
        """
        self.config = config

    def recover(self, event):
        """
        Entry point: seleziona la recovery in base al tipo di servizio.
        Ritorna: (success: bool, dettaglio: str)
        """
        source = event.get("source", "").lower()
        if source == "mongodb":
            return self.recover_mongodb_atlas()
        elif source == "rabbitmq":
            return self.recover_rabbitmq_docker()
        elif source == "ec2":
            return self.recover_ec2_consumer()
        elif source == "nas":
            return self.recover_nas()
        elif source == "vpn":
            return self.recover_vpn()
        elif source == "portainer":
            return self.recover_portainer_docker()
        elif source == "prometheus":
            return self.recover_prometheus_docker()
        else:
            return False, f"Recovery non implementata per '{source}'"

    def recover_mongodb_atlas(self):
        """
        Recovery MongoDB Atlas:
        - Tenta una connessione al cluster (se fallisce, recovery fallita)
        - (Opzionale) Controlla la dimensione totale del db e la riporta nei log
        """
        try:
            mongo_conf = self.config["mongodb"]
            mongo_uri = mongo_conf["uri"]
            db_name = mongo_conf["database"]
            # Timeout opzionale, default 5000ms
            timeout = int(mongo_conf.get("timeout_ms", 5000))
        except Exception as e:
            return False, f"Configurazione MongoDB mancante o invalida: {e}"

        try:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=timeout)
            client.admin.command('ping')
            stats = client[db_name].command("dbstats")
            db_size_mb = stats.get("dataSize", 0) / (1024 * 1024)
            msg = f"MongoDB Atlas raggiungibile (ping OK). Dimensione db '{db_name}': {db_size_mb:.2f} MB"
            return True, msg
        except Exception as e:
            return False, f"MongoDB Atlas non raggiungibile o errore stats: {e}"

    def recover_rabbitmq_docker(self):
        """
        Recovery RabbitMQ (in Docker):
        - Riavvia il container chiamato 'rabbitmq'
        - (Opzionale: nome container da config)
        """
        container = self.config.get("rabbitmq", {}).get("docker_container", "rabbitmq")
        try:
            result = subprocess.run(["docker", "restart", container], capture_output=True, text=True)
            if result.returncode == 0:
                return True, f"RabbitMQ (docker) restart OK: {result.stdout.strip()}"
            return False, f"RabbitMQ (docker) restart FAIL: {result.stderr.strip()}"
        except Exception as e:
            return False, f"Errore recovery RabbitMQ (docker): {e}"

    def recover_ec2_consumer(self):
        """
        Recovery EC2 Consumer:
        - NON automatica (accesso solo via putty/ssh manuale)
        """
        return False, "Recovery EC2 non automatica: accesso solo manuale tramite SSH/putty!"

    def recover_nas(self):
        """
        Recovery NAS produttore:
        - Recovery solo simulata/manuale (hardware personale)
        """
        return False, "Recovery NAS non automatica: richiede intervento manuale sull'hardware!"

    def recover_vpn(self):
        """
        Recovery VPN:
        - Non automatizzabile (richiede intervento umano per sicurezza/autenticazione)
        """
        return False, "Recovery VPN non automatica: richiede intervento manuale su tunnel/connessione!"

    def recover_portainer_docker(self):
        """
        Recovery Portainer (in Docker):
        - Riavvia il container chiamato 'portainer'
        - (Opzionale: nome container da config)
        """
        container = self.config.get("portainer", {}).get("docker_container", "portainer")
        try:
            result = subprocess.run(["docker", "restart", container], capture_output=True, text=True)
            if result.returncode == 0:
                return True, f"Portainer (docker) restart OK: {result.stdout.strip()}"
            return False, f"Portainer (docker) restart FAIL: {result.stderr.strip()}"
        except Exception as e:
            return False, f"Errore recovery Portainer (docker): {e}"

    def recover_prometheus_docker(self):
        """
        Recovery Prometheus (in Docker):
        - Riavvia il container chiamato 'prometheus'
        - (Opzionale: nome container da config)
        """
        container = self.config.get("prometheus", {}).get("docker_container", "prometheus")
        try:
            result = subprocess.run(["docker", "restart", container], capture_output=True, text=True)
            if result.returncode == 0:
                return True, f"Prometheus (docker) restart OK: {result.stdout.strip()}"
            return False, f"Prometheus (docker) restart FAIL: {result.stderr.strip()}"
        except Exception as e:
            return False, f"Errore recovery Prometheus (docker): {e}"
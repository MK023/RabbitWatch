# 🚀 Super Monitor & Control Plane Stack

---

## 🇬🇧 English

### Description

**Super Monitor & Control Plane Stack** is a complete open source solution for **active monitoring and automated recovery management** for your cloud, on-premise, or hybrid infrastructure.

A FastAPI service performs periodic health checks on all your critical services (VPN, NAS, RabbitMQ, database, Prometheus, Grafana, Portainer, VM, and more). If a problem is detected, it triggers automatic recovery or escalation via a centralized Control Plane (CPController).

This project integrates leading OSS tools for monitoring (Prometheus, Grafana, Alertmanager, exporters), event management (RabbitMQ), visualization (Grafana, Portainer), and provides a ready-to-extend base for enterprise deployments.  
**Looking for a plug & play, transparent, extensible, and secure monitoring and self-healing system? You’re in the right place!**

---

### 🗺️ Architecture Diagram
```mermaid
flowchart TD
  subgraph User
    U1["User (Admin/DevOps)"]
  end

  subgraph FastAPI
    FM1["Automatic thread, TCP/HTTP/MongoDB checks"]
    FM2["API /monitor"]
  end

  subgraph CP
    CP1["Receives KO events"]
    CP2["Recovery/Escalation"]
  end

  subgraph Prometheus
    PR1["Scrapes Exporters & Monitor"]
    PR2["Alert Rules"]
    PR3["Alertmanager"]
  end

  subgraph Exporters
    EX1["Node/MongoDB Exporter"]
  end

  subgraph RabbitMQ
    RM1["Event/metrics queues"]
    RM2["Producer/Consumer Python"]
  end

  subgraph Grafana
    GF1["Dashboards"]
  end

  subgraph Portainer
    PO1["Visual Container Management"]
  end

  U1 -- "Status Request" --> FM2
  FM2 -- "Status Response" --> U1

  FM1 -- "Service healthchecks" --> PR1
  FM1 -- "KO Events" --> CP1
  CP1 --> CP2

  EX1 -- "Metrics" --> PR1
  PR1 -- "Metrics Query" --> GF1
  PR1 -- "Alerts" --> PR2 --> PR3

  FM1 -- "Events/metrics" --> RM1
  RM2 <--> RM1

  PO1 -- "Manages" --> FastAPI
  PO1 -- "Manages" --> Grafana
  PO1 -- "Manages" --> Prometheus
  PO1 -- "Manages" --> RabbitMQ
```
---

### Features

- **FastAPI Custom Monitor:** Active health checks, REST API & automatic background thread.
- **Control Plane Integration:** Automated recovery/escalation via pluggable CPController.
- **Prometheus & Alertmanager:** Metrics collection, custom rules, and alerting.
- **Grafana:** Beautiful dashboards.
- **RabbitMQ (+ exporters):** Event-driven metrics architecture.
- **MongoDB Exporter:** Database health and metrics.
- **Portainer:** Visual container management.
- **Python Producer/Consumer:** Metrics collection, push and recovery logic.
- **Secure, modular, production ready.**

---

### Quick Start

1. **Create the Docker network (first time only):**
   ```sh
   docker network create monitoring
   ```

2. **Configure settings:**
   ```sh
   cp monitor_settings.example.yaml monitor_settings.yaml
   # Edit monitor_settings.yaml with your endpoints and credentials
   ```

3. **Bring everything up:**
   ```sh
   docker compose up -d
   ```

4. **(Optional) Build & run the FastAPI monitor:**
   ```sh
   docker build -t fastapi-monitor .
   docker run --network=monitoring -p 8000:8000 -v $(pwd)/monitor_settings.yaml:/app/monitor_settings.yaml:ro fastapi-monitor
   ```
   _Or let Docker Compose manage it!_

---

### What can you monitor?

- VPN and tunnels (TCP)
- NAS and file servers (HTTP)
- RabbitMQ queues (API + exporter)
- Prometheus, Grafana, Portainer (API/health)
- MongoDB (native driver)
- EC2 VM (TCP + HTTP)
- Anything else! Extend `monitor_settings.yaml` and `fastapi_monitor.py`.

---

### Example configuration

```yaml
vpn_host: "YOUR_VPN_IP"
vpn_port: 1194

nas_url: "http://YOUR_NAS_IP:9100/metrics"

rabbitmq_api: "http://rabbitmq:15672/api/health/checks/alarms"
rabbitmq_user: "youruser"
rabbitmq_pass: "yourpassword"

prometheus_url: "http://prometheus:9090/-/healthy"
grafana_url: "http://grafana:3000/api/health"
portainer_url: "http://portainer:9000/api/status"

mongodb_uri: "mongodb+srv://youruser:yourpassword@yourcluster.mongodb.net/?authSource=admin"

ec2_host: "YOUR_EC2_IP"
ec2_port: 22
ec2_http_url: null
```

---

### API Example

```sh
curl http://localhost:8000/monitor
```

Sample response:

```json
{
  "vpn": "ok",
  "nas": "ok",
  "rabbitmq": "ok",
  "prometheus": "ok",
  "grafana": "ok",
  "portainer": "ok",
  "mongodb": "ok",
  "ec2_tcp": "ok",
  "all_critical_ok": true
}
```

---

### Security & Best Practices

- **DO NOT** commit `monitor_settings.yaml` with real credentials.
- Secure Grafana, RabbitMQ, and Portainer with strong passwords.
- Backup persistent directories (`./grafana_data`, `./prometheus_data`, etc.).
- Consider HTTPS and firewalling for production.

---

### Example systemd unit for Python consumer

```ini
[Unit]
Description=Metrics Consumer Python Service
After=network.target openvpn-client@VPNConfig.service
Requires=openvpn-client@VPNConfig.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/bin/python3 /home/ubuntu/metrics_consumer.py --config /home/ubuntu/config_consumer.yaml
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

### Repository structure

- `docker-compose.yml` — all containers orchestration
- `fastapi_monitor.py` — monitoring logic & REST API
- `monitor_settings.example.yaml` — config template
- `Dockerfile` — custom monitor build
- `requirements.txt` — Python deps
- `grafana_data/`, `prometheus_data/`, `rabbitmq/`, etc. — persistent
- `config_all.yaml` — Python producer/consumer config example
- ...and much more!

---

### Tips

- **Add more exporters/services:** Edit `docker-compose.yml` and the YAML config.
- **Debug containers:**  
  ```sh
  docker compose logs -f
  ```
- **Customize healthchecks:** Edit `fastapi_monitor.py` and rebuild.

---

## 🎉 Celebrate your first release!

You’ve built a modern, extensible, and secure stack.  
If you like this project, ⭐️ star it and share!

---

## 📖 License

MIT (or your own policy)

---

## 👤 Author

🎈 **MK023**  
_2025 - Happy Monitoring!_

---

## 🇮🇹 Italiano

### Descrizione

**Super Monitor & Control Plane Stack** è una soluzione open source completa per il **monitoraggio attivo e la gestione automatica dei servizi** in ambienti cloud, on-premise o ibridi.

Il cuore del sistema è un servizio FastAPI che esegue healthcheck periodici su tutti i servizi critici (VPN, NAS, RabbitMQ, database, Prometheus, Grafana, Portainer, VM, ecc.) e, in caso di problemi, attiva recovery o escalation tramite un Control Plane centralizzato (CPController).

Il progetto integra i migliori tool OSS per il monitoring (Prometheus, Grafana, Alertmanager, exporter vari), la gestione eventi (RabbitMQ), la visualizzazione (Grafana, Portainer) e offre una base pronta per estendere la tua architettura verso produzioni enterprise.  
**Se cerchi un sistema plug & play, trasparente, estendibile e sicuro per monitorare e autogestire la tua infrastruttura… sei nel posto giusto!**

---

### 🗺️ Schema Architetturale

*(Vedi sopra, lo schema è universale)*

---

### Cosa include

- **FastAPI Custom Monitor:** Health check attivi, API REST, thread automatico.
- **Control Plane Integration:** Recovery ed escalation via CPController (modulare!)
- **Prometheus & Alertmanager:** Metriche, regole personalizzate, allarmi.
- **Grafana:** Dashboard visive e potenti.
- **RabbitMQ (+ exporter):** Code/eventi per architetture event-driven.
- **MongoDB Exporter:** Metriche e salute database.
- **Portainer:** Gestione visuale dei container.
- **Producer/Consumer Python:** Raccolta, invio, gestione metriche e recovery.
- **Sicurezza, modularità, best practice.**

---

### Quickstart

1. **Crea la Docker network (solo la prima volta):**
   ```sh
   docker network create monitoring
   ```

2. **Configura i parametri:**
   ```sh
   cp monitor_settings.example.yaml monitor_settings.yaml
   # Modifica monitor_settings.yaml con i tuoi endpoint e credenziali
   ```

3. **Avvia tutto:**
   ```sh
   docker compose up -d
   ```

4. **(Opzionale) Builda il monitor FastAPI:**
   ```sh
   docker build -t fastapi-monitor .
   docker run --network=monitoring -p 8000:8000 -v $(pwd)/monitor_settings.yaml:/app/monitor_settings.yaml:ro fastapi-monitor
   ```
   _Oppure lascia che ci pensi Docker Compose!_

---

### Cosa puoi monitorare?

- VPN e tunnel (TCP)
- NAS e file server (HTTP)
- Code RabbitMQ (API + exporter)
- Prometheus, Grafana, Portainer (API/health)
- MongoDB (driver nativo)
- VM EC2 (TCP + HTTP)
- E molto altro! Estendi `monitor_settings.yaml` e `fastapi_monitor.py`

---

### Esempio configurazione

*(Vedi sopra, uguale)*

---

### Esempio API

```sh
curl http://localhost:8000/monitor
```

Risposta tipica:

```json
{
  "vpn": "ok",
  "nas": "ok",
  "rabbitmq": "ok",
  "prometheus": "ok",
  "grafana": "ok",
  "portainer": "ok",
  "mongodb": "ok",
  "ec2_tcp": "ok",
  "all_critical_ok": true
}
```

---

### Sicurezza & Best Practice

- **NON** committare `monitor_settings.yaml` con credenziali reali.
- Proteggi Grafana, RabbitMQ, Portainer con password forti.
- Backup delle directory persistenti (`./grafana_data`, `./prometheus_data`, ecc.).
- Per produzione usa HTTPS e firewall.

---

### Esempio unit systemd

*(Vedi sopra, uguale)*

---

### Struttura repository

- `docker-compose.yml` — orchestrazione container
- `fastapi_monitor.py` — logica monitor & REST
- `monitor_settings.example.yaml` — template configurazione
- `Dockerfile` — build monitor custom
- `requirements.txt` — dipendenze Python
- `grafana_data/`, ecc. — dati persistenti
- `config_all.yaml` — esempio producer/consumer Python
- ...e molto altro!

---

### Consigli utili

- **Aggiungi exporter/servizi:** Modifica `docker-compose.yml` e la YAML config.
- **Debug:**  
  ```sh
  docker compose logs -f
  ```
- **Custom check:** Personalizza `fastapi_monitor.py` e rebuilda.

---

## 🎉 Celebra la tua prima pubblicazione!

Hai creato un’infrastruttura moderna, estendibile e sicura.  
Se ti piace questo progetto, ⭐️ mettilo tra i preferiti e condividilo!

---

## 📖 Licenza

MIT (o come da policy)

---

## 👤 Autore

🎈 **MK023**  
_2025 - Happy Monitoring!_

---

# RabbitWatch

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688.svg)](https://fastapi.tiangolo.com/)
[![Prometheus](https://img.shields.io/badge/Prometheus-metrics-E6522C.svg)](https://prometheus.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-event--bus-FF6600.svg)](https://www.rabbitmq.com/)
[![Security Policy](https://img.shields.io/badge/security-policy-brightgreen.svg)](./SECURITY.md)

> **Self-healing monitoring stack: FastAPI health checks + Prometheus/Grafana/Alertmanager + RabbitMQ event bus, with automated recovery for cloud/on-prem infrastructure.**

RabbitWatch is a small, opinionated control-plane that keeps your critical services (VPN, NAS, message brokers, databases, dashboards, VMs) **up and self-healing**. A FastAPI service runs periodic checks; when something fails, events flow through RabbitMQ to a Control Plane (`CPController`) that decides whether to retry, recover, or escalate — and pushes the resulting metrics to Prometheus/Grafana.

It is designed as a **drop-in observability + recovery layer** for small-to-medium Linux fleets that can't justify a full commercial APM, but still need actionable alerting and hands-off remediation.

---

## Architecture

```mermaid
flowchart LR
  U["Admin / DevOps"] -->|"GET /monitor"| API

  subgraph API["FastAPI Monitor"]
    HC["Periodic health checks<br/>(TCP · HTTP · MongoDB)"]
    EP["REST endpoint /monitor"]
  end

  HC -->|"KO events"| CP
  subgraph CP["Control Plane"]
    CTRL["CPController<br/>classification"]
    REC["Recovery / escalation"]
    CTRL --> REC
  end

  HC -->|"events + metrics"| MQ
  subgraph MQ["RabbitMQ"]
    QS["queues"]
    PC["Python producer / consumer"]
    QS <--> PC
  end

  PC -->|"write"| DB[("MongoDB<br/>metrics history")]

  subgraph OBS["Observability"]
    EX["Node + MongoDB<br/>exporters"]
    PR["Prometheus"]
    AM["Alertmanager"]
    GF["Grafana<br/>dashboards"]
    EX --> PR --> GF
    PR --> AM
  end

  HC -.->|"scrape"| PR
  PO["Portainer"] -.->|"manages"| API
  PO -.->|"manages"| MQ
  PO -.->|"manages"| OBS
```

---

## Features

- **Active health checks** — TCP, HTTP (with basic auth), and MongoDB reachability against a YAML-declared set of endpoints.
- **Event-driven recovery** — failures are published to RabbitMQ; the `CPController` decides on retry / escalation strategy without blocking the check loop.
- **Metrics pipeline** — a Python producer pushes structured metrics to MongoDB (with TTL indexes for retention) and to Prometheus via exporters; Grafana visualizes them.
- **Background thread** — health checks run continuously without external schedulers; the REST endpoint just exposes the latest aggregate.
- **Portainer-friendly** — every component is a standalone container managed via `docker-compose`; Portainer gives a visual UI if you want one.
- **Extensible** — add a new service type by extending `fastapi_monitor.py` and the YAML schema.
- **Hardenable** — deployment guidance and threat model are documented in [SECURITY.md](./SECURITY.md).

---

## Stack

| Layer | Component |
|---|---|
| HTTP monitor + REST API | FastAPI, Uvicorn, `requests` |
| Event bus | RabbitMQ + exporters |
| Metrics store | MongoDB + MongoDB exporter |
| Metrics collection | Prometheus + Alertmanager |
| Visualization | Grafana |
| Orchestration | Docker Compose + systemd |
| Container management | Portainer (optional) |

Pinned Python dependencies live in [`requirements.txt`](./requirements.txt). Container versions are pinned in `docker-compose.yml`.

---

## Quick start

> Prerequisites: Docker (+ Compose plugin), a Linux host with at least 2 GB RAM, and one free port for the monitor (default `8000`).

1. **Create the Docker network** (first run only):

   ```sh
   docker network create monitoring
   ```

2. **Copy and edit the config**:

   ```sh
   cp monitor_settings.example.yaml monitor_settings.yaml
   # then edit monitor_settings.yaml with your endpoints and credentials
   ```

3. **Bring the stack up**:

   ```sh
   docker compose up -d
   ```

4. **Hit the monitor**:

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

If `all_critical_ok` is `false`, the failing service name is the field to check, and a KO event will have already been published to RabbitMQ for the Control Plane to handle.

---

## What you can monitor out of the box

- VPNs and tunnels (TCP reachability)
- NAS and file servers (HTTP endpoints)
- RabbitMQ queues (management API + exporter)
- Prometheus, Grafana, Portainer (health APIs)
- MongoDB clusters (native driver)
- EC2 or any VM (TCP + optional HTTP)

Anything else is one extension of `monitor_settings.yaml` + one check function in `fastapi_monitor.py` away.

---

## Configuration example

```yaml
vpn_host: "YOUR_VPN_IP"
vpn_port: 1194

nas_url: "http://YOUR_NAS_IP:9100/metrics"

rabbitmq_api: "http://rabbitmq:15672/api/health/checks/alarms"
rabbitmq_user: "youruser"
rabbitmq_pass: "yourpassword"

prometheus_url: "http://prometheus:9090/-/healthy"
grafana_url:    "http://grafana:3000/api/health"
portainer_url:  "http://portainer:9000/api/status"

mongodb_uri: "mongodb+srv://youruser:yourpassword@yourcluster.mongodb.net/?authSource=admin"

ec2_host: "YOUR_EC2_IP"
ec2_port: 22
ec2_http_url: null
```

> **Never commit** the real `monitor_settings.yaml`. The repo `.gitignore` already excludes `*.yaml` and `*.env` to prevent accidental leaks. Treat the `*.example.yaml` files as templates only — their values are placeholders, not defaults.

---

## Running the Python consumer as a systemd service

```ini
[Unit]
Description=RabbitWatch metrics consumer
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

## Repository layout

```
.
├── fastapi_monitor.py    # active health checks + REST /monitor
├── api/                  # thin FastAPI wiring
├── agents/               # check agents (CLI demo)
├── cp_core/              # Control Plane: controller + recovery logic
├── consumer/             # RabbitMQ consumer + MongoDB TTL indexes
├── producer/             # metrics producer pushing to RabbitMQ
├── service/              # systemd / service integration helpers
├── script/               # one-off operational scripts
├── docs/                 # additional documentation
├── requirements.txt      # pinned Python deps
├── SECURITY.md           # threat model + reporting
└── README.md
```

---

## Security

See [SECURITY.md](./SECURITY.md) for the threat model, in-scope / out-of-scope definitions, deployment hardening guidance, and the private reporting channel for vulnerabilities.

The short version:

- Run RabbitWatch **behind a trusted network boundary** (VPN, VPC, or Cloudflare Tunnel) — the `/monitor` endpoint is not currently authenticated.
- **Rotate every credential** from the example configs before production.
- Grant the MongoDB user least-privilege access to the metrics database only.

---

## Troubleshooting

- **Stack won't start**: `docker compose logs -f` — most issues are either a missing `monitoring` Docker network or a placeholder still sitting in `monitor_settings.yaml`.
- **`/monitor` returns `ok` but Grafana is empty**: check Prometheus is scraping the exporters (`/targets` page), and that the consumer is running (systemd status or the container log).
- **Alertmanager silent**: verify `alertmanager.yml` is mounted into the container and `docker compose restart alertmanager` after edits.

---

## Roadmap

- [ ] Optional API-key or mTLS authentication on `/monitor`
- [ ] GitHub Actions CI: ruff + pip-audit + bandit on every PR
- [ ] Dependabot configuration for weekly dependency hygiene
- [ ] Helm chart for Kubernetes deployments (currently Docker Compose only)

---

## License

Released under the [MIT License](./LICENSE).

## Author

**Marco Bellingeri** ([MK023](https://github.com/MK023)) — Cloud Platform & Security Engineer.
Contributions, issues, and discussions are welcome.

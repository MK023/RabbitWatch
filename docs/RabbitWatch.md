# RabbitWatch – Architettura e Flusso Metriche

## Schema Architetturale

```mermaid
flowchart LR
    NAS["NAS Synology<br>(Node Exporter)"] -- VPN --> Producer["Producer"]
    Producer --> RabbitMQ["RabbitMQ<br>(AWS)"]
    RabbitMQ -->|Coda #1| Consumer["Consumer<br>(Railway)"]
    RabbitMQ -->|Coda #2| Consumer
    Consumer --> MongoDB["MongoDB Atlas<br>(Railway)"]
    RabbitMQ --> Prometheus["Prometheus<br>(AWS)"]
    Prometheus --> Grafana["Grafana<br>(AWS)"]
    Portainer["Portainer<br>(AWS)"] -.-> RabbitMQ
```

**Legenda:**
- **AWS:** RabbitMQ, Prometheus, Grafana, Portainer
- **Railway:** Consumer, MongoDB Atlas
- **NAS Synology:** dietro VPN, trasmette metriche tramite Node Exporter

---

## Checklist Modifiche Architettura

- [ ] Deploy RabbitMQ, Prometheus, Grafana, Portainer su AWS
- [ ] Deploy Consumer e MongoDB Atlas su Railway
- [ ] Configurare VPN tra NAS Synology e Producer
- [ ] Aggiornare i flussi producer/consumer per lavorare con RabbitMQ/MongoDB su AWS/Railway
- [ ] Aggiornare la documentazione

---
# Security Policy

## Supported Versions

Only the `main` branch receives security updates. Older tags or forks are not maintained.

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| older   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it **privately**.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, send an email to the maintainer at **marco.bellingeri@gmail.com** with:

1. A description of the vulnerability
2. Steps to reproduce the issue (with a minimal example if possible)
3. Potential impact (confidentiality, integrity, availability)
4. Suggested fix, if any

You will receive an acknowledgment **within 72 hours** and a planned timeline for a fix or mitigation.

## Threat Model

RabbitWatch is a self-hosted monitoring and control-plane stack. The threat model assumes:

- The stack runs **behind a trusted network boundary** (VPC, VPN, private LAN, or Cloudflare Tunnel). The `/monitor` endpoint and the RabbitMQ/Grafana/Prometheus/Portainer UIs are **not designed for direct exposure to the public Internet**.
- All credentials (RabbitMQ user/password, MongoDB URI, Grafana admin, Portainer admin) are provided via `monitor_settings.yaml` and environment variables. These files **must not be committed to version control** — `.gitignore` already excludes `*.yaml`, `*.env` and related patterns.
- The Docker host and the `monitoring` Docker network are considered trusted: any workload in the same network can reach the monitored services.

### In scope

- Logic bugs in `fastapi_monitor.py`, `producer/`, `consumer/`, and `cp_core/` that allow bypassing health checks, injecting events into RabbitMQ, or corrupting MongoDB state without authentication.
- Secrets accidentally committed to the repository history.
- Dependency vulnerabilities reported by `pip-audit` or GitHub Dependabot on the pinned versions in `requirements.txt`.
- Privilege-escalation paths in the Docker Compose definitions (once published).

### Out of scope

- Attacks that require physical or privileged access to the Docker host.
- Denial-of-service from a trusted client inside the monitored network.
- Vulnerabilities in the upstream components (Prometheus, Grafana, Alertmanager, RabbitMQ, MongoDB, Portainer) — report those to their respective projects.
- Misconfigurations caused by deploying the stack with the example credentials unchanged.

## Security Considerations for Operators

When deploying RabbitWatch in production:

- **Rotate and harden every credential** in `monitor_settings.yaml`. The `*.example.yaml` file is a template; never reuse its values.
- **Restrict network exposure**: keep the `/monitor` endpoint and all admin UIs behind VPN, Cloudflare Tunnel, or an authenticating reverse proxy.
- **Enable HTTPS/TLS** on any endpoint that leaves the trusted network.
- **Back up persistent volumes** (`grafana_data/`, `prometheus_data/`, the RabbitMQ data directory) regularly and store backups encrypted at rest.
- **Run the FastAPI monitor as a non-root user** both in systemd and inside Docker.
- **Apply least privilege** to the MongoDB user used by the metrics consumer: read/write on the dedicated metrics database only.

## Known Limitations

- The `/monitor` HTTP endpoint currently exposes status information **without authentication**. This is acceptable behind a VPN / reverse proxy, but unsafe on a public interface. Adding an API-key or mTLS layer is tracked as a follow-up improvement.
- CI-side security scanning (Bandit, pip-audit, Gitleaks, CodeQL) is not yet wired into this repository. Contributors are encouraged to run these tools locally before opening a pull request. Adding them to GitHub Actions is tracked as a follow-up improvement.

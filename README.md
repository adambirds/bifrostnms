# BifrostNMS

**A modern, lightweight, distributed Network Monitoring System.**

> See your network from everywhere.

BifrostNMS is an open-source network monitoring platform inspired by the distributed monitoring model that made SmokePing so useful, rebuilt around a modern API, web interface, and lightweight remote probe agents.

The project is designed around a central control plane and small agents deployed across different hosts, networks, regions, and providers. Agents run monitoring probes locally and report measurements back to the server so latency, packet loss, availability, DNS, HTTP and other network behaviour can be compared from multiple vantage points.

## Goals

- Lightweight enough to self-host on modest hardware.
- Distributed monitoring from any number of remote agents.
- Configuration through the web UI and API, with configuration-as-code support where useful.
- Excellent historical latency and packet-loss visualisation.
- Extensible probe system without coupling every probe to the core server.
- First-class Docker and Dev Container development experience.
- A useful open-source product first, with BifrostNMS Cloud planned as a hosted service.

## Planned architecture

```text
                        +---------------------+
                        |   BifrostNMS Web    |
                        |   React / Vite      |
                        +----------+----------+
                                   |
                                   v
+----------------+       +---------+----------+       +----------------+
| Remote Agent A | ----> | BifrostNMS Server | <---- | Remote Agent B |
|       Go       |       | FastAPI + Tortoise|       |       Go       |
+----------------+       +---------+----------+       +----------------+
                                   |
                          +--------+---------+
                          | PostgreSQL/Redis |
                          +------------------+
```

The initial monorepo is split into:

- `backend/` — FastAPI control plane, API and persistence layer.
- `frontend/` — React/Vite web application.
- `agent/` — lightweight Go probe agent.
- `deploy/` — deployment and container orchestration assets.
- `docs/` — architecture, probe and operational documentation.
- `tools/` — repository development tooling.

The exact architecture will evolve while the first probes and data model are implemented. The intent is to keep the server and agents small rather than introduce infrastructure purely for its own sake.

## Probe direction

The first useful milestone will focus on ICMP latency/packet loss, followed by probes such as DNS and HTTP/HTTPS. Where mature system utilities such as `fping`, `dig` or `curl` provide better behaviour than reimplementing a protocol, BifrostNMS can wrap them behind a consistent probe interface. Native implementations can be used where they provide a clear portability or operational benefit.

## Development

The recommended development environment is VS Code Dev Containers. Clone the repository and choose **Dev Containers: Reopen in Container**.

The development container provides Python, Node.js/pnpm, Go, PostgreSQL, Redis and the network utilities needed to develop probes.

See `CONTRIBUTING.md` for the development workflow and `AGENTS.md` for guidance for AI coding agents.

## Status

BifrostNMS is at the beginning of development. APIs, storage formats and configuration are expected to change before the first stable release.

## Contributing

Contributions, ideas, bug reports and probe implementations are welcome. Please read `CONTRIBUTING.md` before opening a pull request.

## Sponsoring

If BifrostNMS becomes useful to you or your organisation, see `SPONSORS.md` for ways to support continued development.

## License

A project licence will be added before the first public release. Until then, the repository being publicly readable should not be interpreted as granting rights beyond those provided by GitHub's Terms of Service.

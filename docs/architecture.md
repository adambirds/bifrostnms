# Architecture

BifrostNMS uses a central FastAPI control plane and independently deployable Go agents. The server owns configuration, identity, persistence and query APIs. Agents own probe execution at their local network vantage point.

The first implementation should favour direct, boring communication between agents and the server. A message broker must not be introduced until workload or reliability requirements demonstrate that it solves a real problem.

## Components

### Server

FastAPI exposes management and ingestion APIs. Tortoise ORM maps the relational model to PostgreSQL.

### Agent

The Go agent fetches/receives assigned probe configuration, executes probes with deadlines and reports structured measurements. It should have a small memory/CPU footprint and minimal runtime dependencies.

### Web

The React/Vite UI configures agents, targets and probes and visualises current and historical measurements.

## Data

Raw measurements should be immutable. Retention/downsampling strategy will be designed after measuring realistic write/query volumes rather than assuming a particular time-series database is required.

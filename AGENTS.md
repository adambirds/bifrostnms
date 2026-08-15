# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

BifrostNMS is a modern distributed Network Monitoring System. It consists of a FastAPI control plane, React/TypeScript web UI and lightweight Go agents deployed at monitoring vantage points.

## Architectural priorities

1. Keep the agent small, reliable and easy to deploy.
2. Keep the control plane understandable; do not introduce distributed infrastructure without demonstrated need.
3. Treat probe input as untrusted. Never interpolate targets into shell commands.
4. Monitoring measurements are time-series data; preserve timestamps, agent identity, target identity and probe configuration needed to interpret a result.
5. Agents must tolerate temporary server/network failure and recover cleanly.
6. UI/API configuration is primary, but design models so configuration-as-code/import/export can be supported cleanly.
7. Prefer explicit APIs and typed contracts between server, frontend and agent.

## Stack

- Backend: Python 3.12+, FastAPI, Tortoise ORM, Pydantic, PostgreSQL, Redis only where justified.
- Agent: Go.
- Frontend: React, TypeScript, Vite, Apollo/HTTP tooling only where the API design requires it, Tailwind CSS.
- Tooling: Ruff, mypy, pytest, ESLint, Prettier, Stylelint, gofmt, go vet, go test.

Do not introduce Django. Do not replace Tortoise ORM without an explicit architectural decision.

## Working rules

Read nearby code and tests before editing. Keep changes scoped to the request. Add tests for behaviour. Do not silently weaken lint/type/test rules. Do not commit secrets, credentials, generated coverage output or local environment files.

Run `tools/lint` and `tools/test-all` before considering a change complete. If a check cannot run, state exactly why.

For Go, run `gofmt` on changed files and keep dependencies minimal. For Python, use modern typing and async APIs where appropriate. For TypeScript, keep strict typing and avoid `any` unless unavoidable and documented.

## Probe safety

External utilities such as `fping`, `dig` and `curl` may be used behind probe adapters when they provide mature functionality. Execute them directly with argument lists, enforce deadlines, capture bounded output, validate target/config values and return structured errors. Never use `shell=True` or equivalent for target-controlled input.

## Repository structure

Do not move top-level components casually. Shared protocol/schema definitions should have one authoritative source and a documented generation path if code generation is introduced.

## Documentation

Update README/docs when adding a user-visible feature, probe, environment variable, port, deployment requirement or breaking API/configuration change.

# Contributing to BifrostNMS

Thanks for considering a contribution.

BifrostNMS is intentionally being built as a small, understandable system. Prefer straightforward implementations and measurable operational benefits over adding infrastructure or abstractions pre-emptively.

## Development environment

The recommended environment is VS Code with Dev Containers.

```bash
git clone git@github.com:adambirds/bifrostnms.git
cd bifrostnms
code .
```

Then choose **Dev Containers: Reopen in Container**. The container installs the Python, Node.js/pnpm and Go toolchains plus PostgreSQL, Redis and common network probe utilities.

## Repository layout

- `backend/` — FastAPI API/control plane using Tortoise ORM.
- `frontend/` — React + TypeScript + Vite web UI.
- `agent/` — Go remote monitoring agent.
- `deploy/` — deployment assets.
- `docs/` — project documentation.
- `tools/` — development scripts.

## Branches and commits

Create a focused branch from `main`. Keep commits small and coherent. Commit messages are checked with gitlint; use an imperative subject and explain non-obvious reasoning in the body.

## Quality checks

Run:

```bash
tools/lint
tools/test-all
```

Python should pass Ruff, mypy and pytest. Go should pass `gofmt`, `go vet` and `go test`. Frontend code should pass ESLint, Prettier, Stylelint and its tests once the frontend is bootstrapped.

## Dependencies

Python top-level dependencies live in `backend/requirements/*.in`; generated lock files live beside them as `*.txt`. Use `tools/update-requirements` after changing an input file.

Go dependencies are managed with Go modules in `agent/`. JavaScript dependencies are managed with pnpm from the repository root.

Avoid dependencies for functionality that can be implemented clearly with the standard library. This is particularly important for the Go agent.

## Pull requests

A PR should describe what changed, why it changed, how it was tested, and any operational/security implications. Add or update tests for behavioural changes. Update documentation when configuration, APIs or user-visible behaviour changes.

## Probe contributions

Probe implementations must have bounded execution time, explicit timeouts, predictable resource usage, structured results, and no shell interpolation of untrusted target data. Prefer argument arrays over invoking commands through a shell.

## Security

Do not open a public issue for a vulnerability that would put deployed BifrostNMS installations at immediate risk. A private reporting process will be documented before the first stable release.

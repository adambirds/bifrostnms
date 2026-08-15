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

Create a focused branch from `main` and keep commits small and coherent. Commit
messages are checked automatically with gitlint and must use this title format:

```text
<type>: <Imperative summary>.
```

Choose one of the following lowercase types:

- `feat` — new user-visible functionality.
- `fix` — a bug fix.
- `refactor` — a code change that neither fixes a bug nor adds a feature.
- `test` — test-only changes.
- `docs` — documentation-only changes.
- `style` — formatting or other non-functional source changes.
- `build` — build system or dependency changes.
- `ci` — continuous-integration changes.
- `deployment` — containers, packaging or deployment changes.
- `chore` — repository maintenance not covered by another type.

Start the summary with a capital letter, write it in imperative mood, and end it
with a period. The complete title, including the prefix and final period, must
not exceed 76 characters. For example:

```text
fix: Fix issue with authentication.
refactor: Change the two-factor method we use.
ci: Update action to new version.
deployment: Add new step to Dockerfile.
```

Do not use past tense, a gerund or third-person wording such as `Fixed`, `Fixing`
or `Fixes`. A commit body is optional. When one is useful, separate it from the
title with a blank line, explain the reason for the change, and keep each line at
or below 76 characters.

Run `tools/commit-message-lint` before pushing and correct every reported
violation. Do not bypass the commit-message checks.

## Quality checks

Run:

```bash
git add <new-files>
tools/lint
tools/test-all
```

`tools/lint` discovers tracked files through Git. Stage newly created files
before running it or they will not be checked. Review the staged changes with
`git status` before continuing; staging for lint does not require committing the
files immediately.

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

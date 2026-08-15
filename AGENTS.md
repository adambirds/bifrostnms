# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

BifrostNMS is a modern distributed Network Monitoring System consisting of a FastAPI control plane, separate Next.js 16 authentication and dashboard applications, and lightweight Go agents deployed at monitoring vantage points.

## Architectural priorities

1. Design persistent domain models deliberately before building features that depend on them.
2. Realm tenancy is fundamental. Persistent realm-owned data must have an explicit, reviewable tenancy boundary.
3. Keep agents self-contained, reliable and portable. Native Go implementations are the default for ICMP, DNS, HTTP, TCP, TLS, traceroute and other probes.
4. Requiring external command-line tools such as `fping`, `dig`, `curl` or `traceroute` is exceptional and requires explicit architectural justification.
5. Agents must continue operating during control-plane/network outages and will use local SQLite for configuration state and unsynchronised observations.
6. PostgreSQL/TimescaleDB stores persistent application and monitoring data. Redis stores browser sessions and appropriate ephemeral state.
7. Prefer explicit typed APIs/contracts between backend, frontends and agent.
8. Design for known future requirements without implementing speculative distributed complexity early.

## Stack

- Backend: Python 3.12+, FastAPI, Tortoise ORM, Pydantic.
- Persistent database: PostgreSQL with TimescaleDB for monitoring time-series data.
- Ephemeral/session store: Redis.
- Agent: Go, with SQLite for durable local operation/offline sync.
- Auth frontend: Next.js 16, React 19, TypeScript, App Router.
- Dashboard frontend: Next.js 16, React 19, TypeScript, App Router.
- Tooling: repository `tools/` suite, Ruff, mypy, pytest, ESLint, Prettier, Stylelint, gofmt, go vet and go test.

Do not introduce Django or replace Tortoise ORM without an explicit architectural decision.

## Authentication

Authentication is a first-class subsystem, not a later add-on. Passwords, TOTP/recovery codes and WebAuthn/passkeys are supported from the initial architecture. Browser sessions are opaque tokens stored in Redis; the raw session token must never be stored in PostgreSQL or logged. Use established security libraries rather than implementing cryptographic primitives manually.

Read `docs/architecture/authentication.md` before changing authentication behaviour.

## Database changes

Use Tortoise's built-in migration system. Do not use `generate_schemas()` as a substitute for migrations and do not introduce Aerich. After changing persistent models, create and review a migration using `tools/db-makemigrations`, then apply it with `tools/db-migrate`.

Read `docs/development/database-migrations.md` before changing schemas.

## Commit messages

When creating a commit, agents must use this exact title format:

```text
<type>: <Imperative summary>.
```

Use one of these lowercase types:

- `feat` for new user-visible functionality.
- `fix` for a bug fix.
- `refactor` for a code change that neither fixes a bug nor adds a feature.
- `test` for test-only changes.
- `docs` for documentation-only changes.
- `style` for formatting or other non-functional source changes.
- `build` for build system or dependency changes.
- `ci` for continuous-integration changes.
- `deployment` for containers, packaging or deployment changes.
- `chore` for repository maintenance not covered by another type.

The summary after the prefix must start with a capital letter, use imperative mood,
end with a period and make the commit's purpose specific. The complete title,
including its prefix and final period, must not exceed 76 characters. Do not use
past tense, a gerund or third-person wording such as `Fixed`, `Fixing` or `Fixes`.

A body is optional. Separate it from the title with a blank line, explain why the
change is needed when the title is not sufficient and keep every body line at or
below 76 characters.

Valid examples:

```text
fix: Fix issue with authentication.
refactor: Change the two-factor method we use.
ci: Update action to new version.
deployment: Add new step to Dockerfile.
```

Invalid examples include `fix: fixed authentication` (past tense, no capital and
no period), `Fix authentication.` (missing type) and titles longer than 76
characters. Before handing off any commit, run `tools/commit-message-lint` and
correct every reported violation. Do not bypass the commit-message rules.

## Working rules

Read nearby code/tests/docs before editing. Keep changes scoped. Add tests for behaviour. Do not silently weaken lint/type/test rules. Do not commit secrets, credentials, local environment files or generated coverage output.

The lint runner only discovers files that are tracked by Git. Before running
`tools/lint`, stage all intended new files with `git add` so they are included;
an untracked file receiving no lint output is not evidence that it passes. Review
the staged scope with `git status`, then run `tools/lint` and `tools/test-all`
before considering a change complete. If a check cannot run, state exactly why.

When a cohesive requested task is fully implemented and validated, create a
commit for it using the repository's commit-message rules. Do not leave completed
work staged without a commit. For a large feature, multiple requested changes or
work that requires follow-up turns, do not create a premature catch-all commit;
commit each complete logical milestone separately as the work progresses.

Branch-and-pull-request workflow is the default for all changes. Large features,
multi-feature changes and work expected to require several follow-up commits must
always be developed on a dedicated branch and submitted through a pull request;
do not commit that work directly to `main`. Create the branch before the first
feature commit, keep its commits scoped to logical milestones and use the pull
request for consolidated review and validation.

During early development, the repository owner may explicitly allow a small,
single-purpose, low-risk change to be committed directly to `main`. Treat this as
an exception, not the default, and do not apply it to large or multi-feature work.
If the intended workflow is unclear, use a branch and pull request.

Keep Git history linear. Update a working branch by fetching the target branch
and rebasing onto it; do not merge `main` or another target branch into the
working branch. Do not create or push merge commits. If rebasing a published
branch rewrites commits that already exist on the remote and makes the update
non-fast-forward, use `git push --force-with-lease`, never plain `--force`. A
normal push remains appropriate when the remote branch is still an ancestor of
the local branch. Resolve rebase conflicts deliberately, rerun the relevant
checks and verify the rewritten commit history before pushing.

For Go, keep dependencies minimal; `tools/lint` runs `gofmt` and `go vet`, and
`tools/lint --fix` applies `gofmt`. For Python, use modern typing and async APIs.
For TypeScript, keep strict typing and avoid `any` unless unavoidable and
documented.

## Documentation

Update README/docs when adding a user-visible feature, environment variable, port, deployment requirement, data-store requirement, authentication change or breaking API/configuration change.

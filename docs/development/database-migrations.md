# Database migrations

BifrostNMS uses Tortoise ORM's built-in migration system. Aerich is not used.

The migration configuration lives in `backend/bifrostnms/database.py` and migrations live in `backend/bifrostnms/migrations/`.

## First-time development database

Inside the Dev Container:

```bash
./tools/db-bootstrap
```

If the repository has no migration yet, this creates the initial migration and then applies it. The generated migration file must be committed.

## Normal model change workflow

After changing a Tortoise model:

```bash
./tools/db-makemigrations --name describe_change
./tools/db-migrate
```

Review the generated migration before committing it. Do not edit the database schema manually to avoid creating drift between deployed databases and migration history.

## Inspect migration history

```bash
./tools/db-history
```

You can also use the Tortoise CLI directly:

```bash
PYTHONPATH=backend tortoise -c bifrostnms.database.TORTOISE_ORM heads
PYTHONPATH=backend tortoise -c bifrostnms.database.TORTOISE_ORM history
PYTHONPATH=backend tortoise -c bifrostnms.database.TORTOISE_ORM sqlmigrate models 0001_initial
```

## Existing development volume created by `generate_schemas`

Early BifrostNMS scaffolding used `Tortoise.generate_schemas()` during application startup. Once migrations are introduced, the cleanest development transition is to recreate the local PostgreSQL volume and run `./tools/db-bootstrap`.

From the host, with the Dev Container stopped:

```bash
docker volume ls | grep bifrostnms
```

Remove only the BifrostNMS PostgreSQL development volume you intentionally want to reset, then reopen the Dev Container and run the bootstrap command. Never use this approach for production data.

## Production rule

`BIFROSTNMS_AUTO_CREATE_SCHEMA` should remain false. Production startup must apply committed migrations as a deployment step before starting the API.

# TimescaleDB operations

## Supported version

Development and CI pin `timescale/timescaledb:2.29.0-pg17`. Supported production
deployments use PostgreSQL 17 with the TimescaleDB 2.29 compatibility line until
a reviewed dependency change updates all environments together. Do not use
`latest-pg17` or another floating tag for persistent deployments.

Migration `models.0005_enable_timescaledb` creates the extension. Later Stage 3
migrations own hypertables, indexes, compression, retention and continuous
aggregate objects. Application startup never creates them implicitly.

## Backup and restore

Back up the complete PostgreSQL cluster or database, not only hypertable chunks.
The backup must include ordinary relational tables, Timescale catalog state,
migration history and audit data. Store backups outside the database host and
encrypt them according to the installation's policy.

Use Timescale's documented `pg_dump`/`pg_restore` procedure, including
`timescaledb_pre_restore()` and `timescaledb_post_restore()` when required for
the selected versions. Restore into a compatible PostgreSQL/TimescaleDB image
and run `ANALYZE` as directed by the upstream procedure.

A backup is not considered usable until a scheduled restore drill proves:

- the database opens with the expected extension version;
- migration history is intact;
- authentication and realm data can be read;
- representative observation queries return expected counts; and
- the API and worker start against the restored database.

## Upgrades

PostgreSQL major, TimescaleDB extension and application schema upgrades are
separate compatibility events even when shipped in one container image.

For a TimescaleDB update within PostgreSQL 17:

1. Read the upstream release and compatibility notes.
2. Back up and complete a restore rehearsal.
3. Update the pinned tag in development and backend CI together.
4. Apply extension update steps in a reviewed migration when required.
5. Run the full migration/integration suite and representative query plans.
6. Roll through staging before production.

A PostgreSQL major upgrade requires an explicit `pg_upgrade` or dump/restore
plan and is never achieved by only changing the image tag. Preserve the old
volume and image until rollback or restore acceptance is complete.

## Monitoring

Operators should alert on storage exhaustion, failed backups, replication or
WAL problems, long transactions, migration failure and extension/version drift.
Timescale background job failures for compression, retention or continuous
aggregates become required signals when those policies are introduced.

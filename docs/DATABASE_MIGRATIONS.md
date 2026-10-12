# Versioned research databases

The API packages an Alembic migration history. Revision `0001_research_records` freezes the original five research tables independently of the current ORM models. New databases initialize through this history; existing databases must be upgraded explicitly before starting the API. Startup rejects an old/unknown revision or schema drift instead of silently creating missing tables.

## Local upgrade

Stop the API and workers, and make a [verified backup](BACKUP_RECOVERY.md). Then:

```sh
.venv/bin/python -m neuroresect_api.migrations status
# One-time adoption of the original, unversioned database:
.venv/bin/python -m neuroresect_api.migrations upgrade --adopt-legacy
# Subsequent releases:
.venv/bin/python -m neuroresect_api.migrations upgrade
```

Commands use `DATABASE_URL` or the local default; `--database-url` overrides it. Legacy adoption compares tables, columns/types/defaults, indexes and unique constraints with the frozen baseline before recording its revision. Partial or drifted schemas are refused. It preserves all research rows. No blind stamp or destructive downgrade command is exposed; recover a backup using the corresponding application release when rollback is needed.

SQLite migrations acquire an immediate write transaction; PostgreSQL migrations acquire a transaction-scoped advisory lock. Concurrent initialization is serialized, and revision updates share the migration transaction. The connection pattern follows the [Alembic programmatic migration recipe](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands). Schema upgrades should run with writers stopped, even when a migration itself is additive.

## Compose upgrade

Fresh Compose databases initialize automatically. For an existing PostgreSQL volume, stop API/worker/web, take your PostgreSQL backup, rebuild the images, and run the migration before restarting application services:

```sh
docker compose stop web api worker
docker compose build
docker compose run --rm api python -m neuroresect_api.migrations status
docker compose run --rm api python -m neuroresect_api.migrations upgrade --adopt-legacy
docker compose up -d --wait
```

Use `upgrade` without `--adopt-legacy` after the first adoption. These commands preserve volumes. The SQLite backup command cannot back up PostgreSQL; shared-lab PostgreSQL recovery remains a separately tested deployment requirement.

## Backup compatibility and development

The backup verifier supports both the frozen unversioned schema and known packaged revision schemas. Old snapshots remain verifiable and restorable; restored legacy databases require explicit adoption before API startup. A revision field accompanies new snapshot manifests. This does not rewrite old manifests or source snapshots.

Add a new immutable revision under `apps/api/neuroresect_api/migration_scripts/versions/` for each schema change. Never edit the frozen baseline or an already released migration. Test empty database creation, upgrade from the prior revision with records, rejection of incompatible schemas, backup/restore and PostgreSQL container startup. The packaged migration scripts must ship in the API wheel and container.

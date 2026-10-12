# PostgreSQL recovery for the Compose deployment

Run the commands from the repository root against the intended Compose project. They use the PostgreSQL client tools already inside the `postgres` service and a short-lived API container for schema validation. No host PostgreSQL client or password on the command line is needed. Build the matching API image first; the database must be at that image's schema revision.

## Snapshot and verify

```sh
python3 scripts/compose_backup.py backup --output data/backups/postgres-before-upgrade
python3 scripts/compose_backup.py verify data/backups/postgres-before-upgrade
```

The default source database/user are `neuroresect`; `backup --database` and `--user` select alternatives. The API image's configured `DATABASE_URL` must use the same server and credentials. Each output directory must be new. The command creates an owner-only custom-format dump and a manifest containing a SHA-256 checksum, size, schema revision, timestamp and client version. It checks the archive table of contents with `pg_restore --list`.

`pg_dump` provides a consistent database snapshot while ordinary writes continue. Stop API/worker submissions and wait for computations to finish when the snapshot must include those completed results. Do not run schema migrations during backup. The source schema check precedes the dump; restore checks the archived revision again. A checksum/TOC verification is **not** a substitute for a full restore drill.

The PostgreSQL [dump](https://www.postgresql.org/docs/17/app-pgdump.html) and [restore](https://www.postgresql.org/docs/17/app-pgrestore.html) tools supply the archive and transaction semantics. Roles/ACLs, Redis queues, downloaded datasets and external training artifacts are excluded. Store these separately, and retain the matching source revision, dependency locks and deployment configuration. Dumps contain research data; use trusted backups and your deployment's encrypted/offsite storage. Checksums provide corruption detection, not authenticity.

## Restore into a new database

```sh
python3 scripts/compose_backup.py restore data/backups/postgres-before-upgrade \
  --destination neuroresect_recovered
```

The role needs permission to create a database. The destination is a validated lowercase identifier and must not exist. `createdb` refuses existing databases; there is no drop, clean or overwrite option. Restore checks staged archive bytes, loads them in a single transaction, verifies the installed schema, then marks unfinished jobs `FAILED / BACKUP_INTERRUPTED`. Completed records remain unchanged. The original database and archive are untouched. If restoration or validation fails, the newly created database is retained for inspection and must not be activated.

The JSON report includes the revision, row counts, content hashes for each application table, and number of interrupted jobs. Compare it with an inspection from a quiescent source database:

```sh
docker compose run --rm --no-deps -T api python -m neuroresect_api.recovery_admin \
  --database-name neuroresect
```

Content hashes of restored jobs can differ when interrupted statuses were finalized. Other tables should match a source inspected at the snapshot point. Do not compare hashes against a source that continued accepting new work after the dump.

Before activating the recovered database, inspect its expected study records, stop existing API/worker/web services, and point both API and worker `DATABASE_URL` values to the recovered name through your Compose override. Start them together and check `/health`, saved scenario exports and experiment results. Avoid connecting new workers to a broker queue from the original database: use an isolated Redis database/namespace for the recovered deployment. Redis messages are transport; restored pending jobs stay failed until explicitly resubmitted with new idempotency keys. Keep the original database until the drill is accepted.

## Automated drill and remaining boundaries

Container CI first produces research results, then stops writers, creates a dump, restores to a fresh database and compares schema, counts and canonical per-table content hashes. It verifies that both the source and an existing restore destination survive attempted overwrite. `scripts/smoke_postgres_backup.py` is only for the disposable CI stack; it stops services and creates a new database.

This implements logical database recovery for the supplied PostgreSQL 17 Compose stack. It does not configure point-in-time recovery/WAL archiving, replication, offsite retention scheduling, encryption keys, organization roles or external artifact backup. A deployment must set and test its own recovery time and recovery point requirements.

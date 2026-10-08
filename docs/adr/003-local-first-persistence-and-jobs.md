# ADR 003: a local research workflow with a worker deployment path

Status: accepted.

The default developer experience is SQLite plus a bounded local job executor. PostgreSQL and Redis/Celery provide the container deployment path. SQLAlchemy keeps persistence behind repositories; the scientific package remains independent.

Jobs persist their state, stage, progress, result, and failure. Restarted local jobs cannot silently remain running forever. Scientific cache identity includes source matrix, region IDs, atlas, resection, threshold, and algorithm version. HTTP idempotency keys cannot substitute for input identity.

This is an anonymous, local research prototype. It is not configured for hosting confidential patient information on the public internet. OIDC, organization tenancy, encrypted asset management, and deployment-specific audit retention belong to a governed lab deployment. No patient data or generated research artifacts are committed by default.

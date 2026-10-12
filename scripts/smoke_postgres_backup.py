"""Restore a snapshot to a new database in the disposable CI Compose stack."""

from pathlib import Path
from uuid import uuid4

from compose_backup import backup, inspect_database, restore, run, verify


def main():
    # No writers while comparing before/after counts in this drill.
    run(["stop", "api", "worker"])
    try:
        before = inspect_database("neuroresect")
        bundle = Path("artifacts/postgres-recovery-drill")
        backup(bundle)
        verify(bundle)
        destination = "recovery_" + uuid4().hex
        report = restore(bundle, destination)
        assert report["row_counts"] == before["row_counts"]
        assert report["schema_revision"] == before["schema_revision"]
        assert report["table_sha256"] == before["table_sha256"]
        assert inspect_database("neuroresect") == before
        try:
            restore(bundle, destination)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Existing database restore was not rejected")
        assert inspect_database(destination)["row_counts"] == before["row_counts"]
        print(
            "PostgreSQL snapshot restored with matching schema/counts; source and existing destination preserved"
        )
    finally:
        run(["up", "-d", "--wait", "api", "worker"])


if __name__ == "__main__":
    main()

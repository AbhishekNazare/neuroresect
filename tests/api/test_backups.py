"""Recovery drills cover committed WAL records, corruption and interrupted work."""

import json
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from neuroresect_api.backups import backup, restore, verify
from neuroresect_api.config import Settings
from neuroresect_api.database import Database
from neuroresect_api.main import create_app
from neuroresect_api.repository import Repository


@pytest.fixture
def research(tmp_path):
    path = tmp_path / "live.db"
    url = f"sqlite:///{path}"
    database = Database(url)
    database.initialize()
    repository = Repository(database)
    scenario = repository.create_scenario(
        {
            "patient_id": "DEMO-001",
            "atlas_id": "demo-64",
            "label": "Recovery drill",
            "regions": [{"region_id": 0, "fraction_removed": 0.5}],
            "method": "weighted",
        }
    )
    repository.save_result(
        scenario["id"],
        "simulation",
        {"provenance": {"scenario_id": scenario["id"]}, "connectivity_loss": 0.12},
    )
    repository.save_import(
        {"id": "RESEARCH-001", "label": "Research"},
        {"patient_id": "RESEARCH-001", "atlas_id": "tiny", "synthetic": False},
    )
    repository.save_experiment({"id": "EXP-drill", "models": {"A": {"metrics": {"roc_auc": 0.5}}}})
    queued, _ = repository.create_job("simulation", scenario["id"], {}, "local", "queued")
    running, _ = repository.create_job("simulation", scenario["id"], {}, "celery", "running")
    repository.claim_job(running["id"])
    complete, _ = repository.create_job("simulation", scenario["id"], {}, "local", "complete")
    repository.claim_job(complete["id"])
    repository.succeed(complete["id"], {"connectivity_loss": 0.12})
    yield path, url, repository, scenario, queued, running, complete
    database.close()


def test_live_wal_snapshot_and_restore_preserve_research_and_fail_unfinished_jobs(
    research, tmp_path
):
    path, url, repository, scenario, queued, running, complete = research
    bundle = tmp_path / "snapshot"
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("UPDATE scenarios SET patient_id='UNCOMMITTED'")
        manifest = backup(url, bundle)
        writer.rollback()
    assert manifest["row_counts"] == {
        "experiments": 1,
        "imported_connectomes": 1,
        "jobs": 3,
        "scenario_results": 1,
        "scenarios": 1,
    }
    assert manifest["job_status_counts"] == {"QUEUED": 1, "RUNNING": 1, "SUCCEEDED": 1}
    assert verify(bundle) == manifest
    assert str(path) not in json.dumps(manifest)
    destination = tmp_path / "restored.db"
    report = restore(bundle, destination)
    assert report["interrupted_jobs"] == 2
    assert destination.stat().st_mode & 0o777 == 0o600
    assert verify(bundle) == manifest  # Restore never edits the original snapshot.
    assert repository.job(queued["id"])["status"] == "QUEUED"
    assert repository.job(running["id"])["status"] == "RUNNING"
    restored_db = Database(f"sqlite:///{destination}")
    restored_repo = Repository(restored_db)
    assert restored_repo.imports() == repository.imports()
    with restored_db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT patient_id FROM scenarios").scalar() == "DEMO-001"
    restored_db.close()
    with TestClient(create_app(Settings(database_url=f"sqlite:///{destination}"))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/scenarios").json()[0]["label"] == "Recovery drill"
        assert (
            client.get(f"/api/v1/scenarios/{scenario['id']}/simulation").json()["connectivity_loss"]
            == 0.12
        )
        assert (
            client.get("/api/v1/experiments/EXP-drill").json()["models"]["A"]["metrics"]["roc_auc"]
            == 0.5
        )
        for job in (queued, running):
            restored = client.get(f"/api/v1/jobs/{job['id']}").json()
            assert restored["status"] == "FAILED"
            assert restored["error"]["code"] == "BACKUP_INTERRUPTED"
        assert client.get(f"/api/v1/jobs/{complete['id']}").json()["status"] == "SUCCEEDED"


def test_corrupt_or_incomplete_backup_cannot_be_restored(research, tmp_path):
    bundle = tmp_path / "snapshot"
    backup(research[1], bundle)
    snapshot = bundle / "database.sqlite3"
    snapshot.write_bytes(snapshot.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum or size"):
        restore(bundle, tmp_path / "restored.db")
    assert not (tmp_path / "restored.db").exists()
    (bundle / "manifest.json").unlink()
    with pytest.raises(FileNotFoundError):
        verify(bundle)


@pytest.mark.parametrize("collision", ["database", "symlink", "sidecar"])
def test_restore_never_overwrites_existing_files(research, tmp_path, collision):
    bundle = tmp_path / "snapshot"
    backup(research[1], bundle)
    destination = tmp_path / "restored.db"
    protected = tmp_path / "protected"
    protected.write_text("preserve me")
    if collision == "database":
        destination.write_text("preserve me")
    elif collision == "symlink":
        destination.symlink_to(protected)
    else:
        (tmp_path / "restored.db-wal").write_text("preserve me")
    with pytest.raises(FileExistsError):
        restore(bundle, destination)
    assert protected.read_text() == "preserve me"


def test_backup_rejects_missing_source_and_schema_drift_and_existing_output(research, tmp_path):
    output = tmp_path / "snapshot"
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        backup(f"sqlite:///{missing}", output)
    assert not missing.exists()
    assert not output.exists()
    output.mkdir()
    (output / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        backup(research[1], output)
    assert (output / "keep").read_text() == "keep"
    with closing(sqlite3.connect(research[0])) as connection:
        connection.execute("CREATE TABLE unsupported (value TEXT)")
    with pytest.raises(ValueError, match="schema differs"):
        backup(research[1], tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize(
    "url", ["sqlite:///:memory:", "postgresql://localhost/research", "sqlite:///x?mode=ro"]
)
def test_backup_rejects_unsupported_database_urls(url, tmp_path):
    with pytest.raises(ValueError, match="file-backed SQLite"):
        backup(url, tmp_path / "snapshot")


def test_backup_timeout_removes_incomplete_bundle(research, tmp_path, monkeypatch):
    from neuroresect_api import backups

    ticks = iter([0, 2])
    monkeypatch.setattr(backups.time, "monotonic", lambda: next(ticks))
    output = tmp_path / "timeout"
    with pytest.raises(TimeoutError, match="deadline"):
        backup(research[1], output, timeout=1)
    assert not output.exists()


def test_verify_rejects_changed_manifest_and_sidecars(research, tmp_path):
    bundle = tmp_path / "snapshot"
    manifest = backup(research[1], bundle)
    manifest["row_counts"]["scenarios"] = 200
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inventory"):
        verify(bundle)
    (bundle / "database.sqlite3-wal").touch()
    with pytest.raises(ValueError, match="sidecars"):
        verify(bundle)


def test_cli_reports_failure_without_creating_missing_database(tmp_path):
    import subprocess
    import sys

    missing = tmp_path / "missing.db"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "neuroresect_api.backups",
            "backup",
            "--database-url",
            f"sqlite:///{missing}",
            "--output",
            str(tmp_path / "snapshot"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Backup operation failed" in result.stderr
    assert "Traceback" not in result.stderr
    assert not missing.exists()

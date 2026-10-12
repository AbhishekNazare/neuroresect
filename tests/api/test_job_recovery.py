from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import Mock

import pytest
from neuroresect_api.config import Settings
from neuroresect_api.database import Database, JobRecord
from neuroresect_api.jobs import JobDispatcher, JobRunner
from neuroresect_api.repository import Repository, utcnow
from neuroresect_api.services import ResearchService
from sqlalchemy import update


@pytest.fixture
def repository(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    database.initialize()
    yield Repository(database)
    database.close()


def enqueue(repository, executor="celery"):
    return repository.create_job("simulation", "SCN-fixture", {}, executor, None)[0]["id"]


def age(repository, job_id, **values):
    with repository.database.sessions.begin() as session:
        session.execute(update(JobRecord).where(JobRecord.id == job_id).values(**values))


def test_committed_queue_survives_broker_failure_and_dispatcher_restart(repository):
    settings = Settings(job_executor="celery")
    first = JobDispatcher(settings, repository, JobRunner(repository, ResearchService(repository)))
    first.celery = Mock()
    first.celery.send_task.side_effect = RuntimeError("private broker address")
    job = first.submit("simulation", "SCN-fixture", {}, "stable-key")
    assert job["status"] == "QUEUED"
    assert job["stage"] == "WAITING_FOR_BROKER"
    assert job["dispatch_attempts"] == 1
    assert "private broker" not in str(job)
    first.shutdown()
    age(repository, job["id"], next_dispatch_at=utcnow() - timedelta(seconds=1))
    restarted = JobDispatcher(
        settings, repository, JobRunner(repository, ResearchService(repository))
    )
    restarted.celery = Mock()
    try:
        restarted.recover_once()
        assert restarted.celery.send_task.call_count == 1
        assert repository.job(job["id"])["stage"] == "WAITING_FOR_WORKER"
        assert repository.job(job["id"])["dispatch_attempts"] == 2
        restarted.recover_once()
        assert restarted.celery.send_task.call_count == 1
        replay = restarted.submit("simulation", "SCN-fixture", {}, "stable-key")
        assert replay["id"] == job["id"]
    finally:
        restarted.shutdown()


def test_delivery_reservation_and_execution_claim_are_atomic(repository):
    job_id = enqueue(repository)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: repository.reserve_delivery(job_id, 30), range(8))) == 1
        claims = list(pool.map(lambda _: repository.claim_job(job_id), range(8)))
    assert sum(claim is not None for claim in claims) == 1
    assert repository.job(job_id)["dispatch_attempts"] == 1


def test_expiry_fences_late_results_and_preserves_live_work(repository):
    expired = enqueue(repository)
    live = enqueue(repository)
    timed_out = enqueue(repository)
    queued = enqueue(repository)
    local = enqueue(repository, "local")
    for job_id in (expired, live, timed_out, local):
        repository.claim_job(job_id)
    old = utcnow() - timedelta(hours=2)
    age(repository, expired, heartbeat_at=old)
    age(repository, timed_out, started_at=old)
    age(repository, queued, created_at=old)
    age(repository, local, heartbeat_at=old)
    assert repository.expire_jobs(90, 1200, 3600) == 3
    assert repository.job(live)["status"] == "RUNNING"
    assert repository.job(local)["status"] == "RUNNING"
    assert repository.job(queued)["error"]["code"] == "QUEUE_WAIT_EXPIRED"
    assert repository.heartbeat(expired) is False
    repository.progress(expired, 90, "LATE_PROGRESS")
    repository.save_job_result(expired, "simulation", {"late": True})
    repository.succeed(expired, {"late": True})
    assert repository.result("SCN-fixture", "simulation") is None
    assert repository.job(expired)["error"]["code"] == "WORKER_LEASE_EXPIRED"
    assert repository.claim_job(expired) is None
    assert repository.due_deliveries() == []


def test_runner_heartbeats_during_long_computation(repository, monkeypatch):
    job_id = enqueue(repository)
    settings = Settings(job_heartbeat_seconds=1, job_lease_seconds=3)
    runner = JobRunner(repository, ResearchService(repository), settings)
    observed = Event()
    original = repository.heartbeat

    def heartbeat(identifier):
        result = original(identifier)
        observed.set()
        return result

    monkeypatch.setattr(repository, "heartbeat", heartbeat)

    def compute(*_):
        assert observed.wait(5)
        return {"connectivity_loss": 0.1}

    monkeypatch.setattr(runner, "compute", compute)
    runner.execute(job_id)
    assert repository.job(job_id)["status"] == "SUCCEEDED"
    runner.execute(job_id)  # A duplicate delivery cannot replace the result.
    assert repository.job(job_id)["result"] == {"connectivity_loss": 0.1}


def test_recovery_loop_runs_and_stops(repository, monkeypatch):
    dispatcher = JobDispatcher(
        Settings(job_executor="celery"),
        repository,
        JobRunner(repository, ResearchService(repository)),
    )
    dispatcher.celery = Mock()
    observed = Event()
    monkeypatch.setattr(dispatcher, "recover_once", observed.set)
    dispatcher.start()
    assert observed.wait(3)
    dispatcher.shutdown()
    assert not dispatcher.recovery_thread.is_alive()

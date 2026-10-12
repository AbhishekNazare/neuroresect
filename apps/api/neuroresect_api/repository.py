"""Atomic job transitions and durable research records."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from .database import (
    Database,
    ExperimentRecord,
    ImportRecord,
    JobRecord,
    ResultRecord,
    ScenarioRecord,
)
from .errors import APIError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def job_payload(record: JobRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "kind": record.kind,
        "scenario_id": record.scenario_id,
        "status": record.status,
        "progress": record.progress,
        "stage": record.stage,
        "dispatch_attempts": record.dispatch_attempts,
        "result": record.result,
        "error": record.error,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = {**payload, "id": new_id("SCN"), "created_at": utcnow().isoformat()}
        with self.database.sessions.begin() as session:
            session.add(
                ScenarioRecord(id=result["id"], patient_id=result["patient_id"], payload=result)
            )
        return result

    def scenario(self, scenario_id: str) -> dict[str, Any]:
        with self.database.sessions() as session:
            record = session.get(ScenarioRecord, scenario_id)
            if record is None:
                raise APIError(404, "SCENARIO_NOT_FOUND", "Scenario does not exist.")
            return record.payload

    def scenarios(self, patient_id: str | None) -> list[dict[str, Any]]:
        query = select(ScenarioRecord)
        if patient_id is not None:
            query = query.where(ScenarioRecord.patient_id == patient_id)
        with self.database.sessions() as session:
            return sorted(
                [row.payload for row in session.scalars(query)],
                key=lambda item: item["created_at"],
                reverse=True,
            )

    def imports(self) -> list[dict[str, Any]]:
        with self.database.sessions() as session:
            return [
                {"patient": row.patient, "connectome": row.connectome}
                for row in session.scalars(select(ImportRecord))
            ]

    def imported_connectome(self, patient_id: str, atlas_id: str) -> dict[str, Any] | None:
        with self.database.sessions() as session:
            row = session.get(ImportRecord, (patient_id, atlas_id))
            return row.connectome if row else None

    def save_import(self, patient: dict[str, Any], connectome: dict[str, Any]) -> None:
        try:
            with self.database.sessions.begin() as session:
                session.add(
                    ImportRecord(
                        patient_id=patient["id"],
                        atlas_id=connectome["atlas_id"],
                        patient=patient,
                        connectome=connectome,
                    )
                )
        except IntegrityError as exc:
            raise APIError(
                409, "CONNECTOME_EXISTS", "This patient/atlas pair already exists."
            ) from exc

    def result(self, scenario_id: str, kind: str) -> dict[str, Any] | None:
        with self.database.sessions() as session:
            row = session.get(ResultRecord, (scenario_id, kind))
            return row.payload if row else None

    def save_result(self, scenario_id: str, kind: str, payload: dict[str, Any]) -> None:
        # Independent jobs may finish simultaneously. Retry an insert conflict as an update.
        for attempt in range(2):
            try:
                with self.database.sessions.begin() as session:
                    session.merge(ResultRecord(scenario_id=scenario_id, kind=kind, payload=payload))
                return
            except IntegrityError:
                if attempt:
                    raise

    def experiments(self) -> list[dict[str, Any]]:
        with self.database.sessions() as session:
            return [row.payload for row in session.scalars(select(ExperimentRecord))]

    def experiment(self, experiment_id: str) -> dict[str, Any]:
        with self.database.sessions() as session:
            row = session.get(ExperimentRecord, experiment_id)
            if row is None:
                raise APIError(404, "EXPERIMENT_NOT_FOUND", "Experiment does not exist.")
            return row.payload

    def save_experiment(self, result: dict[str, Any]) -> None:
        with self.database.sessions.begin() as session:
            session.merge(ExperimentRecord(id=result["id"], payload=result))

    def create_job(
        self,
        kind: str,
        scenario_id: str | None,
        payload: dict[str, Any],
        executor: str,
        key: str | None,
    ) -> tuple[dict[str, Any], bool]:
        fingerprint = stable_hash(payload)
        scope = stable_hash([kind, scenario_id, key]) if key else None
        now = utcnow()
        record = JobRecord(
            id=new_id("JOB"),
            kind=kind,
            scenario_id=scenario_id,
            executor=executor,
            status="QUEUED",
            progress=0,
            stage="QUEUED",
            payload=payload,
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
            idempotency_scope=scope,
            request_hash=fingerprint,
        )
        try:
            with self.database.sessions.begin() as session:
                session.add(record)
            return job_payload(record), True
        except IntegrityError:
            if scope is None:
                raise
            with self.database.sessions() as session:
                existing = session.scalar(
                    select(JobRecord).where(JobRecord.idempotency_scope == scope)
                )
                if existing is None:
                    raise
                if existing.request_hash != fingerprint:
                    raise APIError(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This idempotency key was used with different request parameters.",
                    )
                return job_payload(existing), False

    def job(self, job_id: str) -> dict[str, Any]:
        with self.database.sessions() as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise APIError(404, "JOB_NOT_FOUND", "Job does not exist.")
            return job_payload(row)

    def claim_job(self, job_id: str) -> dict[str, Any] | None:
        with self.database.sessions.begin() as session:
            result = session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "QUEUED")
                .values(
                    status="RUNNING",
                    progress=10,
                    stage="LOADING_INPUTS",
                    updated_at=utcnow(),
                    started_at=utcnow(),
                    heartbeat_at=utcnow(),
                )
            )
            if cast(CursorResult, result).rowcount != 1:
                return None
            row = session.get(JobRecord, job_id)
            assert row is not None
            return {"kind": row.kind, "scenario_id": row.scenario_id, "payload": row.payload}

    def progress(self, job_id: str, percent: int, stage: str) -> None:
        with self.database.sessions.begin() as session:
            session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "RUNNING")
                .values(progress=percent, stage=stage, updated_at=utcnow())
            )

    def succeed(self, job_id: str, result: dict[str, Any]) -> None:
        stable_hash(result)  # Reject nonfinite/unserializable scientific output before persistence.
        with self.database.sessions.begin() as session:
            transition = session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "RUNNING")
                .values(
                    status="SUCCEEDED",
                    progress=100,
                    stage="COMPLETE",
                    result=result,
                    error=None,
                    updated_at=utcnow(),
                )
            )
            if cast(CursorResult, transition).rowcount != 1:
                return
            job = session.get(JobRecord, job_id)
            assert job is not None
            if job.kind == "experiment":
                session.merge(ExperimentRecord(id=result["id"], payload=result))
            else:
                session.merge(
                    ResultRecord(scenario_id=job.scenario_id, kind=job.kind, payload=result)
                )

    def fail(self, job_id: str, code: str, message: str) -> None:
        with self.database.sessions.begin() as session:
            session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status.in_(["QUEUED", "RUNNING"]))
                .values(
                    status="FAILED",
                    stage="FAILED",
                    updated_at=utcnow(),
                    error={"code": code, "message": message, "details": {}},
                )
            )

    def recover_local_jobs(self) -> int:
        with self.database.sessions.begin() as session:
            result = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.executor == "local",
                    JobRecord.status.in_(["QUEUED", "RUNNING"]),
                )
                .values(
                    status="FAILED",
                    stage="INTERRUPTED",
                    updated_at=utcnow(),
                    error={
                        "code": "JOB_INTERRUPTED",
                        "message": "The local executor restarted. Submit a new job to retry.",
                        "details": {},
                    },
                )
            )
            return cast(CursorResult, result).rowcount

    def heartbeat(self, job_id: str) -> bool:
        with self.database.sessions.begin() as session:
            result = session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "RUNNING")
                .values(heartbeat_at=utcnow())
            )
            return cast(CursorResult, result).rowcount == 1

    def due_deliveries(self, limit: int = 20) -> list[str]:
        with self.database.sessions() as session:
            return list(
                session.scalars(
                    select(JobRecord.id)
                    .where(
                        JobRecord.executor == "celery",
                        JobRecord.status == "QUEUED",
                        or_(
                            JobRecord.next_dispatch_at.is_(None),
                            JobRecord.next_dispatch_at <= utcnow(),
                        ),
                    )
                    .order_by(JobRecord.created_at)
                    .limit(limit)
                )
            )

    def reserve_delivery(self, job_id: str, retry_seconds: int) -> bool:
        now = utcnow()
        with self.database.sessions.begin() as session:
            result = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.executor == "celery",
                    JobRecord.status == "QUEUED",
                    or_(JobRecord.next_dispatch_at.is_(None), JobRecord.next_dispatch_at <= now),
                )
                .values(
                    next_dispatch_at=now + timedelta(seconds=retry_seconds),
                    dispatch_attempts=JobRecord.dispatch_attempts + 1,
                )
            )
            return cast(CursorResult, result).rowcount == 1

    def delivery_stage(self, job_id: str, stage: str) -> None:
        with self.database.sessions.begin() as session:
            session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "QUEUED")
                .values(stage=stage, updated_at=utcnow())
            )

    def expire_jobs(
        self, lease_seconds: int, max_runtime_seconds: int, queue_timeout_seconds: int
    ) -> int:
        now = utcnow()
        stale = or_(
            func.coalesce(JobRecord.heartbeat_at, JobRecord.updated_at)
            < now - timedelta(seconds=lease_seconds),
            func.coalesce(JobRecord.started_at, JobRecord.created_at)
            < now - timedelta(seconds=max_runtime_seconds),
        )
        with self.database.sessions.begin() as session:
            running = session.execute(
                update(JobRecord)
                .where(JobRecord.executor == "celery", JobRecord.status == "RUNNING", stale)
                .values(
                    status="FAILED",
                    stage="INTERRUPTED",
                    updated_at=now,
                    error={
                        "code": "WORKER_LEASE_EXPIRED",
                        "message": "Worker heartbeat or runtime limit expired. Submit a new job with a new idempotency key.",
                        "details": {},
                    },
                )
            )
            queued = session.execute(
                update(JobRecord)
                .where(
                    JobRecord.executor == "celery",
                    JobRecord.status == "QUEUED",
                    JobRecord.created_at < now - timedelta(seconds=queue_timeout_seconds),
                )
                .values(
                    status="FAILED",
                    stage="QUEUE_EXPIRED",
                    updated_at=now,
                    error={
                        "code": "QUEUE_WAIT_EXPIRED",
                        "message": "No worker claimed the job within its queue deadline. Submit a new job.",
                        "details": {},
                    },
                )
            )
            return cast(CursorResult, running).rowcount + cast(CursorResult, queued).rowcount

    def save_job_result(self, job_id: str, kind: str, payload: dict[str, Any]) -> None:
        # The guarded UPDATE locks this job against expiry until the result transaction commits.
        stable_hash(payload)
        with self.database.sessions.begin() as session:
            transition = session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id, JobRecord.status == "RUNNING")
                .values(updated_at=JobRecord.updated_at)
            )
            if cast(CursorResult, transition).rowcount != 1:
                return
            job = session.get(JobRecord, job_id)
            assert job is not None
            session.merge(ResultRecord(scenario_id=job.scenario_id, kind=kind, payload=payload))

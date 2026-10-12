"""Explicit environment configuration shared by API and workers."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./data/neuroresect.db"
    job_executor: str = "local"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    max_request_bytes: int = 8 * 1024 * 1024
    local_workers: int = 2
    job_heartbeat_seconds: int = 15
    job_lease_seconds: int = 90
    job_max_runtime_seconds: int = 1200
    job_queue_timeout_seconds: int = 3600
    job_dispatch_retry_seconds: int = 30
    job_recovery_interval_seconds: int = 10

    def __post_init__(self) -> None:
        if self.job_executor not in {"local", "celery"}:
            raise ValueError("JOB_EXECUTOR must be local or celery")
        if self.max_request_bytes < 1024 or not 1 <= self.local_workers <= 8:
            raise ValueError("Invalid request limit or local worker count")

        if not (
            1
            <= self.job_heartbeat_seconds * 3
            <= self.job_lease_seconds
            <= self.job_max_runtime_seconds
        ):
            raise ValueError(
                "Heartbeat, lease and runtime limits must satisfy heartbeat*3 <= lease <= runtime"
            )
        if (
            min(
                self.job_queue_timeout_seconds,
                self.job_dispatch_retry_seconds,
                self.job_recovery_interval_seconds,
            )
            < 1
        ):
            raise ValueError("Job queue and recovery intervals must be positive")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            job_executor=os.getenv("JOB_EXECUTOR", cls.job_executor),
            celery_broker_url=os.getenv("CELERY_BROKER_URL", cls.celery_broker_url),
            celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", cls.celery_result_backend),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
                if origin.strip()
            ),
            max_request_bytes=int(os.getenv("MAX_REQUEST_BYTES", str(cls.max_request_bytes))),
            local_workers=int(os.getenv("LOCAL_WORKERS", str(cls.local_workers))),
            **{
                name: int(os.getenv(name.upper(), str(getattr(cls, name))))
                for name in (
                    "job_heartbeat_seconds",
                    "job_lease_seconds",
                    "job_max_runtime_seconds",
                    "job_queue_timeout_seconds",
                    "job_dispatch_retry_seconds",
                    "job_recovery_interval_seconds",
                )
            },
        )

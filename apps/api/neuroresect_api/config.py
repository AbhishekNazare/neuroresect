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

    def __post_init__(self) -> None:
        if self.job_executor not in {"local", "celery"}:
            raise ValueError("JOB_EXECUTOR must be local or celery")
        if self.max_request_bytes < 1024 or not 1 <= self.local_workers <= 8:
            raise ValueError("Invalid request limit or local worker count")

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
        )

"""Run: celery -A workers.celery_app:celery_app worker --loglevel=info."""

from celery import Celery
from celery.signals import task_failure
from neuroresect_api.config import Settings
from neuroresect_api.database import Database
from neuroresect_api.jobs import JobRunner
from neuroresect_api.repository import Repository
from neuroresect_api.services import ResearchService

settings = Settings.from_env()
celery_app = Celery(
    "neuroresect", broker=settings.celery_broker_url, backend=settings.celery_result_backend
)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True, worker_prefetch_multiplier=1,
    task_acks_late=True, task_reject_on_worker_lost=False,
    task_time_limit=1200,
)


@task_failure.connect
def record_worker_failure(sender=None, args=None, **kwargs) -> None:
    """Record failures outside JobRunner, including child-worker termination."""
    if getattr(sender, "name", None) != "neuroresect.execute_job" or not args:
        return
    database = Database(settings.database_url)
    try:
        Repository(database).fail(
            args[0], "WORKER_FAILED", "Worker execution was interrupted. Submit a new job."
        )
    finally:
        database.close()


@celery_app.task(name="neuroresect.execute_job")
def execute_job(job_id: str) -> None:
    database = Database(settings.database_url)
    repository = Repository(database)
    try:
        JobRunner(repository, ResearchService(repository)).execute(job_id)
    finally:
        database.close()

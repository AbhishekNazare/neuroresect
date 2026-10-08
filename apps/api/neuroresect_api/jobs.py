"""Persistent job runner used unchanged by local threads and Celery workers."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .config import Settings
from .errors import APIError
from .repository import Repository, stable_hash, utcnow
from .services import ResearchService

logger = logging.getLogger("neuroresect.jobs")


class JobRunner:
    def __init__(self, repository: Repository, service: ResearchService) -> None:
        self.repository = repository
        self.service = service

    def execute(self, job_id: str) -> None:
        job = self.repository.claim_job(job_id)
        if job is None:
            return
        try:
            result = self.compute(job_id, job)
            self.repository.succeed(job_id, result)
        except APIError as exc:
            self.repository.fail(job_id, exc.code, exc.message)
        except ValueError as exc:
            self.repository.fail(job_id, "INVALID_SCIENTIFIC_INPUT", str(exc)[:500])
        except Exception as exc:
            # Logs contain identifiers and exception type, never connectome or request data.
            logger.error("job_failed job_id=%s error_type=%s", job_id, type(exc).__name__)
            self.repository.fail(
                job_id, "JOB_FAILED", "Computation failed. Review worker logs and submit a new job."
            )

    def compute(self, job_id: str, job: dict[str, Any]) -> dict[str, Any]:
        kind = job["kind"]
        if kind == "experiment":
            from neurocore.experiments import run_experiment

            self.repository.progress(job_id, 20, "PATIENT_SEPARATED_VALIDATION")
            return run_experiment(job["payload"])

        from neurocore.simulation import simulate

        scenario = self.repository.scenario(job["scenario_id"])
        connectome = self.service.connectome(scenario["patient_id"], scenario["atlas_id"])
        regions = scenario["regions"]
        method = scenario["method"]
        if kind == "simulation":
            self.repository.progress(job_id, 35, "COMPUTING_GRAPH_METRICS")
            result = simulate(connectome, regions, method=method)
        elif kind == "prediction":
            from neurocore.experiments import predict_scenario

            simulation = self.repository.result(scenario["id"], "simulation")
            if simulation is None:
                self.repository.progress(job_id, 20, "COMPUTING_GRAPH_METRICS")
                simulation = simulate(connectome, regions, method=method)
                simulation = self.attach_provenance(simulation, scenario, connectome)
                self.repository.save_result(scenario["id"], "simulation", simulation)
            self.repository.progress(job_id, 40, "BOOTSTRAP_MODEL_REFITS")
            result = predict_scenario(connectome, regions, simulation)
        elif kind == "sensitivity":
            from neurocore.analysis import sensitivity

            self.repository.progress(job_id, 30, "PERTURBING_RESECTION")
            result = sensitivity(connectome, regions, method=method)
        elif kind == "counterfactuals":
            from neurocore.analysis import counterfactuals

            self.repository.progress(job_id, 30, "SEARCHING_CONSTRAINED_ALTERNATIVES")
            result = counterfactuals(connectome, regions, job["payload"])
        else:
            raise ValueError("Unknown job operation")
        self.repository.progress(job_id, 90, "SAVING_RESEARCH_OUTPUT")
        return self.attach_provenance(result, scenario, connectome)

    @staticmethod
    def attach_provenance(
        result: dict[str, Any], scenario: dict[str, Any], connectome: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **result,
            "provenance": {
                **result.get("provenance", {}),
                "scenario_id": scenario["id"],
                "patient_id": scenario["patient_id"],
                "dataset_id": connectome["dataset_id"],
                "atlas_id": scenario["atlas_id"],
                "synthetic": connectome["synthetic"],
                "resection": scenario["regions"],
                "scenario_method": scenario["method"],
                "connectome_sha256": stable_hash(connectome),
                "computed_at": utcnow().isoformat(),
                "research_only": True,
            },
        }


class JobDispatcher:
    def __init__(self, settings: Settings, repository: Repository, runner: JobRunner) -> None:
        self.settings = settings
        self.repository = repository
        self.runner = runner
        self.pool = (
            ThreadPoolExecutor(max_workers=settings.local_workers, thread_name_prefix="neuroresect")
            if settings.job_executor == "local"
            else None
        )
        self.celery = None
        if settings.job_executor == "celery":
            from celery import Celery

            self.celery = Celery(
                "neuroresect", broker=settings.celery_broker_url,
                backend=settings.celery_result_backend,
            )
            self.celery.conf.update(
                task_serializer="json", accept_content=["json"], result_serializer="json",
                broker_connection_timeout=3, task_publish_retry=False,
            )

    def submit(
        self, kind: str, scenario_id: str | None, payload: dict[str, Any], key: str | None
    ) -> dict[str, Any]:
        job, created = self.repository.create_job(
            kind, scenario_id, payload, self.settings.job_executor, key
        )
        if created:
            try:
                if self.pool is not None:
                    self.pool.submit(self.runner.execute, job["id"])
                else:
                    self.celery.send_task("neuroresect.execute_job", args=[job["id"]])
            except Exception:
                self.repository.fail(
                    job["id"], "DISPATCH_FAILED",
                    "The worker queue is unavailable. Submit a new job to retry.",
                )
                return self.repository.job(job["id"])
        return job

    def shutdown(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=False)
        if self.celery is not None:
            self.celery.close()

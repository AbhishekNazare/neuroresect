"""Versioned research endpoints; long computations always produce persisted jobs."""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from .errors import APIError
from .schemas import (
    ConnectomeImport,
    Constraints,
    ExperimentCreate,
    Identifier,
    ScenarioCreate,
)

router = APIRouter(prefix="/api/v1")
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$"),
]


@router.get("/patients", tags=["catalog"])
def patients(request: Request):
    return request.app.state.service.patients()


@router.get("/patients/{patient_id}", tags=["catalog"])
def patient(request: Request, patient_id: Identifier):
    return request.app.state.service.patient(patient_id)


@router.get("/atlases", tags=["catalog"])
def atlases(request: Request):
    return request.app.state.service.atlases()


@router.get("/patients/{patient_id}/connectome", tags=["catalog"])
def connectome(
    request: Request,
    patient_id: Identifier,
    atlas_id: Annotated[Identifier, Query()] = "demo-64",
    include_matrix: bool = False,
):
    result = request.app.state.service.connectome(patient_id, atlas_id)
    return result if include_matrix else {key: value for key, value in result.items() if key != "matrix"}


@router.get("/scenarios", tags=["scenarios"])
def scenarios(request: Request, patient_id: Annotated[Identifier | None, Query()] = None):
    if patient_id is not None:
        request.app.state.service.patient(patient_id)
    return request.app.state.repository.scenarios(patient_id)


@router.post("/scenarios", status_code=201, tags=["scenarios"])
def create_scenario(request: Request, body: ScenarioCreate):
    return request.app.state.service.create_scenario(body)


def submit_scenario_job(request: Request, scenario_id: str, kind: str, key: str | None, payload=None):
    request.app.state.repository.scenario(scenario_id)
    return request.app.state.dispatcher.submit(kind, scenario_id, payload or {}, key)


@router.post("/scenarios/{scenario_id}/simulate", status_code=202, tags=["jobs"])
def simulate(request: Request, scenario_id: Identifier, idempotency_key: IdempotencyKey = None):
    return submit_scenario_job(request, scenario_id, "simulation", idempotency_key)


@router.get("/scenarios/{scenario_id}/simulation", tags=["scenarios"])
def simulation(request: Request, scenario_id: Identifier):
    request.app.state.repository.scenario(scenario_id)
    result = request.app.state.repository.result(scenario_id, "simulation")
    if result is None:
        raise APIError(404, "SIMULATION_NOT_FOUND", "No completed simulation exists for this scenario.")
    return result


@router.post("/scenarios/{scenario_id}/predict", status_code=202, tags=["jobs"])
def predict(request: Request, scenario_id: Identifier, idempotency_key: IdempotencyKey = None):
    scenario = request.app.state.repository.scenario(scenario_id)
    if scenario["method"] != "weighted":
        raise APIError(
            422, "MODEL_INCOMPATIBLE",
            "The available outcome model supports weighted resection scenarios only.",
        )
    if request.app.state.repository.imported_connectome(scenario["patient_id"], scenario["atlas_id"]):
        raise APIError(
            422, "MODEL_INCOMPATIBLE",
            "The available outcome model is trained on synthetic demo data and cannot score imports.",
        )
    return submit_scenario_job(request, scenario_id, "prediction", idempotency_key)


@router.post("/scenarios/{scenario_id}/sensitivity", status_code=202, tags=["jobs"])
def sensitivity(request: Request, scenario_id: Identifier, idempotency_key: IdempotencyKey = None):
    return submit_scenario_job(request, scenario_id, "sensitivity", idempotency_key)


@router.post("/scenarios/{scenario_id}/counterfactuals", status_code=202, tags=["jobs"])
def counterfactuals(
    request: Request,
    scenario_id: Identifier,
    body: Constraints,
    idempotency_key: IdempotencyKey = None,
):
    scenario = request.app.state.repository.scenario(scenario_id)
    if scenario["method"] != "weighted":
        raise APIError(
            422, "UNSUPPORTED_RESECTION_METHOD",
            "Counterfactual search currently supports weighted resection scenarios only.",
        )
    connectome = request.app.state.service.connectome(scenario["patient_id"], scenario["atlas_id"])
    request.app.state.service.validate_region_ids(connectome, body.protected_regions)
    return submit_scenario_job(request, scenario_id, "counterfactuals", idempotency_key, body.model_dump())


@router.get("/scenarios/{scenario_id}/export", tags=["exports"])
def export_scenario(request: Request, scenario_id: Identifier):
    result = request.app.state.service.scenario_export(scenario_id)
    return JSONResponse(
        result,
        headers={"Content-Disposition": f'attachment; filename="{scenario_id}.json"'},
    )


@router.get("/jobs/{job_id}", tags=["jobs"])
def job(request: Request, job_id: Identifier):
    return request.app.state.repository.job(job_id)


@router.get("/experiments", tags=["experiments"])
def experiments(request: Request):
    return request.app.state.repository.experiments()


@router.post("/experiments", status_code=202, tags=["experiments"])
def create_experiment(request: Request, body: ExperimentCreate, idempotency_key: IdempotencyKey = None):
    from neurocore.demo import list_atlases

    if body.atlas_id not in {atlas["id"] for atlas in list_atlases()}:
        raise APIError(422, "ATLAS_NOT_SUPPORTED", "Experiments currently require a synthetic demo atlas.")
    return request.app.state.dispatcher.submit("experiment", None, body.model_dump(), idempotency_key)


@router.get("/experiments/{experiment_id}", tags=["experiments"])
def experiment(request: Request, experiment_id: Identifier):
    return request.app.state.repository.experiment(experiment_id)


@router.get("/experiments/{experiment_id}/export", tags=["exports"])
def export_experiment(request: Request, experiment_id: Identifier):
    result = request.app.state.repository.experiment(experiment_id)
    return JSONResponse(
        result,
        headers={"Content-Disposition": f'attachment; filename="{experiment_id}.json"'},
    )


@router.get("/models", tags=["catalog"])
def models():
    from neurocore.experiments import model_registry

    return model_registry()


@router.post("/datasets/import", status_code=201, tags=["datasets"])
def import_dataset(request: Request, body: ConnectomeImport):
    return request.app.state.service.import_connectome(body)

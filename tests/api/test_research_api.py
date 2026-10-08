"""Integration tests exercise actual neurocore work, persistence, and failure boundaries."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from neuroresect_api.config import Settings
from neuroresect_api.main import create_app

PREFIX = "/api/v1"


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'research.db'}")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def tiny_import():
    return {
        "deidentified": True,
        "patient_id": "RESEARCH-001",
        "patient_label": "De-identified subject 001",
        "atlas_id": "tiny-3",
        "dataset_id": "test-dataset",
        "synthetic": True,
        "nodes": [
            {"id": 10, "name": "Left A", "hemisphere": "L", "network": "test", "x": -1, "y": 0, "z": 0},
            {"id": 20, "name": "Middle B", "hemisphere": "M", "network": "test", "x": 0, "y": 0, "z": 0},
            {"id": 30, "name": "Right C", "hemisphere": "R", "network": "test", "x": 1, "y": 0, "z": 0},
        ],
        "matrix": [[0, 1, 0], [1, 0, 1], [0, 1, 0]],
        "actual_resection": [{"region_id": 20, "fraction_removed": 0.5}],
    }


def create_tiny_scenario(client, method="weighted"):
    imported = client.post(f"{PREFIX}/datasets/import", json=tiny_import())
    assert imported.status_code == 201, imported.text
    response = client.post(
        f"{PREFIX}/scenarios",
        json={
            "patient_id": "RESEARCH-001", "atlas_id": "tiny-3", "label": "Half of the bridge",
            "method": method, "regions": [{"region_id": 20, "fraction_removed": 0.5}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_job(client, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{PREFIX}/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"SUCCEEDED", "FAILED"}:
            return job
        time.sleep(0.02)
    pytest.fail(f"Job {job_id} did not reach a terminal state")


def test_import_simulate_export_and_restart(settings):
    with TestClient(create_app(settings)) as client:
        scenario = create_tiny_scenario(client)
        route = f"{PREFIX}/scenarios/{scenario['id']}"
        assert client.get(f"{route}/simulation").status_code == 404
        response = client.post(f"{route}/simulate", headers={"Idempotency-Key": "simulation-1"})
        assert response.status_code == 202
        job_id = response.json()["id"]
        completed = wait_for_job(client, job_id)
        assert completed["status"] == "SUCCEEDED", completed
        result = completed["result"]
        assert result["baseline"]["efficiency"] == pytest.approx(5 / 6)
        assert result["post"]["efficiency"] == pytest.approx(5 / 12)
        assert result["connectivity_loss"] == pytest.approx(0.5)
        assert result["provenance"]["scenario_id"] == scenario["id"]
        assert result["provenance"]["research_only"] is True
        repeated = client.post(f"{route}/simulate", headers={"Idempotency-Key": "simulation-1"})
        assert repeated.json()["id"] == job_id
        assert client.get(f"{route}/simulation").json() == result
        export = client.get(f"{route}/export")
        assert export.json()["simulation"] == result
        assert len(export.json()["connectome"]["matrix"]) == 3
        assert "attachment" in export.headers["Content-Disposition"]
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get(f"{PREFIX}/jobs/{job_id}").json()["status"] == "SUCCEEDED"
        assert reopened.get(f"{route}/simulation").json() == result
        assert reopened.get(f"{PREFIX}/scenarios?patient_id=RESEARCH-001").json()[0] == scenario
        assert reopened.get(f"{PREFIX}/patients/RESEARCH-001").json()["available_atlases"] == ["tiny-3"]


def test_catalog_openapi_health_and_request_identity(client):
    health = client.get("/health")
    assert health.json()["status"] == "ok"
    assert len(health.headers["X-Request-ID"]) == 32
    patient = client.get(f"{PREFIX}/patients").json()[0]
    assert patient["synthetic"] is True
    connectome = client.get(f"{PREFIX}/patients/{patient['id']}/connectome").json()
    assert len(connectome["nodes"]) == 64
    assert "matrix" not in connectome
    assert "matrix" in client.get(
        f"{PREFIX}/patients/{patient['id']}/connectome?include_matrix=true"
    ).json()
    schema = client.get("/openapi.json").json()
    assert f"{PREFIX}/scenarios/{{scenario_id}}/simulate" in schema["paths"]


@pytest.mark.parametrize("mutation", [
    lambda value: value["matrix"][0].__setitem__(1, -1),
    lambda value: value["matrix"][0].__setitem__(1, 0.4),
    lambda value: value["matrix"][0].__setitem__(0, 1),
    lambda value: value["nodes"][1].__setitem__("id", 10),
    lambda value: value["actual_resection"][0].__setitem__("region_id", 999),
    lambda value: value["actual_resection"][0].__setitem__("fraction_removed", 2),
    lambda value: value.__setitem__("patient_id", "../outside"),
    lambda value: value.__setitem__("deidentified", False),
    lambda value: value["matrix"][0].__setitem__(1, True),
    lambda value: value["nodes"].pop(),
])
def test_import_rejects_invalid_scientific_input(client, mutation):
    data = tiny_import()
    mutation(data)
    response = client.post(f"{PREFIX}/datasets/import", json=data)
    assert response.status_code == 422, response.text
    assert "error" in response.json()
    assert all(patient["id"] != "RESEARCH-001" for patient in client.get(f"{PREFIX}/patients").json())


def test_import_collisions_and_atlas_identity(client):
    first = tiny_import()
    assert client.post(f"{PREFIX}/datasets/import", json=first).status_code == 201
    assert client.post(f"{PREFIX}/datasets/import", json=first).status_code == 409
    second = copy.deepcopy(first)
    second["patient_id"] = "RESEARCH-002"
    second["nodes"][0]["name"] = "Mismatched atlas definition"
    response = client.post(f"{PREFIX}/datasets/import", json=second)
    assert response.json()["error"]["code"] == "ATLAS_DEFINITION_CONFLICT"
    second["patient_id"] = "DEMO-001"
    assert client.post(f"{PREFIX}/datasets/import", json=second).status_code == 409
    second["patient_id"] = "RESEARCH-002"
    second["atlas_id"] = "demo-64"
    assert client.post(f"{PREFIX}/datasets/import", json=second).status_code == 409


def test_scenario_rejects_bad_regions_and_unknown_entities(client):
    for regions in (
        [{"region_id": 9999, "fraction_removed": 0.4}],
        [{"region_id": 0, "fraction_removed": -0.2}],
        [{"region_id": 0, "fraction_removed": 0.2}] * 2,
    ):
        response = client.post(f"{PREFIX}/scenarios", json={"patient_id": "DEMO-001", "regions": regions})
        assert response.status_code == 422
        assert set(response.json()) == {"error"}
    assert client.get(f"{PREFIX}/patients/UNKNOWN").status_code == 404
    assert client.get(f"{PREFIX}/patients/DEMO-001/connectome?atlas_id=wrong").status_code == 404
    assert client.post(f"{PREFIX}/scenarios/UNKNOWN/simulate").status_code == 404
    assert client.get(f"{PREFIX}/jobs/UNKNOWN").status_code == 404
    assert client.get("/not-an-endpoint").json()["error"]["code"] == "HTTP_ERROR"


def test_imported_prediction_and_binary_counterfactual_are_explicitly_unsupported(client):
    scenario = create_tiny_scenario(client, method="binary")
    route = f"{PREFIX}/scenarios/{scenario['id']}"
    assert client.post(f"{route}/predict").json()["error"]["code"] == "MODEL_INCOMPATIBLE"
    response = client.post(f"{route}/counterfactuals", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_RESECTION_METHOD"


def test_real_sensitivity_and_constrained_counterfactuals(client):
    scenario = create_tiny_scenario(client)
    route = f"{PREFIX}/scenarios/{scenario['id']}"
    sensitivity = client.post(f"{route}/sensitivity")
    result = wait_for_job(client, sensitivity.json()["id"])
    assert result["status"] == "SUCCEEDED", result
    assert len(result["result"]["variants"]) >= 3
    response = client.post(
        f"{route}/counterfactuals", json={"protected_regions": [10], "minimum_target_coverage": 0.8},
        headers={"Idempotency-Key": "alternatives-1"},
    )
    result = wait_for_job(client, response.json()["id"])
    assert result["status"] == "SUCCEEDED", result
    for candidate in result["result"]["candidates"]:
        assert candidate["target_coverage"] >= 0.8
        assert all(region["region_id"] != 10 for region in candidate["regions"])
    conflict = client.post(
        f"{route}/counterfactuals", json={"minimum_target_coverage": 0.9},
        headers={"Idempotency-Key": "alternatives-1"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_failed_jobs_are_persisted_and_error_is_sanitized(client, monkeypatch):
    scenario = create_tiny_scenario(client)

    def fail(*args, **kwargs):
        raise RuntimeError("private source matrix should not leak")

    monkeypatch.setattr("neurocore.simulation.simulate", fail)
    response = client.post(f"{PREFIX}/scenarios/{scenario['id']}/simulate")
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "JOB_FAILED"
    assert "private source" not in str(job)
    assert client.get(f"{PREFIX}/scenarios/{scenario['id']}/simulation").status_code == 404


def test_restart_marks_unfinished_local_jobs_failed(settings):
    with TestClient(create_app(settings)) as client:
        repository = client.app.state.repository
        queued, _ = repository.create_job("simulation", "SCN-unfinished", {}, "local", None)
        running, _ = repository.create_job("simulation", "SCN-unfinished", {}, "local", None)
        assert repository.claim_job(running["id"]) is not None
    with TestClient(create_app(settings)) as client:
        for old in (queued, running):
            recovered = client.get(f"{PREFIX}/jobs/{old['id']}").json()
            assert recovered["status"] == "FAILED"
            assert recovered["error"]["code"] == "JOB_INTERRUPTED"


def test_idempotency_is_atomic_across_concurrent_requests(client):
    repository = client.app.state.repository

    def submit(_):
        return repository.create_job("simulation", "SCN-concurrent", {}, "local", "same-key")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(12)))
    assert len({job["id"] for job, _ in results}) == 1
    assert sum(created for _, created in results) == 1


def test_body_limits_and_invalid_json_return_standard_errors(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'limits.db'}", max_request_bytes=1024)
    with TestClient(create_app(settings)) as client:
        oversized = client.post(f"{PREFIX}/datasets/import", content=b"x" * 1025)
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"
        invalid = client.post(f"{PREFIX}/datasets/import", content=b"{broken", headers={"Content-Type": "application/json"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"


def test_dispatch_failure_is_visible(client, monkeypatch):
    scenario = create_tiny_scenario(client)

    def unavailable(*args, **kwargs):
        raise RuntimeError("executor unavailable")

    monkeypatch.setattr(client.app.state.dispatcher.pool, "submit", unavailable)
    response = client.post(f"{PREFIX}/scenarios/{scenario['id']}/simulate")
    assert response.status_code == 202
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"]["code"] == "DISPATCH_FAILED"


def test_experiment_and_prediction_roundtrip(client):
    response = client.post(f"{PREFIX}/experiments", json={"n_patients": 24, "folds": 3})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"], timeout=60)
    assert job["status"] == "SUCCEEDED", job["error"]
    experiment = job["result"]
    assert set(experiment["models"]) == {"A", "B", "C"}
    assert client.get(f"{PREFIX}/experiments/{experiment['id']}/export").status_code == 200
    connectome = client.get(f"{PREFIX}/patients/DEMO-001/connectome").json()
    scenario = client.post(f"{PREFIX}/scenarios", json={
        "patient_id": "DEMO-001", "atlas_id": "demo-64",
        "regions": connectome["actual_resection"],
    }).json()
    prediction = client.post(f"{PREFIX}/scenarios/{scenario['id']}/predict")
    job = wait_for_job(client, prediction.json()["id"], timeout=60)
    assert job["status"] == "SUCCEEDED", job["error"]
    assert job["result"]["provenance"]["scenario_id"] == scenario["id"]
    assert job["result"]["interval"]["iterations"] == 64
    assert len(client.get(f"{PREFIX}/models").json()) == 2

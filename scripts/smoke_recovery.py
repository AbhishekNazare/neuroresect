"""CI-only destructive fault drill for the disposable Compose stack, never production."""

import json
import subprocess
import time
import urllib.request


def compose(*args):
    subprocess.run(["docker", "compose", *args], check=True, timeout=120)


def request(path, body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    compose("stop", "worker", "redis")
    try:
        connectome = request("/api/v1/patients/DEMO-001/connectome")
        scenario = request(
            "/api/v1/scenarios",
            {
                "patient_id": "DEMO-001",
                "atlas_id": "demo-64",
                "label": "Disposable recovery drill",
                "regions": connectome["actual_resection"],
            },
        )
        job = request(f"/api/v1/scenarios/{scenario['id']}/simulate", {})
        assert job["status"] == "QUEUED", job
        assert job["stage"] == "WAITING_FOR_BROKER", job
        compose("restart", "api")
    finally:
        compose("up", "-d", "--wait", "redis", "worker")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = request(f"/api/v1/jobs/{job['id']}")
        if job["status"] in {"SUCCEEDED", "FAILED"}:
            break
        time.sleep(1)
    assert job["status"] == "SUCCEEDED", job
    assert job["dispatch_attempts"] >= 2, job
    assert job["result"]["provenance"]["scenario_id"] == scenario["id"]
    print("Broker outage + API restart: persisted job was redelivered and completed")


if __name__ == "__main__":
    main()

"""Exercise a running API/worker stack without third-party client dependencies."""

import argparse
import json
import time
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        with urlopen(
            Request(args.url + path, data=data, headers={"Content-Type": "application/json"}),
            timeout=15,
        ) as response:
            return json.load(response)

    assert request("/health")["status"] == "ok"
    connectome = request("/api/v1/patients/DEMO-001/connectome")
    scenario = request(
        "/api/v1/scenarios",
        {
            "patient_id": "DEMO-001",
            "atlas_id": "demo-64",
            "label": "Container integration smoke",
            "regions": connectome["actual_resection"],
        },
    )
    job = request(f"/api/v1/scenarios/{scenario['id']}/simulate", {})
    deadline = time.monotonic() + 90
    while job["status"] in {"QUEUED", "RUNNING"} and time.monotonic() < deadline:
        time.sleep(0.5)
        job = request(f"/api/v1/jobs/{job['id']}")
    assert job["status"] == "SUCCEEDED", job
    assert 0 < job["result"]["connectivity_loss"] < 1
    export = request(f"/api/v1/scenarios/{scenario['id']}/export")
    assert export["simulation"]["provenance"]["scenario_id"] == scenario["id"]
    print("API, worker execution, persistence, and provenance export passed.")


if __name__ == "__main__":
    main()

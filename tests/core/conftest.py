import pytest


@pytest.fixture
def line_connectome():
    return {
        "patient_id": "TEST-001", "atlas_id": "test-4", "dataset_id": "unit-fixtures",
        "synthetic": True,
        "nodes": [
            {"id": i, "name": f"Node {i}", "hemisphere": "L" if i < 2 else "R",
             "network": "test", "x": float(i), "y": 0.0, "z": 0.0}
            for i in range(4)
        ],
        "matrix": [[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]],
        "actual_resection": [],
    }

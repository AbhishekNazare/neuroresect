"""Deterministic, entirely synthetic atlases, subjects and structural connectomes.

Coordinates are an illustrative ellipsoid, not registered anatomy. x is left/right
(positive right), y posterior/anterior (positive anterior), z inferior/superior.
"""

from __future__ import annotations

import copy
import hashlib
from functools import lru_cache

import numpy as np

from neurocore.validation import matrix_edges

DATASET_ID = "synthetic-dwi-v1"
NETWORKS = [
    "default-mode",
    "frontoparietal",
    "limbic",
    "somatomotor",
    "dorsal-attention",
    "ventral-attention",
    "visual",
]
REGION_NAMES = [
    "Superior frontal",
    "Middle frontal",
    "Inferior frontal",
    "Orbitofrontal",
    "Anterior cingulate",
    "Precentral",
    "Postcentral",
    "Superior parietal",
    "Inferior parietal",
    "Supramarginal",
    "Angular",
    "Precuneus",
    "Posterior cingulate",
    "Superior temporal",
    "Middle temporal",
    "Inferior temporal",
    "Temporal pole",
    "Entorhinal",
    "Parahippocampal",
    "Fusiform",
    "Lateral occipital",
    "Cuneus",
    "Lingual",
    "Pericalcarine",
    "Insula",
    "Hippocampal",
    "Amygdalar",
    "Thalamic",
    "Caudate",
    "Putamen",
    "Pallidal",
    "Accumbens",
]


def list_atlases() -> list[dict]:
    return [
        {
            "id": f"demo-{count}",
            "name": f"Illustrative {count}",
            "region_count": count,
            "synthetic": True,
            "description": "Synthetic bilateral ellipsoid; illustrative region labels, not a registered clinical atlas.",
        }
        for count in (64, 96)
    ]


@lru_cache(maxsize=2)
def _atlas_nodes(atlas_id: str) -> list[dict]:
    if atlas_id not in ("demo-64", "demo-96"):
        raise ValueError(f"Unknown atlas: {atlas_id}")
    half = int(atlas_id.split("-")[1]) // 2
    nodes: list[dict] = []
    # Fibonacci sampling on each lateral hemisphere avoids longitude clustering.
    for hemisphere, sign in (("L", -1), ("R", 1)):
        for index in range(half):
            lateral = 0.12 + 0.85 * (index + 0.5) / half
            angle = index * np.pi * (3 - np.sqrt(5))
            radius = np.sqrt(1 - lateral**2)
            y = 1.30 * radius * np.cos(angle)
            z = 0.90 * radius * np.sin(angle)
            network = (
                "visual"
                if y < -0.60
                else "frontoparietal"
                if y > 0.55
                else "somatomotor"
                if z > 0.35
                else "limbic"
                if z < -0.40
                else NETWORKS[index % len(NETWORKS)]
            )
            suffix = f" · parcel {index // 32 + 1}" if index >= 32 else ""
            nodes.append(
                {
                    "id": len(nodes),
                    "name": f"{hemisphere} {REGION_NAMES[index % 32]}{suffix}",
                    "hemisphere": hemisphere,
                    "network": network,
                    "x": float(sign * lateral),
                    "y": float(y),
                    "z": float(z),
                }
            )
    return nodes


def atlas_nodes(atlas_id: str = "demo-64") -> list[dict]:
    return copy.deepcopy(_atlas_nodes(atlas_id))


def synthetic_patient(index: int) -> dict:
    rng = np.random.default_rng(1701 + index)
    age = int(rng.integers(19, 65))
    return {
        "id": f"DEMO-{index:03d}",
        "dataset_id": DATASET_ID,
        "label": f"Synthetic participant {index:03d}",
        "age": age,
        "sex": "F" if index % 2 else "M",
        "epilepsy_duration": int(rng.integers(2, min(age - 5, 29))),
        "modalities": ["DWI"],
        "available_atlases": ["demo-64", "demo-96"],
        "synthetic": True,
    }


def list_patients() -> list[dict]:
    return [synthetic_patient(index) for index in range(1, 13)]


@lru_cache(maxsize=512)
def _synthetic_connectome(index: int, atlas_id: str) -> dict:
    nodes = _atlas_nodes(atlas_id)
    n = len(nodes)
    seed = int.from_bytes(
        hashlib.sha256(f"synthetic-dwi-v1:{index}:{atlas_id}".encode()).digest()[:8], "little"
    )
    rng = np.random.default_rng(seed)
    xyz = np.array([[node[axis] for axis in ("x", "y", "z")] for node in nodes])
    distances = np.linalg.norm(xyz[:, None] - xyz[None, :], axis=2)
    networks = np.array([node["network"] for node in nodes])
    within = networks[:, None] == networks[None, :]
    hemisphere = np.array([node["hemisphere"] for node in nodes])
    ipsilateral = hemisphere[:, None] == hemisphere[None, :]
    # Positive structural weights combine distance, modularity and subject variation.
    probability = 0.045 + 0.38 * np.exp(-distances / 0.85) + 0.24 * within
    upper = np.triu(rng.random((n, n)) < probability, 1)
    raw = (0.10 + 0.80 * np.exp(-distances / 1.4)) * (1 + 0.35 * within)
    raw *= rng.lognormal(0, 0.24, (n, n)) * (0.80 + 0.40 * rng.random())
    raw *= np.where(ipsilateral, 1.0, 0.75)
    weights = np.triu(raw * upper, 1)
    weights += weights.T
    # A sparse positive backbone keeps demo baseline graphs connected.
    for i in range(n - 1):
        weights[i, i + 1] = weights[i + 1, i] = max(weights[i, i + 1], 0.08)
    weights = np.round(weights, 6)
    side = 0 if index % 3 else n // 2
    targets = [side + target for target in (13, 14, 16, 17, 18, 25)]
    resection = [
        {"region_id": target, "fraction_removed": round(float(rng.uniform(0.25, 0.95)), 2)}
        for target in targets[: int(rng.integers(3, 7))]
    ]
    return {
        "patient_id": f"DEMO-{index:03d}",
        "dataset_id": DATASET_ID,
        "atlas_id": atlas_id,
        "synthetic": True,
        "nodes": nodes,
        "matrix": weights.tolist(),
        "edges": matrix_edges(weights, [node["id"] for node in nodes]),
        "actual_resection": resection,
        "coordinate_system": "Illustrative normalized RAS: +x right, +y anterior, +z superior",
        "weight_units": "arbitrary synthetic structural strength",
    }


def synthetic_connectome(index: int, atlas_id: str = "demo-64") -> dict:
    """Internal reproducible synthetic cohort generator; no real patient information."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ValueError("Synthetic participant index must be a positive integer")
    return copy.deepcopy(_synthetic_connectome(index, atlas_id))


def get_connectome(patient_id: str, atlas_id: str = "demo-64") -> dict:
    if patient_id not in {patient["id"] for patient in list_patients()}:
        raise ValueError(f"Unknown patient: {patient_id}")
    return synthetic_connectome(int(patient_id.split("-")[1]), atlas_id)

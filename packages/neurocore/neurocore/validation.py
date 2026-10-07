"""Reject malformed scientific data instead of silently repairing it."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

MAX_REGIONS = 500


def finite_number(value: Any, name: str) -> float:
    if isinstance(value, (bool, str)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def validate_matrix(matrix: Any, n_regions: int | None = None) -> np.ndarray:
    try:
        result = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Matrix must be numeric and rectangular") from error
    if result.ndim != 2 or result.shape[0] != result.shape[1]:
        raise ValueError("Matrix must be square")
    if not 2 <= len(result) <= MAX_REGIONS:
        raise ValueError(f"Matrix must contain 2..{MAX_REGIONS} regions")
    if n_regions is not None and len(result) != n_regions:
        raise ValueError("Matrix dimensions do not match atlas regions")
    if not np.isfinite(result).all() or (result < 0).any():
        raise ValueError("Matrix weights must be finite and nonnegative")
    if not np.allclose(result, result.T, rtol=0, atol=1e-10):
        raise ValueError("Matrix must be symmetric (absolute tolerance 1e-10)")
    if not np.allclose(np.diag(result), 0, rtol=0, atol=1e-12):
        raise ValueError("Matrix diagonal must be zero")
    # Canonicalize only accepted floating point roundoff; never repair invalid input.
    result = (result + result.T) / 2
    np.fill_diagonal(result, 0)
    return result


def validate_regions(regions: Any, node_ids: Sequence[int]) -> list[dict]:
    if not isinstance(regions, (list, tuple)):
        raise ValueError("Resection regions must be an array")
    known, seen, result = set(node_ids), set(), []
    for region in regions:
        if not isinstance(region, Mapping):
            raise ValueError("Each resection region must be an object")
        region_id = region.get("region_id")
        if isinstance(region_id, bool) or not isinstance(region_id, int) or region_id not in known:
            raise ValueError(f"Unknown or invalid region_id: {region_id}")
        if region_id in seen:
            raise ValueError(f"Duplicate resection region_id: {region_id}")
        fraction = finite_number(region.get("fraction_removed"), "fraction_removed")
        if not 0 <= fraction <= 1:
            raise ValueError("fraction_removed must be between 0 and 1")
        seen.add(region_id)
        result.append({"region_id": region_id, "fraction_removed": fraction})
    return sorted(result, key=lambda region: region["region_id"])


def matrix_edges(matrix: np.ndarray, node_ids: Sequence[int]) -> list[dict]:
    source, target = np.where(np.triu(matrix, 1) > 0)
    return [
        {"source": node_ids[int(i)], "target": node_ids[int(j)], "weight": float(matrix[i, j])}
        for i, j in zip(source, target, strict=True)
    ]


def validate_connectome(connectome: Any) -> dict:
    if not isinstance(connectome, Mapping):
        raise ValueError("Connectome must be an object")
    for key in ("patient_id", "atlas_id", "dataset_id"):
        if not isinstance(connectome.get(key), str) or not connectome[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    nodes = connectome.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("nodes must be an array")
    matrix = validate_matrix(connectome.get("matrix"), len(nodes))
    clean_nodes, seen = [], set()
    for node in nodes:
        if not isinstance(node, Mapping):
            raise ValueError("Each node must be an object")
        node_id = node.get("id")
        if isinstance(node_id, bool) or not isinstance(node_id, int) or node_id < 0 or node_id in seen:
            raise ValueError("Node IDs must be unique nonnegative integers")
        for key in ("name", "hemisphere", "network"):
            if not isinstance(node.get(key), str) or not node[key].strip():
                raise ValueError(f"Node {key} must be a nonempty string")
        if node["hemisphere"] not in ("L", "R", "M"):
            raise ValueError("Node hemisphere must be L, R, or M")
        clean_node = {key: node[key] for key in ("id", "name", "hemisphere", "network")}
        for axis in ("x", "y", "z"):
            clean_node[axis] = finite_number(node.get(axis), axis)
        clean_nodes.append(clean_node)
        seen.add(node_id)
    synthetic = connectome.get("synthetic", False)
    if not isinstance(synthetic, bool):
        raise ValueError("synthetic must be boolean")
    region_ids = [node["id"] for node in clean_nodes]
    return {
        **connectome, "nodes": clean_nodes, "matrix": matrix.tolist(), "synthetic": synthetic,
        "actual_resection": validate_regions(connectome.get("actual_resection", []), region_ids),
        "edges": matrix_edges(matrix, region_ids),
    }

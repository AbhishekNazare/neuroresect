"""Deterministic virtual resection; both endpoints independently attenuate an edge."""

from __future__ import annotations

import numpy as np

from neurocore.metrics import global_metrics, node_metrics
from neurocore.provenance import connectome_identity, provenance
from neurocore.thresholds import threshold_matrix
from neurocore.validation import (
    matrix_edges,
    validate_connectome,
    validate_matrix,
    validate_regions,
)


def resect_matrix(matrix, regions: list[dict], node_ids: list[int], method: str = "weighted") -> np.ndarray:
    if method not in ("weighted", "binary"):
        raise ValueError("method must be weighted or binary")
    regions = validate_regions(regions, node_ids)
    by_id = {region["region_id"]: region["fraction_removed"] for region in regions}
    removed = np.array([by_id.get(region_id, 0.0) for region_id in node_ids])
    if method == "binary":
        removed = (removed >= 0.5).astype(float)
    retained = 1 - removed
    return validate_matrix(matrix, len(node_ids)) * np.outer(retained, retained)


def simulate(connectome: dict, regions: list[dict], method: str = "weighted", threshold: float = 0.0) -> dict:
    connectome = validate_connectome(connectome)
    node_ids = [node["id"] for node in connectome["nodes"]]
    regions = validate_regions(regions, node_ids)
    before = threshold_matrix(connectome["matrix"], "absolute", threshold)
    after = resect_matrix(before, regions, node_ids, method)
    baseline, post = global_metrics(before), global_metrics(after)
    delta, relative_delta = {}, {}
    for key, original in baseline.items():
        modified = post[key]
        delta[key] = None if original is None or modified is None else modified - original
        relative_delta[key] = None if original in (None, 0) or modified is None else (modified - original) / original
    baseline_nodes, post_nodes = node_metrics(before), node_metrics(after)
    removal = {region["region_id"]: region["fraction_removed"] for region in regions}
    nodes, impacted = [], []
    for node, old, new in zip(connectome["nodes"], baseline_nodes, post_nodes, strict=True):
        strength_loss = old["strength"] - new["strength"]
        if old["is_hub"] and strength_loss > 1e-12:
            impacted.append(node["id"])
        nodes.append({
            **node, **old, "post_strength": new["strength"], "post_degree": new["degree"],
            "post_is_hub": new["is_hub"], "strength_delta": -strength_loss,
            "post_betweenness": new["betweenness"], "post_closeness": new["closeness"],
            "post_eigenvector": new["eigenvector"], "post_participation_coefficient": new["participation_coefficient"],
            "fraction_removed": removal.get(node["id"], 0.0),
        })
    old_hub_strength = sum(node["strength"] for node in baseline_nodes if node["is_hub"])
    remaining_hub_strength = sum(new["strength"] for old, new in zip(baseline_nodes, post_nodes, strict=True) if old["is_hub"])
    total_weight = float(before.sum())
    config = {
        "method": method, "threshold": float(threshold), "threshold_strategy": "absolute",
        "threshold_application": "baseline before resection; no post-hoc pruning",
        "binary_fraction_threshold": 0.5, "regions": regions,
        "node_denominator": "original atlas; removed nodes retained as isolates",
        "efficiency_distance": "reciprocal positive strength; unreachable pairs contribute zero",
        "path_length": "null when disconnected; reachable_path_length excludes unreachable pairs",
        "hub_definition": "baseline strength > mean + population standard deviation",
        "node_metrics": "normalized reciprocal-distance betweenness; Wasserman-Faust closeness; eigenvector null on nonconvergence; participation over greedy weighted communities",
    }
    return {
        "baseline": baseline, "post": post, "delta": delta, "relative_delta": relative_delta,
        "connectivity_loss": 0.0 if total_weight == 0 else float(1 - after.sum() / total_weight),
        "impacted_hubs": impacted,
        "hub_damage": 0.0 if old_hub_strength == 0 else float(1 - remaining_hub_strength / old_hub_strength),
        "removed_edges": int(np.count_nonzero(np.triu((before > 0) & (after == 0), 1))),
        "attenuated_edges": int(np.count_nonzero(np.triu((after < before) & (after > 0), 1))),
        "nodes": nodes, "edges": matrix_edges(after, node_ids),
        "provenance": {
            **provenance("virtual-resection-v1", connectome_identity(connectome), config),
            "patient_id": connectome["patient_id"], "dataset_id": connectome["dataset_id"],
            "atlas_id": connectome["atlas_id"], "synthetic": connectome["synthetic"],
        },
    }

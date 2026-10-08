"""Versioned, explicitly allowed preoperative and simulated-resection features."""

from __future__ import annotations

import numpy as np

from neurocore.validation import validate_regions

FEATURE_VERSION = "clinical-graph-delta-v1"
CLINICAL_FEATURES = (
    "age", "sex_female", "epilepsy_duration", "resection_fraction_sum",
    "resection_region_fraction", "resection_left_fraction",
)
BASELINE_FEATURES = (
    "baseline_efficiency", "baseline_density", "baseline_clustering", "baseline_modularity",
    "baseline_mean_strength",
)
DELTA_FEATURES = (
    "simulated_post_efficiency", "simulated_post_clustering", "simulated_post_modularity",
    "delta_efficiency", "delta_modularity", "connectivity_loss", "hub_damage",
)
FEATURE_SETS = {
    "A": CLINICAL_FEATURES,
    "B": CLINICAL_FEATURES + BASELINE_FEATURES,
    "C": CLINICAL_FEATURES + BASELINE_FEATURES + DELTA_FEATURES,
}


def extract_features(patient: dict, connectome: dict, regions: list[dict], simulation: dict) -> dict[str, float]:
    regions = validate_regions(regions, [node["id"] for node in connectome["nodes"]])
    fractions = {region["region_id"]: region["fraction_removed"] for region in regions}
    resection_mass = sum(fractions.values())
    left_mass = sum(fractions.get(node["id"], 0.0) for node in connectome["nodes"] if node["hemisphere"] == "L")
    baseline, post = simulation["baseline"], simulation["post"]
    features = {
        "age": float(patient["age"]), "sex_female": float(patient["sex"] == "F"),
        "epilepsy_duration": float(patient["epilepsy_duration"]),
        "resection_fraction_sum": resection_mass,
        "resection_region_fraction": sum(value > 0 for value in fractions.values()) / len(connectome["nodes"]),
        "resection_left_fraction": left_mass / resection_mass if resection_mass else 0.0,
        "baseline_mean_strength": float(np.asarray(connectome["matrix"]).sum() / len(connectome["nodes"])),
        "connectivity_loss": float(simulation["connectivity_loss"]), "hub_damage": float(simulation["hub_damage"]),
    }
    for metric in ("efficiency", "density", "clustering", "modularity"):
        features[f"baseline_{metric}"] = float(baseline[metric])
    for metric in ("efficiency", "clustering", "modularity"):
        features[f"simulated_post_{metric}"] = float(post[metric])
    for metric in ("efficiency", "modularity"):
        features[f"delta_{metric}"] = float(post[metric] - baseline[metric])
    return {name: features[name] for name in FEATURE_SETS["C"]}

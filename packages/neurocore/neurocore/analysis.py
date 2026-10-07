"""Fraction sensitivity and finite constrained research-scenario search.

Coverage is retained removal mass relative to the requested target fractions.
It is not anatomical target coverage: no voxel masks or tissue volumes exist here.
"""

from __future__ import annotations

from neurocore.provenance import connectome_identity, content_hash, provenance
from neurocore.simulation import simulate
from neurocore.validation import finite_number, validate_connectome, validate_regions


def sensitivity(connectome: dict, regions: list[dict], method: str = "weighted") -> dict:
    connectome = validate_connectome(connectome)
    regions = validate_regions(regions, [node["id"] for node in connectome["nodes"]])
    variants = []
    for offset in (-0.10, -0.05, 0.0, 0.05, 0.10):
        changed = [
            {"region_id": region["region_id"], "fraction_removed": min(1.0, max(0.0, region["fraction_removed"] + offset))}
            for region in regions
        ]
        result = simulate(connectome, changed, method)
        variants.append({
            "label": "Baseline scenario" if offset == 0 else f"{offset * 100:+.0f} percentage points",
            "offset": offset, "regions": changed, "connectivity_loss": result["connectivity_loss"],
            "efficiency": result["post"]["efficiency"], "efficiency_delta": result["delta"]["efficiency"],
        })
    scores = []
    reference = variants[2]["efficiency"]
    for region in regions:
        changes = []
        for offset in (-0.10, 0.10):
            perturbed = [
                {**entry, "fraction_removed": min(1.0, max(0.0, entry["fraction_removed"] + offset))}
                if entry["region_id"] == region["region_id"] else entry for entry in regions
            ]
            changes.append(abs(simulate(connectome, perturbed, method)["post"]["efficiency"] - reference))
        scores.append({"region_id": region["region_id"], "score": sum(changes) / len(changes)})
    return {
        "variants": variants, "region_scores": scores,
        "provenance": provenance("fraction-sensitivity-v1", connectome_identity(connectome), {
            "regions": regions, "method": method, "offsets": [-0.1, -0.05, 0, 0.05, 0.1],
            "score_definition": "mean absolute efficiency change for individual fraction ±10 percentage points; not prediction sensitivity",
        }),
    }


def counterfactuals(connectome: dict, regions: list[dict], constraints: dict | None = None) -> dict:
    connectome = validate_connectome(connectome)
    node_ids = [node["id"] for node in connectome["nodes"]]
    regions = validate_regions(regions, node_ids)
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    constraints = constraints or {}
    unknown = set(constraints) - {"minimum_target_coverage", "protected_regions", "max_candidates"}
    if unknown:
        raise ValueError(f"Unknown constraints: {sorted(unknown)}")
    minimum = finite_number(constraints.get("minimum_target_coverage", 0.8), "minimum_target_coverage")
    maximum = constraints.get("max_candidates", 5)
    protected = constraints.get("protected_regions", [])
    if not 0 <= minimum <= 1:
        raise ValueError("minimum_target_coverage must be between 0 and 1")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 50:
        raise ValueError("max_candidates must be an integer between 1 and 50")
    if not isinstance(protected, list) or any(isinstance(i, bool) or not isinstance(i, int) or i not in node_ids for i in protected):
        raise ValueError("protected_regions must contain valid region IDs")
    normalized = {"minimum_target_coverage": minimum, "protected_regions": sorted(set(protected)), "max_candidates": maximum}
    config = {
        "regions": regions, "constraints": normalized, "method": "weighted",
        "algorithm": "deterministic beam search, depth=3, width=12, removal decrements=0.1",
        "coverage_definition": "sum(min(candidate removal, target removal)) / sum(target removal)",
        "objective": "connectivity_loss + 0.35 * hub_damage (lower is better)",
        "limitations": "finite search; no global optimum or clinical outcome guarantee; fractions are not tissue volumes",
    }
    target_mass = sum(region["fraction_removed"] for region in regions)
    provenance_data = provenance("constrained-search-v1", connectome_identity(connectome), config)
    if target_mass == 0:
        return {"candidates": [], "constraints": normalized, "provenance": provenance_data}
    initial = [
        {**region, "fraction_removed": 0.0 if region["region_id"] in protected else region["fraction_removed"]}
        for region in regions
    ]
    if sum(region["fraction_removed"] for region in initial) / target_mass + 1e-12 < minimum:
        return {"candidates": [], "constraints": normalized, "provenance": provenance_data}
    evaluated = {}

    def evaluate(candidate):
        key = content_hash(candidate)
        if key in evaluated:
            return evaluated[key]
        coverage = sum(region["fraction_removed"] for region in candidate) / target_mass
        if coverage + 1e-12 < minimum:
            return None
        result = simulate(connectome, candidate)
        record = {
            "id": f"CF-{key[:10]}", "label": "Target-preserving research alternative", "regions": candidate,
            "target_coverage": coverage, "connectivity_loss": result["connectivity_loss"],
            "hub_damage": result["hub_damage"],
            "objective_score": result["connectivity_loss"] + 0.35 * result["hub_damage"],
            "efficiency": result["post"]["efficiency"],
        }
        evaluated[key] = record
        return record

    beam = [evaluate(initial)]
    for _ in range(3):
        next_beam = {}
        for parent in beam:
            for index, region in enumerate(parent["regions"]):
                if region["fraction_removed"] <= 0:
                    continue
                candidate = [dict(entry) for entry in parent["regions"]]
                candidate[index]["fraction_removed"] = max(0.0, round(region["fraction_removed"] - 0.1, 10))
                item = evaluate(candidate)
                if item is not None:
                    next_beam[item["id"]] = item
        beam = sorted(next_beam.values(), key=lambda item: (item["objective_score"], item["id"]))[:12]
        if not beam:
            break
    candidates = sorted(evaluated.values(), key=lambda item: (item["objective_score"], item["id"]))[:maximum]
    for index, candidate in enumerate(candidates, 1):
        candidate["label"] = f"Alternative {index} · {candidate['target_coverage']:.0%} target fraction coverage"
    provenance_data["evaluated_candidates"] = len(evaluated)
    return {"candidates": candidates, "constraints": normalized, "provenance": provenance_data}

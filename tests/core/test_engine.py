import copy
import json

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from neurocore.analysis import counterfactuals, sensitivity
from neurocore.demo import get_connectome, list_atlases, list_patients
from neurocore.metrics import global_metrics, node_metrics
from neurocore.provenance import content_hash
from neurocore.simulation import resect_matrix, simulate
from neurocore.thresholds import threshold_matrix
from neurocore.validation import validate_connectome, validate_matrix


def test_known_line_metrics(line_connectome):
    metrics = global_metrics(line_connectome["matrix"])
    assert metrics["efficiency"] == pytest.approx(13 / 18)
    assert metrics["path_length"] == pytest.approx(5 / 3)
    assert metrics["density"] == 0.5
    assert metrics["clustering"] == 0
    assert metrics["components"] == 1


def test_efficiency_uses_strength_as_reciprocal_distance():
    assert global_metrics([[0, 2], [2, 0]])["efficiency"] == 2
    assert global_metrics([[0, 2], [2, 0]])["path_length"] == 0.5


def test_node_centralities_on_line_and_empty_graph(line_connectome):
    nodes = node_metrics(line_connectome["matrix"])
    assert nodes[1]["betweenness"] == pytest.approx(2 / 3)
    assert nodes[1]["closeness"] == pytest.approx(3 / 4)
    assert nodes[0]["eigenvector"] < nodes[1]["eigenvector"]
    for node in node_metrics(np.zeros((4, 4))):
        assert (
            node["betweenness"]
            == node["closeness"]
            == node["eigenvector"]
            == node["participation_coefficient"]
            == 0
        )
    disconnected = node_metrics([[0, 1, 0], [1, 0, 0], [0, 0, 0]])
    assert disconnected[2]["closeness"] == 0
    assert all(0 <= node["participation_coefficient"] <= 1 for node in nodes)


def test_weighted_double_endpoints_and_no_mutation(line_connectome):
    original = copy.deepcopy(line_connectome)
    regions = [{"region_id": 1, "fraction_removed": 0.4}, {"region_id": 2, "fraction_removed": 0.2}]
    result = simulate(line_connectome, regions)
    weights = {(edge["source"], edge["target"]): edge["weight"] for edge in result["edges"]}
    assert weights[(1, 2)] == pytest.approx(0.48)
    assert weights[(0, 1)] == pytest.approx(0.6)
    assert weights[(2, 3)] == pytest.approx(0.8)
    assert result["removed_edges"] == 0
    assert result["attenuated_edges"] == 3
    assert line_connectome == original
    assert result["delta"]["efficiency"] < 0


def test_binary_keeps_original_denominator_and_fraction_cutoff(line_connectome):
    result = simulate(line_connectome, [{"region_id": 1, "fraction_removed": 0.5}], "binary")
    assert result["post"]["efficiency"] == pytest.approx(1 / 6)
    assert result["post"]["components"] == 3
    assert result["post"]["node_count"] == 4
    assert result["post"]["path_length"] is None
    assert result["post"]["reachable_path_length"] == 1
    assert result["removed_edges"] == 2
    unchanged = simulate(line_connectome, [{"region_id": 1, "fraction_removed": 0.4999}], "binary")
    assert unchanged["baseline"] == unchanged["post"]


def test_total_removal_and_empty_graph_are_json_safe(line_connectome):
    regions = [{"region_id": i, "fraction_removed": 1.0} for i in range(4)]
    result = simulate(line_connectome, regions)
    assert result["post"]["efficiency"] == 0
    assert result["connectivity_loss"] == 1
    line_connectome["matrix"] = np.zeros((4, 4)).tolist()
    result = simulate(line_connectome, [])
    assert result["connectivity_loss"] == 0
    assert result["relative_delta"]["efficiency"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "matrix",
    [
        [[0, 1, 2], [1, 0, 1]],
        [[0, -1], [-1, 0]],
        [[0, float("nan")], [float("nan"), 0]],
        [[0, float("inf")], [float("inf"), 0]],
        [[0, 1], [2, 0]],
        [[1, 0], [0, 0]],
        [[0]],
    ],
)
def test_invalid_matrices_rejected(matrix):
    with pytest.raises(ValueError):
        validate_matrix(matrix)


@pytest.mark.parametrize(
    "regions",
    [
        [{"region_id": 99, "fraction_removed": 0.5}],
        [{"region_id": True, "fraction_removed": 0.5}],
        [{"region_id": 1, "fraction_removed": -0.01}],
        [{"region_id": 1, "fraction_removed": 1.01}],
        [{"region_id": 1, "fraction_removed": float("nan")}],
        [{"region_id": 1, "fraction_removed": True}],
        [{"region_id": 1, "fraction_removed": 0.3}, {"region_id": 1, "fraction_removed": 0.4}],
    ],
)
def test_invalid_regions_rejected(line_connectome, regions):
    with pytest.raises(ValueError):
        simulate(line_connectome, regions)


@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=4, max_size=4))
@settings(max_examples=30)
def test_resection_never_increases_strength_or_efficiency(fractions):
    weights = np.array([[0, 1, 0.5, 0], [1, 0, 2, 0.3], [0.5, 2, 0, 1], [0, 0.3, 1, 0]])
    regions = [{"region_id": i, "fraction_removed": value} for i, value in enumerate(fractions)]
    modified = resect_matrix(weights, regions, list(range(4)))
    assert np.all(modified <= weights)
    assert np.array_equal(modified, modified.T)
    assert global_metrics(modified)["efficiency"] <= global_metrics(weights)["efficiency"] + 1e-12


def test_threshold_strategies_and_scientific_threshold(line_connectome):
    matrix = [[0, 0.2, 0.8], [0.2, 0, 0.5], [0.8, 0.5, 0]]
    assert np.count_nonzero(threshold_matrix(matrix, "absolute", 0.5)) == 2
    assert np.count_nonzero(threshold_matrix(matrix, "percentile", 50)) == 4
    assert np.count_nonzero(threshold_matrix(matrix, "density", 1 / 3)) == 2
    assert np.count_nonzero(threshold_matrix(matrix, "top_k", 1)) == 4  # symmetric union
    assert simulate(line_connectome, [], threshold=1)["baseline"]["edge_count"] == 0
    for strategy, value in [
        ("percentile", 101),
        ("density", -0.1),
        ("top_k", 1.5),
        ("absolute", -1),
        ("unknown", 0),
    ]:
        with pytest.raises(ValueError):
            threshold_matrix(matrix, strategy, value)


def test_reproducibility_and_provenance(line_connectome):
    a = simulate(line_connectome, [{"region_id": 1, "fraction_removed": 0.3}])
    b = simulate(line_connectome, [{"region_id": 1, "fraction_removed": 0.3}])
    c = simulate(line_connectome, [{"region_id": 1, "fraction_removed": 0.4}])
    assert a == b
    assert a["provenance"]["input_hash"] == c["provenance"]["input_hash"]
    assert a["provenance"]["config_hash"] != c["provenance"]["config_hash"]
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_noncontiguous_region_ids_preserve_matrix_order(line_connectome):
    for node, new_id in zip(line_connectome["nodes"], [12, 18, 4, 91], strict=True):
        node["id"] = new_id
    result = simulate(line_connectome, [{"region_id": 18, "fraction_removed": 1}])
    assert result["edges"] == [{"source": 4, "target": 91, "weight": 1.0}]


def test_demo_atlases_and_patient_isolation():
    assert len(list_patients()) == 12
    assert len(list_atlases()) == 2
    for atlas in ("demo-64", "demo-96"):
        connectome = get_connectome("DEMO-001", atlas)
        assert validate_connectome(connectome) == connectome
        assert len(connectome["nodes"]) == int(atlas.split("-")[1])
        assert all(
            node["x"] < 0 if node["hemisphere"] == "L" else node["x"] > 0
            for node in connectome["nodes"]
        )
        connectome["nodes"][0]["name"] = "mutated"
        assert get_connectome("DEMO-001", atlas)["nodes"][0]["name"] != "mutated"
    with pytest.raises(ValueError):
        get_connectome("missing")


def test_sensitivity_fraction_bounds_and_effect(line_connectome):
    result = sensitivity(line_connectome, [{"region_id": 1, "fraction_removed": 0.05}])
    assert len(result["variants"]) == 5
    assert result["variants"][0]["regions"][0]["fraction_removed"] == 0
    assert result["region_scores"][0]["score"] > 0
    assert result["variants"][0]["efficiency"] > result["variants"][-1]["efficiency"]


def test_counterfactual_constraints_are_hard(line_connectome):
    regions = [{"region_id": 0, "fraction_removed": 0.2}, {"region_id": 1, "fraction_removed": 0.8}]
    result = counterfactuals(
        line_connectome,
        regions,
        {"minimum_target_coverage": 0.6, "protected_regions": [0], "max_candidates": 3},
    )
    assert result["candidates"]
    assert len(result["candidates"]) <= 3
    for candidate in result["candidates"]:
        assert candidate["target_coverage"] >= 0.6 - 1e-12
        assert candidate["regions"][0]["fraction_removed"] == 0
    infeasible = counterfactuals(
        line_connectome, regions, {"minimum_target_coverage": 0.9, "protected_regions": [0]}
    )
    assert infeasible["candidates"] == []
    assert counterfactuals(line_connectome, [], {})["candidates"] == []
    with pytest.raises(ValueError):
        counterfactuals(line_connectome, regions, {"protected_regions": [999]})

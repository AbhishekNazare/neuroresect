import copy

import numpy as np
import pytest
from neurocore.demo import get_connectome
from neurocore.experiments import (
    fit_fold,
    make_pipeline,
    predict_scenario,
    reproduce_experiment,
    run_experiment,
    synthetic_records,
)
from neurocore.leakage import assert_disjoint_patients, validate_feature_names, validate_records
from neurocore.simulation import simulate


def test_grouped_experiment_reproducible_and_exports(tmp_path):
    result = run_experiment({"n_patients": 24, "folds": 3}, tmp_path)
    assert set(result["models"]) == {"A", "B", "C"}
    seen = []
    for fold in result["folds"]:
        assert not set(fold["train_patient_ids"]) & set(fold["test_patient_ids"])
        seen.extend(fold["test_patient_ids"])
    assert len(seen) == len(set(seen)) == 24
    for model in result["models"].values():
        assert len(model["predictions"]) == 24
        assert all(0 <= p["probability"] <= 1 for p in model["predictions"])
        assert 0 <= model["metrics"]["brier"] <= 1
        for fold, metric in zip(result["folds"], model["fold_metrics"], strict=True):
            assert metric["preprocessing_fit_patient_ids"] == fold["train_patient_ids"]
    assert reproduce_experiment(tmp_path / "experiment.json")["reproduction"]["matches"]


def test_preprocessing_never_sees_held_out_extreme():
    features = np.array([[0.0], [1.0], [2.0], [3.0], [9999.0]])
    fitted, _ = fit_fold(
        make_pipeline("logistic", 42),
        features,
        np.array([0, 1, 0, 1, 0]),
        np.arange(4),
        np.array([4]),
    )
    assert fitted.named_steps["scaler"].mean_[0] == pytest.approx(1.5)


def test_leakage_guards_reject_patient_overlap_outcome_and_duplicates():
    with pytest.raises(ValueError, match="LEAKAGE"):
        assert_disjoint_patients(["p1"], ["p1"])
    with pytest.raises(ValueError, match="LEAKAGE"):
        validate_feature_names(["age", "observed_postoperative_outcome"])
    records = synthetic_records(2)
    duplicate = copy.deepcopy(records[0])
    duplicate["record_id"] = "another-record"
    with pytest.raises(ValueError, match="duplicate feature"):
        validate_records([records[0], duplicate])


def test_prediction_has_real_bootstrap_and_excludes_subject():
    connectome = get_connectome("DEMO-001")
    regions = connectome["actual_resection"]
    result = predict_scenario(connectome, regions, simulate(connectome, regions))
    assert 0 <= result["probability"] <= 1
    interval = result["interval"]
    assert 0 <= interval["lower"] <= interval["upper"] <= 1
    assert interval["iterations"] == len(interval["draw_hashes"]) == 64
    assert "DEMO-001" not in result["provenance"]["training_patient_ids"]
    logit = result["intercept"] + sum(c["value"] for c in result["contributions"])
    assert 1 / (1 + np.exp(-logit)) == pytest.approx(result["probability"])
    with pytest.raises(ValueError, match="weighted"):
        predict_scenario(connectome, regions, simulate(connectome, regions, "binary"))
    altered = copy.deepcopy(connectome)
    altered["matrix"][0][1] += 0.1
    altered["matrix"][1][0] += 0.1
    with pytest.raises(ValueError, match="unchanged"):
        predict_scenario(altered, regions, simulate(altered, regions))


@pytest.mark.parametrize("model", ["random_forest", "svm"])
def test_alternative_estimators_execute(model):
    result = run_experiment({"n_patients": 24, "folds": 2, "model_type": model})
    assert all(len(m["predictions"]) == 24 for m in result["models"].values())

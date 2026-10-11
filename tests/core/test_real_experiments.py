import copy

import numpy as np
import pytest
from neurocore.real_experiments import CATEGORIES, FEATURES, evaluate_real_records


def fixture_records():
    rng = np.random.default_rng(13)
    return [
        {
            "patient_id": f"fixture-{i}",
            "target": i % 2,
            "features": {
                name: ("group-a" if i % 3 else "group-b")
                if name in CATEGORIES
                else float(rng.normal() + i / 100)
                for name in FEATURES["C"]
            },
        }
        for i in range(40)
    ]


def test_real_folds_and_preprocessing_are_patient_separated():
    records = fixture_records()
    report, models = evaluate_real_records(records, folds=4)
    heldout = []
    for fold in report["folds"]:
        assert not set(fold["train_patient_ids"]) & set(fold["test_patient_ids"])
        heldout.extend(fold["test_patient_ids"])
    assert len(heldout) == len(set(heldout)) == 40
    for key, result in report["models"].items():
        numeric = FEATURES[key][len(CATEGORIES) :]
        for fold, values in zip(report["folds"], result["folds"], strict=True):
            expected = np.mean(
                [
                    [row["features"][name] for name in numeric]
                    for row in records
                    if row["patient_id"] in fold["train_patient_ids"]
                ],
                axis=0,
            )
            assert np.allclose(values["numeric_scaler_mean"], expected)
    assert set(models) == {"A", "B", "C"}
    assert all(0 <= row[key] <= 1 for row in report["predictions"] for key in models)


def test_real_training_rejects_duplicate_patients_and_outcome_features():
    records = fixture_records()
    with pytest.raises(ValueError, match="One binary-labelled"):
        evaluate_real_records(records + [records[0]])
    leaked = copy.deepcopy(records)
    leaked[0]["features"]["ILAE_Year1"] = 1
    with pytest.raises(ValueError, match="Unapproved"):
        evaluate_real_records(leaked)


def test_experiment_rejects_changed_cohort_before_training(tmp_path):
    from neurocore.io import write_json
    from neurocore.real_experiments import run_real_experiment

    cohort = write_json(tmp_path / "cohort.json", {})
    config = write_json(
        tmp_path / "config.json",
        {
            "estimator": "logistic",
            "C": 1.0,
            "threshold": 0.5,
            "hyperparameter_search": False,
            "atlas": "Lausanne-36",
            "measure": "Count",
            "tractography": "probabilistic",
            "cohort": str(cohort),
            "cohort_sha256": "incorrect",
        },
    )
    with pytest.raises(ValueError, match="pinned SHA-256"):
        run_real_experiment(config, tmp_path / "results")

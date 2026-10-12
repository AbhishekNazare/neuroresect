import copy

import pytest
from neurocore.experiments import classification_metrics
from neurocore.ideas import sha256
from neurocore.io import write_json
from neurocore.study_reports import export_real_study


def test_export_verifies_metrics_and_never_copies_patient_rows(tmp_path):
    import numpy as np

    y = np.array([0, 1, 0, 1])
    p = np.array([0.2, 0.8, 0.6, 0.4])
    cohort = {
        "subjects": [
            {
                "subject_id": f"private-{i}",
                "target": int(target),
                "eligible": True,
                "group": "surgical_patient",
                "exclusion_reasons": [],
            }
            for i, target in enumerate(y)
        ],
        "dataset_id": "fixture",
        "network_subject_count": 4,
        "network_group_counts": {"healthy_control": 0},
        "eligible_count": 4,
        "class_counts": {"0": 2, "1": 2},
        "atlas": "fixture",
        "measure": "Count",
        "tractography": "probabilistic",
        "resection_input_unit": "fraction",
    }
    cohort_path = write_json(tmp_path / "cohort.json", cohort)
    result = {
        "synthetic": False,
        "cohort_sha256": sha256(cohort_path),
        "predictions": [
            {
                "patient_id": f"private-{i}",
                "target": int(target),
                **dict.fromkeys("ABC", float(p[i])),
            }
            for i, target in enumerate(y)
        ],
        "models": {
            key: {
                "metrics": classification_metrics(y, p),
                "feature_names": ["feature"],
                "coefficients": {"private-coefficient": 3},
            }
            for key in "ABC"
        },
        "endpoint": {},
        "config": {"folds": 2, "seed": 42, "estimator": "logistic", "C": 1, "threshold": 0.5},
        "paired_auc_C_minus_A": {},
        "limitations": [],
        "source_hashes": {},
        "engine_source_hashes": {},
        "runtime": {},
        "feature_version": "fixture",
    }
    result_path = write_json(tmp_path / "results.json", result)
    output = tmp_path / "public.json"
    report = export_real_study(str(result_path), str(cohort_path), str(output))
    assert "private-" not in output.read_text()
    assert len(report["models"]["A"]["calibration"]["predicted"]) > 0
    changed = copy.deepcopy(result)
    changed["models"]["A"]["metrics"]["roc_auc"] = 0
    write_json(result_path, changed)
    with pytest.raises(ValueError, match="Stored metrics"):
        export_real_study(str(result_path), str(cohort_path), str(output))
    write_json(result_path, result)
    cohort["eligible_count"] = 99
    write_json(cohort_path, cohort)
    with pytest.raises(ValueError, match="verified cohort"):
        export_real_study(str(result_path), str(cohort_path), str(output))

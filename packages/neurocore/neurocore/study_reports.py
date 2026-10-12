"""Export verified aggregate study reports without subject IDs or model binaries."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import precision_recall_curve, roc_curve

from neurocore.experiments import classification_metrics
from neurocore.ideas import sha256
from neurocore.io import read_json, write_json


def export_real_study(results_path: str, cohort_path: str, output: str) -> dict:
    result, cohort = read_json(results_path), read_json(cohort_path)
    if result.get("synthetic") is not False or result["cohort_sha256"] != sha256(Path(cohort_path)):
        raise ValueError("Report must come from a real experiment and its verified cohort")
    config = result["config"]
    if (
        config.get("estimator") != "logistic"
        or config.get("C") != 1
        or config.get("threshold") != 0.5
    ):
        raise ValueError("This report supports the fixed logistic C=1, threshold=0.5 baseline")
    eligible = {row["subject_id"]: row["target"] for row in cohort["subjects"] if row["eligible"]}
    predictions = result["predictions"]
    if len(predictions) != len(eligible) or {row["patient_id"] for row in predictions} != set(
        eligible
    ):
        raise ValueError("Predictions do not match the eligible cohort")
    if any(row["target"] != eligible[row["patient_id"]] for row in predictions):
        raise ValueError("Prediction targets differ from cohort outcomes")
    y = np.asarray([row["target"] for row in predictions])
    models = {}
    names = {
        "A": "Clinical and resection",
        "B": "Add preoperative networks",
        "C": "Add virtual resection",
    }
    for key in ("A", "B", "C"):
        probability = np.asarray([row[key] for row in predictions])
        metrics = classification_metrics(y, probability)
        for metric, value in metrics.items():
            stored = result["models"][key]["metrics"][metric]
            if value is None or stored is None or not np.isclose(value, stored, rtol=0, atol=1e-12):
                raise ValueError("Stored metrics differ from held-out predictions")
        fpr, tpr, _ = roc_curve(y, probability)
        precision, recall, _ = precision_recall_curve(y, probability)
        observed, predicted = calibration_curve(y, probability, n_bins=5, strategy="quantile")
        model = result["models"][key]
        models[key] = {
            "name": names[key],
            "feature_set": model["feature_names"],
            "metrics": metrics,
            "roc_curve": {"fpr": fpr.tolist(), "tpr": tpr.tolist()},
            "precision_recall_curve": {"recall": recall.tolist(), "precision": precision.tolist()},
            "calibration": {
                "predicted": predicted.tolist(),
                "observed": observed.tolist(),
            },
        }
    surgical = [row for row in cohort["subjects"] if row["group"] == "surgical_patient"]
    report = {
        "id": "ideas-year1-baseline-v1",
        "name": "IDEAS II · first-year outcome baseline",
        "synthetic": False,
        "report_kind": "saved_aggregate_research_result",
        "dataset_id": cohort["dataset_id"],
        "endpoint": result["endpoint"],
        "cohort": {
            "network_subjects": cohort["network_subject_count"],
            "surgical_patients": len(surgical),
            "healthy_controls": cohort["network_group_counts"]["healthy_control"],
            "eligible_patients": cohort["eligible_count"],
            "class_counts": cohort["class_counts"],
            "surgical_exclusions": {
                reason: sum(reason in row["exclusion_reasons"] for row in surgical)
                for reason in sorted({r for row in surgical for r in row["exclusion_reasons"]})
            },
        },
        "methods": {
            "atlas": cohort["atlas"],
            "measure": cohort["measure"],
            "tractography": cohort["tractography"],
            "folds": result["config"]["folds"],
            "seed": result["config"]["seed"],
            "estimator": "Logistic regression, C=1",
            "threshold": 0.5,
            "preprocessing": "Imputation, encoding and scaling fitted within training folds",
            "resection_input_unit": cohort["resection_input_unit"],
        },
        "models": models,
        "paired_auc_C_minus_A": result["paired_auc_C_minus_A"],
        "limitations": result["limitations"],
        "provenance": {
            "cohort_sha256": result["cohort_sha256"],
            "result_sha256": sha256(Path(results_path)),
            "source_hashes": result["source_hashes"],
            "engine_source_hashes": result["engine_source_hashes"],
            "runtime": result["runtime"],
            "feature_version": result["feature_version"],
        },
    }
    write_json(output, report)
    return report

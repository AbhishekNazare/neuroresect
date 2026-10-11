"""Pre-specified retrospective models on the explicitly joined IDEAS cohort."""

from __future__ import annotations

import csv
import platform
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from neurocore.experiments import classification_metrics
from neurocore.ideas import read_network_matrix, sha256
from neurocore.ideas_cohort import ENDPOINT, map_outcome
from neurocore.io import read_json, write_json
from neurocore.leakage import assert_disjoint_patients
from neurocore.metrics import global_metrics
from neurocore.provenance import content_hash
from neurocore.simulation import resect_matrix

CATEGORIES = ("Sex", "Binned_Onset_Age", "Binned_Age_at_Scan")
CLINICAL = (
    "Number_ASMs",
    "resection_fraction_sum",
    "resection_region_fraction",
    "resection_left_fraction",
)
BASELINE = tuple(
    f"baseline_{name}"
    for name in ("efficiency", "density", "clustering", "modularity", "mean_strength")
)
DELTA = (
    "post_efficiency",
    "post_clustering",
    "post_modularity",
    "delta_efficiency",
    "delta_modularity",
    "connectivity_loss",
)
FEATURES = {
    "A": CATEGORIES + CLINICAL,
    "B": CATEGORIES + CLINICAL + BASELINE,
    "C": CATEGORIES + CLINICAL + BASELINE + DELTA,
}


def real_pipeline(n_features: int, seed: int) -> Pipeline:
    numeric = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocess = ColumnTransformer(
        [
            ("categories", categorical, list(range(len(CATEGORIES)))),
            ("numeric", numeric, list(range(len(CATEGORIES), n_features))),
        ]
    )
    return Pipeline(
        [
            ("preprocess", preprocess),
            ("classifier", LogisticRegression(C=1.0, max_iter=10000, random_state=seed)),
        ]
    )


def real_records(cohort: dict) -> list[dict]:
    if (
        cohort.get("atlas") != "Lausanne-36"
        or cohort.get("measure") != "Count"
        or cohort.get("tractography") != "probabilistic"
        or cohort.get("endpoint") != ENDPOINT
        or cohort.get("region_name_mapping_verified") is not True
    ):
        raise ValueError("Cohort is incompatible with the pre-specified experiment")
    archive = Path(cohort["archive_path"])
    if sha256(archive) != cohort["source_hashes"]["network_archive"]:
        raise ValueError("Network archive no longer matches cohort provenance")
    labels = cohort["region_labels"]
    records, seen = [], set()
    for row in cohort["subjects"]:
        if not row["eligible"]:
            continue
        identifier = row["subject_id"]
        if identifier in seen or row["group"] != "surgical_patient" or row["target"] not in (0, 1):
            raise ValueError("Eligible patients must be unique surgical cases with binary outcomes")
        if row.get("exclusion_reasons") or map_outcome(row["source_outcome"]) != row["target"]:
            raise ValueError("Eligible row contradicts its source outcome or exclusions")
        seen.add(identifier)
        source = read_network_matrix(archive, row["matrix_member"])
        if (
            source["subject_id"] != identifier
            or source["source_csv_sha256"] != row["matrix_csv_sha256"]
        ):
            raise ValueError("Matrix identity differs from audited cohort")
        matrix = np.asarray(source["matrix"])
        fractions = np.asarray(row["resection_fractions"], dtype=float)
        if (
            len(labels) != len(matrix)
            or fractions.shape != (len(matrix),)
            or not np.isfinite(fractions).all()
        ):
            raise ValueError("Resection/atlas dimensions or finite values invalid")
        if (fractions < 0).any() or (fractions > 1).any() or fractions.sum() == 0:
            raise ValueError("Invalid or empty resection")
        after = resect_matrix(
            matrix,
            [{"region_id": i, "fraction_removed": float(f)} for i, f in enumerate(fractions)],
            list(range(len(matrix))),
        )
        baseline, post = global_metrics(matrix), global_metrics(after)
        clinical = row["clinical"]
        features = {name: clinical[name] for name in CATEGORIES}
        features.update(
            {
                "Number_ASMs": float(clinical["Number_ASMs"]),
                "resection_fraction_sum": float(fractions.sum()),
                "resection_region_fraction": float(np.mean(fractions > 0)),
                "resection_left_fraction": float(
                    sum(
                        f
                        for label, f in zip(labels, fractions, strict=True)
                        if label.startswith(("Left-", "l."))
                    )
                    / fractions.sum()
                ),
                "baseline_mean_strength": float(matrix.sum(axis=1).mean()),
                "connectivity_loss": 1.0 - float(after.sum()) / float(matrix.sum())
                if matrix.sum()
                else 0.0,
            }
        )
        for metric in ("efficiency", "density", "clustering", "modularity"):
            features[f"baseline_{metric}"] = baseline[metric]
        for metric in ("efficiency", "clustering", "modularity"):
            features[f"post_{metric}"] = post[metric]
        for metric in ("efficiency", "modularity"):
            features[f"delta_{metric}"] = post[metric] - baseline[metric]
        if set(features) != set(FEATURES["C"]):
            raise ValueError("Real-data feature whitelist mismatch")
        records.append({"patient_id": identifier, "target": row["target"], "features": features})
    if len(records) != cohort["eligible_count"]:
        raise ValueError("Cohort eligible count mismatch")
    return records


def evaluate_real_records(records: list[dict], folds: int = 5, seed: int = 42) -> tuple[dict, dict]:
    ids = np.array([row["patient_id"] for row in records])
    y = np.array([row["target"] for row in records])
    if len(set(ids)) != len(ids) or any(
        type(row["target"]) is not int or row["target"] not in (0, 1) for row in records
    ):
        raise ValueError("One binary-labelled row per patient is required")
    if folds < 2 or min(np.bincount(y, minlength=2)) < folds:
        raise ValueError("Each class needs at least folds patients")
    for row in records:
        if set(row["features"]) != set(FEATURES["C"]):
            raise ValueError("Unapproved or missing real-data features")
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    splits = list(splitter.split(np.zeros((len(y), 1)), y, ids))
    fold_info, assignment = [], np.zeros(len(y), dtype=int)
    for index, (train, test) in enumerate(splits):
        assert_disjoint_patients(ids[train], ids[test])
        if len(np.unique(y[train])) != 2 or len(np.unique(y[test])) != 2:
            raise ValueError("Each training and held-out fold must contain both classes")
        assignment[test] += 1
        fold_info.append(
            {
                "fold": index + 1,
                "train_patient_ids": ids[train].tolist(),
                "test_patient_ids": ids[test].tolist(),
            }
        )
    if not (assignment == 1).all():
        raise ValueError("Each patient must be held out exactly once")
    reports: dict[str, dict] = {}
    models: dict[str, Pipeline] = {}
    predictions: dict[str, np.ndarray] = {}
    for key, names in FEATURES.items():
        x = np.array([[row["features"][name] for name in names] for row in records], dtype=object)
        oof = np.full(len(y), np.nan)
        fold_results = []
        for index, (train, test) in enumerate(splits):
            fitted = real_pipeline(len(names), seed).fit(x[train], y[train])
            oof[test] = fitted.predict_proba(x[test])[:, 1]
            fold_results.append(
                {
                    "fold": index + 1,
                    "metrics": classification_metrics(y[test], oof[test]),
                    "numeric_scaler_mean": fitted.named_steps["preprocess"]
                    .named_transformers_["numeric"]
                    .named_steps["scaler"]
                    .mean_.tolist(),
                }
            )
        if not np.isfinite(oof).all():
            raise ValueError("Nonfinite held-out predictions")
        observed, predicted = calibration_curve(y, oof, n_bins=5, strategy="quantile")
        final = real_pipeline(len(names), seed).fit(x, y)
        reports[key] = {
            "feature_names": list(names),
            "metrics": classification_metrics(y, oof),
            "folds": fold_results,
            "reliability": {
                "mean_predicted": predicted.tolist(),
                "observed_fraction": observed.tolist(),
            },
            "coefficients": dict(
                zip(
                    final.named_steps["preprocess"].get_feature_names_out().tolist(),
                    final.named_steps["classifier"].coef_[0].tolist(),
                    strict=True,
                )
            ),
        }
        predictions[key] = oof
        models[key] = final
    # Paired resampling of fixed held-out predictions, not a model-refitting interval.
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(1000):
        sample = rng.integers(0, len(y), len(y))
        if len(np.unique(y[sample])) == 2:
            differences.append(
                roc_auc_score(y[sample], predictions["C"][sample])
                - roc_auc_score(y[sample], predictions["A"][sample])
            )
    report = {
        "models": reports,
        "folds": fold_info,
        "patient_count": len(ids),
        "class_counts": {str(k): int((y == k).sum()) for k in (0, 1)},
        "paired_auc_C_minus_A": {
            "estimate": reports["C"]["metrics"]["roc_auc"] - reports["A"]["metrics"]["roc_auc"],
            "conditional_95_percent_interval": np.quantile(differences, [0.025, 0.975]).tolist(),
            "method": "1000 paired patient resamples of fixed out-of-fold predictions; no model refitting",
        },
        "predictions": [
            {
                "patient_id": identifier,
                "target": int(y[i]),
                **{key: float(predictions[key][i]) for key in FEATURES},
            }
            for i, identifier in enumerate(ids)
        ],
    }
    return report, models


def run_real_experiment(config_path: str | Path, output: str | Path) -> dict:
    config = read_json(config_path)
    if (
        config.get("estimator") != "logistic"
        or config.get("C") != 1.0
        or config.get("threshold") != 0.5
        or config.get("hyperparameter_search") is not False
        or config.get("atlas") != "Lausanne-36"
        or config.get("measure") != "Count"
        or config.get("tractography") != "probabilistic"
    ):
        raise ValueError("Unsupported real-data baseline configuration")
    if sha256(Path(config["cohort"])) != config.get("cohort_sha256"):
        raise ValueError("Cohort differs from the experiment's pinned SHA-256")
    cohort = read_json(config["cohort"])
    if (
        config.get("categorical_features") != list(CATEGORIES)
        or config.get("numeric_clinical_features") != ["Number_ASMs"]
        or config.get("resection_input_unit") != cohort.get("resection_input_unit")
        or config.get("endpoint") != "ILAE_Year1: 1 versus 2–6; NA excluded"
    ):
        raise ValueError("Configuration does not match the frozen cohort/feature protocol")
    records = real_records(cohort)
    report, models = evaluate_real_records(records, config["folds"], config["seed"])
    report.update(
        {
            "config": config,
            "endpoint": cohort["endpoint"],
            "synthetic": False,
            "cohort_sha256": sha256(Path(config["cohort"])),
            "source_hashes": cohort["source_hashes"],
            "feature_version": "ideas-categorical-graph-v1",
            "runtime": {
                "python": platform.python_version(),
                **{
                    name: version(name)
                    for name in ("numpy", "scipy", "scikit-learn", "networkx", "openpyxl")
                },
            },
            "engine_source_hashes": {
                name: sha256(Path(__file__).with_name(name))
                for name in ("real_experiments.py", "metrics.py", "simulation.py", "validation.py")
            },
            "feature_records_hash": content_hash(records),
            "limitations": [
                "Internal retrospective cross-validation; no independent external validation.",
                "Actual postoperative resections and explicitly configured fractional-unit interpretation.",
                "Probabilities are not recalibrated; reliability curves assess held-out calibration only.",
                "Coefficient magnitudes are associations, not causal effects or surgical recommendations.",
                "No patient MRI coordinates or surface registration; models are not served by the workstation.",
            ],
        }
    )
    root = Path(output)
    write_json(root / "results.json", report)
    write_json(root / "feature-records.json", records)
    write_json(root / "config.json", config)
    with (root / "predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["patient_id", "target", "A", "B", "C"])
        writer.writeheader()
        writer.writerows(report["predictions"])
    joblib.dump(
        {
            "models": models,
            "feature_names": FEATURES,
            "feature_version": report["feature_version"],
            "cohort_sha256": report["cohort_sha256"],
            "endpoint": ENDPOINT,
        },
        root / "models.joblib",
    )
    return report

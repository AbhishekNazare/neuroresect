# Reproducible outcome experiments

Run a study independently from the UI:

```sh
.venv/bin/neuroresect experiment configs/experiments/synthetic-abc.json --output artifacts/study
.venv/bin/neuroresect reproduce artifacts/study/experiment.json --output artifacts/reproduced
```

The output contains `experiment.json`, `config.json`, `provenance.json`, `metrics.json`, `predictions.csv`, `feature_importance.csv`, and `models.joblib`. The serialized models are final fits on the complete generated cohort; reported validation metrics come exclusively from held-out folds. Only load joblib files you generated or otherwise trust.

Three feature sets share the exact patient splits:

| Model | Inputs |
| --- | --- |
| A | Age, synthetic sex variable, epilepsy duration, resection fractions |
| B | A plus preoperative graph metrics |
| C | B plus simulated post-resection graph and disruption features |

Supported estimators are logistic regression, random forest, and support vector machine. XGBoost is an optional Python-core extension when installed, and is not exposed as an installed default in the API. Default examples use logistic regression. The versioned synthetic outcome generator is recorded in provenance.

A `StratifiedGroupKFold` split separates patient IDs. Each fold fits its own imputer, scaler, and estimator. Exports include fold memberships, preprocessing fit IDs, per-fold metrics, out-of-fold probabilities, ROC/PR curves, reliability diagnostics, and available coefficient/importance summaries. Reproduction compares scientific outputs and dataset hashes; runtime and git metadata may differ.

The scenario predictor uses a separate fit with the selected participant excluded from every training and bootstrap sample. It reports 64 patient-resampled refits and the 2.5th/97.5th percentiles. Explanations are exact standardized linear log-odds contributions for the logistic model. They are not SHAP values or causal effects. Calibration is explicitly not externally validated.

The bundled cohort has no clinical evidentiary value. Imports can be simulated but cannot be scored by the synthetic model. Real cohort training, endpoint harmonization, registered anatomical assets, and external validation remain additional research work.

# ADR 002: patient-separated experiments and honest uncertainty

Status: accepted.

All records from one patient stay together during validation. A/B/C feature-set comparisons share folds and seeds. Imputation and scaling are fitted inside each training fold; the held-out fold only receives transforms. Group overlap, inconsistent labels, target-derived inputs, and degenerate folds must fail before a misleading result is reported.

This follows the [scikit-learn grouped cross-validation contract](https://scikit-learn.org/stable/modules/cross_validation). Calibration must never fit on the fold used to evaluate it. An uncalibrated prediction is labeled as such.

Prediction intervals are empirical bootstrap refit intervals, with method and replicate count exposed; they are not guarantees for an individual patient. Model coefficients are explanations in log-odds units, not percentage-point causal effects.

The bundled synthetic cohort tests the software pipeline. Its AUC is never evidence of clinical effectiveness. A real study needs dataset governance, a prespecified endpoint and follow-up interval, missing-data analysis, external validation, and independent scientific review.

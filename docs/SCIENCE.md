# Scientific methods and interpretation

## What the simulation means

A connectome is a symmetric, nonnegative strength matrix with zero diagonal and an explicitly ordered atlas. Region metadata and matrix dimensions must agree; invalid values, unknown regions, duplicates, and malformed resection fractions are rejected.

For a removal fraction `f_i`, weighted resection computes:

```text
W′ij = Wij (1 − fi) (1 − fj)
```

An edge of strength 0.8 between regions removed by 40% and 20% becomes `0.8 × 0.6 × 0.8 = 0.384`. Inputs are not modified. Binary removal zeros incident edges for fractions at least 0.5. Both strategies retain the original node universe.

This operation approximates network disruption. It does not simulate electrical seizure activity, tissue deformation, recovery, connectivity rewiring, or individual neurological function.

## Metrics

Positive strengths become distances `1 / weight`. Global efficiency is the sum of reciprocal finite shortest-path distances divided by `N(N−1)`. Unreachable pairs contribute zero. Density is undirected edge count divided by `N(N−1)/2`; partial weakening need not change density. Weighted clustering and modularity describe topology; neither is a direct clinical outcome measure. Undefined quantities use JSON null.

Connectivity loss is `1 − sum(W′) / sum(W)` with zero loss for an empty baseline graph. Deltas are `post − baseline`; relative deltas are undefined when baseline is zero. Hub criteria and algorithm versions belong to provenance rather than hidden UI constants.

Changing the viewer threshold only changes drawn edges. It cannot silently change reported scientific metrics.

## Sensitivity and counterfactuals

Fraction perturbations vary selected regions' removal fractions and repeat the same analysis. Fraction offsets are percentage points, not millimeters. Per-region sensitivity measures graph response and is labeled separately from outcome-probability uncertainty.

Counterfactuals explore feasible removal patterns subject to target coverage and protected regions. Their objective ranks graph trade-offs; a higher score is not a surgical recommendation. An empty feasible set is a valid result. Target coverage is a region-fraction surrogate, not measured epileptogenic tissue coverage.

## Outcome experiments

The core research comparison is clinical/resection features (A), plus baseline graph features (B), plus simulated network-change features (C). Shared patient-grouped folds make these comparisons interpretable. All transformations are fitted on the training patients only. Report ROC-AUC, precision-recall performance, balanced accuracy, sensitivity/specificity, and Brier score where mathematically defined.

Bootstrap refits sample training patients with replacement and fit a new pipeline per replicate. Quantiles describe variability under this procedure. They do not guarantee individual outcome coverage or substitute for calibration. Feature contributions must include their units; log-odds coefficients are not changes in clinical probability or causal effects.

Bundled outcomes are generated synthetic labels. Synthetic metrics validate execution and reproducibility only. Real research requires a documented endpoint (e.g. outcome scale and follow-up interval), approved data, confounding analysis, missing-data handling, held-out external validation, and domain review.

## Provenance

Results capture input hashes, dataset/atlas IDs, simulation method, threshold, feature and engine versions, seed where applicable, and code version when available. An exported result must identify its scenario. Fixed inputs and seeds reproduce numerical outputs within documented numerical tolerance; timestamps and run IDs need not match.

References: [NetworkX weighted-efficiency caveat](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.efficiency_measures.global_efficiency.html), [scikit-learn grouped validation](https://scikit-learn.org/stable/modules/cross_validation).

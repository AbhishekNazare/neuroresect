# Joining IDEAS clinical outcomes, labels and resections

The five companion files supplied by the user have been acquired. [The manifest](../configs/datasets/ideas-companions-manifest.json) pins their initial locally computed SHA-256 fingerprints. Files and patient-level derived artifacts stay outside Git.

| Figshare file ID | Source |
| --- | --- |
| 46131036 | Metadata_Release_Anon.csv |
| 48408520 | Metadata_Controls_Release.csv |
| 48408532 | readme_metadata.pdf |
| 67695237 | IDEAS_regionNames.xlsx |
| 46131042 | table_resected.csv |

```sh
.venv/bin/neuroresect dataset-download configs/datasets/ideas-companions-manifest.json \
  --destination data/ideas/companions --max-bytes 1000000
.venv/bin/neuroresect ideas-cohort \
  --patients data/ideas/companions/46131036 \
  --controls data/ideas/companions/48408520 \
  --labels data/ideas/companions/67695237 \
  --resections data/ideas/companions/46131042 \
  --archive data/ideas/networks/probabilistic_tractography.zip \
  --resection-unit fraction --output data/ideas/cohort-year1.json
```

## Explicit mapping decisions

- Numeric clinical IDs join to BIDS `sub-{ID}`. Subject/control membership comes from the respective source tables, never inferred from the ID's magnitude.
- The patient CSV has 443 rows but 442 unique IDs: patient 209 occurs twice with identical values. Exact duplicates are collapsed and reported; conflicting duplicates fail the import.
- The `scale36` spreadsheet has 82 ordered region labels. Strip the source's surrounding single quotes and map resection `ctx-lh-X` / `ctx-rh-X` names to `l.X` / `r.X`. Require exact one-to-one label-set agreement and reorder by workbook order. Subcortical labels remain unchanged.
- This adapter supports **non-dilated Lausanne-36 Count** only. The 82-region resection table is not silently applied to other scales or dilated variants.
- The website calls the resection entries percentages, but the supplied numeric values lie in `[0,1]`, including fully resected values of `1`. The first analysis explicitly interprets them as **fractions**, with no division by 100. This unit interpretation is recorded in the cohort and remains an assumption to confirm against imaging/source methods before anatomical or clinical validation.
- Twelve source resection columns contain `NaN`. Any missing regional value makes that subject's resection vector incomplete; missing entries are never zero-filled. One otherwise eligible network patient is excluded for this reason.
- The clinical dictionary describes `ILAE_Year?` as yearly outcomes and `NA` as unavailable. The first experiment uses **reported year-one class 1 versus classes 2–6**, not freedom from disabling seizures (which could use a different grouping), cumulative freedom since surgery, or a last-available-follow-up endpoint. Class definitions follow the [ILAE outcome classification](https://www.ilae.org/files/ilaeGuideline/New-Classification-of-OutcomeFollowing-Epilepsy-Surgery-2001.pdf).
- Preserve source age bins as categories. Do not reconstruct exact age or epilepsy duration from bins. Outcome fields, histopathology and free-text surgical notes are excluded from the feature whitelist.

## Observed cohort

| Stage | Subjects |
| --- | ---: |
| Network archive | 288 |
| Matched surgical patients | 191 |
| Matched healthy controls, excluded from outcome training | 97 |
| Surgical patients missing year-one outcome | 8 |
| Additional incomplete resection | 1 |
| Eligible retrospective analysis cohort | **182** |
| Class 1 / classes 2–6 | **101 / 81** |

Exclusion reasons may overlap. The source-level duplicate collapse and each excluded network subject are retained in the cohort report. Every selected matrix is CRC-checked and numerically validated; source hashes and explicit matrix-member paths are saved.

Region-name correspondence is verified. This does **not** provide patient MRI coordinates, cortical surfaces, imaging registration or prospective clinical validation. The headless graph analysis requires no invented coordinates. Actual postoperative resection fractions make this a retrospective analysis.

The [first experiment configuration](../configs/experiments/ideas-year1.json) is fixed before fitting: probabilistic Count, five patient-separated folds, seed 42, logistic regression with C=1, no hyperparameter search, and a 0.5 decision threshold. A/B/C comparisons must use the same cohort and held-out folds. The first fit and held-out results are documented in [real experiments](REAL_EXPERIMENTS.md).

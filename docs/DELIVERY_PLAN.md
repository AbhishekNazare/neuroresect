# NeuroResect delivery plan

This plan implements the HLD/LLD as a runnable research prototype. Original designs remain in [HLD.txt](HLD.txt) and [LLD.txt](LLD.txt). Synthetic data and synthetic atlas geometry are explicitly identified; no real clinical performance claim is possible without an approved dataset and external validation.

| Phase | Feature branch | Pull request | Acceptance criteria |
| --- | --- | --- | --- |
| 01 | `feat/research-foundations` | Research foundations: architecture, contracts, and delivery roadmap | Installable monorepo, documented scientific conventions and API contracts |
| 02 | `feat/connectome-engine` | Inside the connectome: deterministic virtual resection engine | Validated matrices; weighted/binary resection; graph metrics; sensitivity; constrained search; scientific tests |
| 03 | `feat/outcome-experiments` | Evidence with uncertainty: patient-separated outcome experiments | A/B/C comparisons, grouped validation, fold-local preprocessing, bootstrap intervals, artifact export; leakage tests |
| 04 | `feat/research-api` | From scenario to evidence: persistent research API | Patients, atlases, scenarios, async jobs, simulation, provenance, imports, exports; API integration tests |
| 05 | `feat/brain-workstation` | Explore the living network: interactive 3D research workstation | Interactive regions and edges, resection editor, before/after, comparison, sensitivity, experiments, provenance; responsive and accessible UI |
| 06 | `feat/release-toolkit` | Ready for discovery: reproducible launch, CI, and illustrated field guide | Docker and local setup, CI, end-to-end checks, diagrams, screenshots, scientific limitations, polished README |

Each phase receives focused conventional commits. PRs include behavior, scientific assumptions, verification, and known limitations. Dependent PRs are stacked if they are left open for review. The user authorized merging each verified phase into main. Preserve merge commits and feature branches; no force pushes or fabricated backdated history.

## Release boundary

The release includes a functioning DWI-connectome workflow on synthetic data plus validated JSON/CSV import interfaces. Real tract intersection, raw MRI preprocessing, named atlas meshes, lab identity management, prospective clinical validation, and MEG/fMRI/HGM pipelines require additional assets or deployment context. Extension contracts and explicit capability metadata distinguish these from implemented features.

## Scientific acceptance

- Strength weights are nonnegative; shortest-path distance is reciprocal positive strength.
- Weighted resection scales both endpoints: `W'[i,j] = W[i,j] * (1-f[i]) * (1-f[j])`.
- Preserve original atlas indexing for comparison. Binary removal uses zero incident edges, and reports the retained-node convention.
- Disconnected pairs contribute zero to efficiency; undefined metrics serialize as null.
- Display thresholds are separate from scientific thresholds.
- Simulated post-resection features use preoperative connectivity and resection definitions, never observed postoperative outcome variables.
- Synthetic outcome-model metrics demonstrate software only. They do not establish clinical predictive utility.
- All displayed predictions include model, feature version, dataset, scenario, uncertainty method, and research labeling.


## Real-data completion programme

The original prototype phases are merged. The remaining programme is incremental; a merged infrastructure PR does not imply that its dataset-dependent acceptance gate is satisfied.

| Phase | Branch | Acceptance gate | Status |
| --- | --- | --- | --- |
| 07 | `feat/ideas-data-ingestion` | Acquired and audited connectomes, outcomes and resections with reproducible ID joins | Networks and companions acquired; 182 eligible first-year cases joined with explicit exclusions; fractional-unit assumption documented |
| 08 | `feat/anatomical-atlas-pipeline` | One actual patient with verified atlas order, geometry and resection alignment | Awaiting derivative assets |
| 09 | `feat/real-cohort-outcomes` | Frozen endpoint, leakage-controlled real cohort A/B/C evaluations and reproducible artifacts | First logistic A/B/C baseline evaluated on 182 patients; no demonstrated improvement; external validation outstanding |
| 10 | `feat/research-model-registry` | Versioned compatible real model serving with calibrated evaluation and explanations | Pending real experiments |
| 11 | `feat/anatomical-scenarios` | Physical mask edits, constraints and sensitivity verified against anatomy | Pending aligned imaging |
| 12 | `feat/patient-anatomy-workspace` | Complete real-data workflow and inspectable intermediate results | Pending real anatomy/model contracts |
| 13 | `feat/lab-deployment` | Identity, migrations, durable recovery, object storage and backup/restore | Pending implementation and deployment configuration |
| 14 | `feat/multimodal-research` | Actual matched modalities and evaluated fusion, not placeholders | Requires suitable source data |
| 15 | `feat/research-release-validation` | Requirements traceability, reproducible real results and documented independent validation status | Pending prior gates |

[IDEAS integration](IDEAS_INTEGRATION.md) records acquisition commands, evidence and current blockers. Independent clinical validation is an evidence requirement, not a property established by software tests.

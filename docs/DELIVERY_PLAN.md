# NeuroResect delivery plan

This plan implements the HLD/LLD as a runnable research prototype. Original designs remain in [HLD.txt](HLD.txt) and [LLD.txt](LLD.txt). Synthetic data and synthetic atlas geometry are explicitly identified; no real clinical performance claim is possible without an approved dataset and external validation.

| Phase | Feature branch | Pull request | Acceptance criteria |
| --- | --- | --- | --- |
| 01 | `feat/research-foundations` | Research foundations: architecture, contracts, and delivery roadmap | Installable monorepo, documented scientific conventions and API contracts |
| 02 | `feat/connectome-engine` | Inside the connectome: deterministic virtual resection engine | Validated matrices; weighted/binary resection; graph metrics; sensitivity; constrained search; scientific tests |
| 03 | `feat/research-api` | From scenario to evidence: persistent research API | Patients, atlases, scenarios, async jobs, simulation, provenance, imports, exports; API integration tests |
| 04 | `feat/outcome-experiments` | Evidence with uncertainty: patient-separated outcome experiments | A/B/C comparisons, grouped validation, fold-local preprocessing, bootstrap intervals, artifact export; leakage tests |
| 05 | `feat/brain-workstation` | Explore the living network: interactive 3D research workstation | Interactive regions and edges, resection editor, before/after, comparison, sensitivity, experiments, provenance; responsive and accessible UI |
| 06 | `feat/release-toolkit` | Ready for discovery: reproducible launch, CI, and illustrated field guide | Docker and local setup, CI, end-to-end checks, diagrams, screenshots, scientific limitations, polished README |

Each phase receives focused conventional commits. PRs include behavior, scientific assumptions, verification, and known limitations. Dependent PRs are stacked if they are left open for review. Merging is subject to the user's workflow preference; no force pushes or fabricated backdated history.

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

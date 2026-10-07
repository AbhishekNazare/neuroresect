# Contributing to NeuroResect

Read [the delivery plan](docs/DELIVERY_PLAN.md), [API contract](docs/API_CONTRACT.md), and [architecture decisions](docs/adr) before changing interfaces. Preserve the source HLD/LLD; document deviations in an ADR.

Use small feature branches and conventional commits (`feat`, `fix`, `test`, `docs`, `chore`). PR titles describe the capability, not a vague update. Describe the final behavior, evidence, and limitations. Do not combine clinical data or secrets with source commits.

Scientific changes need known-graph examples, deterministic behavior, input-validation coverage, and recorded algorithm versions. ML changes need patient-overlap checks and preprocessing inside folds. UI work needs loading, empty, error, keyboard, and reduced-motion behavior. A screenshot alone does not establish correctness.

Run Python lint and tests, TypeScript checks, production build, and relevant end-to-end tests before requesting review. See the README for exact setup commands once all implementation phases are present.

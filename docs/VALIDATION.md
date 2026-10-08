# Validation record

The local release checks passed on macOS ARM64 with Python 3.14.4 and Node 25.5.0. The supported container/CI Node runtime is 24 LTS. `requirements.lock` and `package-lock.json` record the exact dependency versions.

| Check | Local evidence |
| --- | --- |
| Scientific and API suite | 59 tests passed |
| Python lint | Ruff passed |
| Python static types | 24 source files passed mypy |
| Frontend types | TypeScript passed |
| Production frontend | Next.js production build passed |
| Browser workflows | 3 Playwright tests passed against actual FastAPI computations |
| Study reproducibility | Dataset hash, folds, and scientific outputs matched |
| Container configuration | `docker compose config --quiet` passed |
| Dependency audit | npm reported 0 vulnerabilities at install time |

The browser workflows cover simulation, prediction/bootstrap output, export, stale-result invalidation, patient switching, sensitivity, constrained alternatives, A/B/C experiments, mobile width, keyboard help, and explicit API failure. Screenshots in `docs/assets` were captured from the running application with `scripts/capture-workstation.mjs`.

GitHub Actions validates on Linux, builds both container images, starts PostgreSQL/Redis/Celery/API/web, and exercises an actual queued simulation plus persisted export through `scripts/smoke_api.py`. See the workflow run for the authoritative remote result. Docker was installed but its daemon was not running in the local development environment; a Compose configuration check alone is not a container-runtime test.

Two upstream deprecation notices are currently expected: Starlette's HTTPX-based test client and scikit-learn's `SVC(probability=True)`. They do not fail validation; versions are pinned. Follow-up upgrades should migrate these interfaces with equivalent validation behavior.

## Limits of these checks

Passing software tests does not validate anatomical accuracy, clinical performance, or outcome calibration. The synthetic benchmark is not a medical study. No formal cross-device frame-rate or production-load benchmark has been established. Performance targets in the source LLD are targets, not measured guarantees.

# Development and operations

## Local workflow

Use Python 3.14 (the pinned validation runtime), Node.js 24 LTS, and npm. From the repository root:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Run the API and web server in separate terminals:

```sh
.venv/bin/uvicorn neuroresect_api.main:app --reload --host 127.0.0.1 --port 8000
```

```sh
npm run dev
```

Open http://localhost:3000 and http://localhost:8000/docs. Next proxies API requests on the same origin. Set `API_URL` **before building** to change the API destination: Next rewrites are resolved at build time.

SQLite state is stored under ignored `data/`. Local jobs use one API process. For multi-process execution, use Celery and PostgreSQL through Compose.

## Container workflow

```sh
docker compose up --build
```

The services are web, API, worker, PostgreSQL, and Redis. API health gates worker/web startup. Named volumes persist PostgreSQL and Redis state. `docker compose down` stops services while preserving data. Do not remove volumes unless you intend to delete local research records.

For an exact source revision in container provenance, build with `NEURORESECT_GIT_COMMIT` as documented in the README. Model/result artifacts must retain dataset/configuration hashes even when a deployment cannot resolve a git checkout.

## Validation

```sh
.venv/bin/ruff check packages apps/api workers tests
.venv/bin/pytest
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
docker compose config --quiet
```

Browser tests exercise an actual API and rendered workstation. Screenshot captures are supporting visual evidence; numerical and API tests remain the source of correctness checks.

`npm run typecheck` generates Next.js route/environment declarations before checking types. `next-env.d.ts` is generated and ignored, so switching between development and production does not dirty the source checkout.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| API unavailable in the workstation | API is running on port 8000; `API_URL` matched the address when Next started/built |
| `neuroresect_api` or `neurocore` cannot import | Use the project `.venv` and install both editable packages |
| Job fails | Open job error/provenance; invalid inputs are rejected explicitly |
| Running job after development restart | Local unfinished jobs are marked interrupted on API startup; submit again |
| 3D canvas unavailable | Enable browser WebGL; the region list remains an accessible editing path |
| Real-data prediction rejected | Bundled models are trained on synthetic data and intentionally incompatible with clinical use |
| Docker cannot connect | Start your Docker engine; Compose files alone do not start the daemon |

## Research data and deployment

Do not commit source patient data, credentials, raw scans, model binaries from private cohorts, or exported patient artifacts. Demo mode is anonymous. Before deploying with real data, add your organization's authentication, access controls, retention policy, transport/storage encryption, audit policy, and dataset agreements. These are deployment work, not claims made by this prototype.

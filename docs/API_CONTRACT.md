# API implementation contract v1

Base path `/api/v1`. JSON uses snake_case. Errors: `{ "error": { "code": "...", "message": "...", "details": {} } }`.

## Core Python interface

`neurocore.demo.list_patients()` returns patient dictionaries: `id, dataset_id, label, age, sex, epilepsy_duration, modalities` (string array), `available_atlases` (string array), `synthetic` (bool).

`neurocore.demo.list_atlases()` returns atlas dictionaries: `id, name, region_count, synthetic, description`.

`neurocore.demo.get_connectome(patient_id, atlas_id='demo-64')` returns `{patient_id, atlas_id, dataset_id, synthetic, nodes, edges, matrix, actual_resection}`. Nodes: `{id, name, hemisphere, network, x, y, z}`. Edges: `{source, target, weight}`. Actual resection: array `{region_id, fraction_removed}`.

`neurocore.simulation.simulate(connectome, regions, method='weighted', threshold=0.0)` returns JSON-ready `{baseline, post, delta, relative_delta, connectivity_loss, impacted_hubs, hub_damage, removed_edges, nodes, edges, provenance}`. Metric keys include `efficiency, density, clustering, modularity, components, largest_component_fraction, path_length`. Baseline and post refer to global metrics; nodes include calculated strength and hub status. Invalid input raises ValueError.

`neurocore.analysis.sensitivity(connectome, regions, method='weighted')` returns `{variants: [{label, offset, regions, connectivity_loss, efficiency, efficiency_delta}], region_scores: [{region_id, score}], provenance}`.

`neurocore.analysis.counterfactuals(connectome, regions, constraints)` returns `{candidates: [{id, label, regions, target_coverage, connectivity_loss, hub_damage, objective_score, efficiency}], constraints, provenance}`. Constraints: `minimum_target_coverage` (0..1, default .8), `protected_regions` (ID array), `max_candidates` (1..50, default 5). All candidates obey constraints, or the result is empty.

`neurocore.experiments.run_experiment(config, output_dir=None)` returns `{id, name, status, dataset_id, atlas_id, seed, models, folds, provenance}`. `models` contains A/B/C entries with `name, feature_set, metrics, fold_metrics, predictions`. Config supports `name, seed, folds, n_patients, model_type, atlas_id`; available `model_type` values are `logistic`, `random_forest`, `svm`. Include optional xgboost only if dependency installed. `neurocore.experiments.predict_scenario(connectome, regions, simulation)` returns `{probability, interval: {lower,upper,level,method}, model: {id,name,version}, feature_version, synthetic, contributions: [{feature,value}], provenance}`. Bootstrap involves actual patient-resampled refits; no invented confidence intervals.

## HTTP endpoints

- `GET /health` (outside prefix)
- `GET /patients` → patient array; `GET /patients/{id}` → patient
- `GET /atlases` → atlas array
- `GET /patients/{id}/connectome?atlas_id=demo-64` → connectome (matrix may be omitted for UI)
- `GET /scenarios?patient_id=...` → scenario array
- `POST /scenarios` body `{patient_id, atlas_id, label, method, regions}` → scenario `{id, patient_id, atlas_id, label, method, regions, created_at}`
- `POST /scenarios/{id}/simulate` → job `{id,status,progress,stage,result,error}`; accepts `Idempotency-Key`
- `GET /jobs/{id}` → job, status `QUEUED|RUNNING|SUCCEEDED|FAILED`
- `GET /scenarios/{id}/simulation` → saved simulation (404 if absent)
- `POST /scenarios/{id}/predict` → job, result prediction
- `POST /scenarios/{id}/sensitivity` → job, result sensitivity
- `POST /scenarios/{id}/counterfactuals` body constraints → job, result counterfactuals
- `GET /scenarios/{id}/export` → JSON scenario, simulation, prediction, provenance
- `GET /experiments` → experiment array
- `POST /experiments` body config → job, result experiment
- `GET /experiments/{id}` → experiment
- `GET /experiments/{id}/export` → downloadable JSON
- `GET /models` → honest model capabilities/registry
- `POST /datasets/import` → validated de-identified connectome JSON import

Long-running operations return HTTP 202 and persisted job records. UI polls jobs until success/failure; it must not fabricate computation results on connection errors. API defaults to SQLite with SQLAlchemy and a local executor; Docker adds PostgreSQL, Redis, and a Celery executor. Async failures are persisted and surfaced. Local executor jobs interrupted by restart must be marked failed rather than left running.

# Architecture

NeuroResect has two entry points into one scientific engine: the research workstation and the command line. Browser code never calculates the authoritative scientific result.

```mermaid
flowchart TB
    subgraph Client[Interactive workstation]
        UI[Next.js · React · TypeScript]
        Scene[Three.js · React Three Fiber]
        Panels[Resection editor · metrics · experiments]
        UI --- Scene
        UI --- Panels
    end
    UI -->|same-origin /api/v1| API[FastAPI · validated requests]
    API --> Repo[SQLAlchemy repositories]
    Repo --> DB[(SQLite locally / PostgreSQL in Compose)]
    API --> Jobs[Persisted job coordinator]
    Jobs --> Local[Bounded local executor]
    Jobs --> Queue[Redis · Celery worker]
    Local --> Core
    Queue --> Core
    CLI[neuroresect CLI] --> Core
    subgraph Core[Framework-independent neurocore]
        Validate[Input validation]
        Sim[Resection + graph metrics]
        Analyze[Sensitivity + constrained search]
        Learn[Grouped experiments + uncertainty]
        Prov[Hashes + versions + artifacts]
        Validate --> Sim
        Sim --> Analyze
        Sim --> Learn
        Sim --> Prov
        Analyze --> Prov
        Learn --> Prov
    end
```

## A simulation request

```mermaid
sequenceDiagram
    actor Researcher
    participant Web as 3D workstation
    participant API as FastAPI
    participant DB as Database
    participant Worker as Job executor
    participant Core as neurocore
    Researcher->>Web: Select regions and removal fractions
    Web->>API: POST /scenarios
    API->>DB: Store immutable scenario definition
    API-->>Web: Scenario ID
    Web->>API: POST /scenarios/{id}/simulate
    API->>DB: Persist queued job / check idempotency
    API-->>Web: 202 + job ID
    API->>Worker: Dispatch work
    Worker->>Core: Validate and simulate
    Core-->>Worker: Before/after metrics + provenance
    Worker->>DB: Persist result and succeeded state
    loop While queued or running
        Web->>API: GET /jobs/{id}
        API-->>Web: Status, stage, progress
    end
    Web->>Researcher: Animate network and show computed metrics
```

Switching patient/atlas or editing a scenario invalidates visible old results. Requests belonging to an old selection must not overwrite the current workspace. A failed job is shown as a failure, never replaced with demo numbers.

## Data and result identity

```mermaid
erDiagram
    DATASET ||--o{ PATIENT : contains
    PATIENT ||--o{ CONNECTOME : has
    ATLAS ||--o{ CONNECTOME : indexes
    CONNECTOME ||--o{ SCENARIO : contextualizes
    SCENARIO ||--o{ JOB : launches
    SCENARIO ||--o| SIMULATION : produces
    SCENARIO ||--o| PREDICTION : produces
    EXPERIMENT ||--o{ FOLD_RESULT : records
    EXPERIMENT ||--|| PROVENANCE : identifies
```

This diagram represents domain relationships, not a promise of one SQL table per entity. Prototype persistence uses typed records plus structured JSON scientific payloads. Source hashes cover the matrix and atlas metadata; configuration hashes cover operations. Database IDs alone are insufficient provenance.

## Deployment boundaries

The local executor is for a single API process. The container deployment moves execution into Celery and uses PostgreSQL. Redis and PostgreSQL are internal Compose services; only the web and API ports bind to localhost. The provided configuration is a development/research deployment, without lab identity or tenancy.

The HLD also describes MinIO, MLflow, and DVC. This release keeps artifact exports and provenance self-contained so a research workflow does not require those services. Object-store and experiment-tracker integrations, anatomical meshes, raw imaging preprocessing, and additional modalities remain explicit extensions rather than disconnected placeholder services.

See [architecture decisions](adr), [API contract](API_CONTRACT.md), and [scientific methods](SCIENCE.md).

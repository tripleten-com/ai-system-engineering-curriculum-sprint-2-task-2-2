# Coldline Task 2.2 — Define service boundaries that reduce coupling

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/tripleten-com/ai-system-engineering-curriculum-sprint-2-task-2-2/tree/main)

## Start the system

Prerequisites are Python 3.12 and Docker with Compose v2. The supplied bootstrap supports macOS
arm64/x86-64, Windows x86-64, and Linux x86-64/aarch64, and installs pinned uv 0.11.8 under
`.tools/bin`. If your computer cannot run the stack locally, use the Codespaces button above.

On macOS and most Linux distributions the interpreter is `python3`; substitute it wherever these
commands say `python`.

```shell
python infra/scripts/bootstrap.py
./.tools/bin/uv sync --frozen
./.tools/bin/uv run --frozen poe preflight
./.tools/bin/uv run --frozen poe start
./.tools/bin/uv run --frozen poe ready
./.tools/bin/uv run --frozen poe ingest
./.tools/bin/uv run --frozen poe baseline
```

PowerShell and POSIX wrappers are available under `infra/scripts/`. After uv is on `PATH`, the
shorter `uv run --frozen poe <task>` form works.

| Service | Local URL | Purpose |
|---|---|---|
| API | `http://localhost:8000` | Submit exception workflows and retrieval queries |
| Grafana | `http://localhost:3000` | Use the focused diagnostics dashboard |
| Prometheus | `http://localhost:9090` | Query bounded metrics |
| Jaeger | `http://localhost:16686` | Inspect local traces |
| LocalStack S3 | `http://localhost:4566` | Inspect the emulated object-storage endpoint |

Each of these ports can be overridden by setting the matching `COLDLINE_API_HOST_PORT`,
`COLDLINE_GRAFANA_HOST_PORT`, `COLDLINE_PROMETHEUS_HOST_PORT`, `COLDLINE_JAEGER_HOST_PORT`, or
`COLDLINE_LOCALSTACK_HOST_PORT` environment variable in your shell environment or a local `.env`
file (copy `.env.example`) if a default collides with something already running on your machine.
Keep the override in place for every `poe` command.

If you change the API port, also set `COLDLINE_API_HOST_PORT` in the shell that runs
`poe load-test`: this command does not read `.env`. Use the same port for startup and load testing.
For example, to use port 8001, run the command for your shell before starting the system:

| Shell | Set the API host port |
|---|---|
| PowerShell | `$env:COLDLINE_API_HOST_PORT = "8001"` |
| macOS/Linux (POSIX) | `export COLDLINE_API_HOST_PORT=8001` |

PostgreSQL, Redis, worker metrics, and OTLP remain inside the Compose network. Codespaces uses the
same `compose.yaml` and keeps every forwarded port private.

## Command path

For a fresh investigation, run the supplied commands in this order:

```text
poe start
poe ready
poe ingest
poe baseline
poe verify
```

| Command | Use |
|---|---|
| `poe ingest` | Run the supplied baseline corpus ingestion inside the API container |
| `poe baseline` | Run every published query and print the baseline evaluation report |
| `poe boundary-service` | Check dependency direction and behavior before wiring |
| `poe boundary-integration` | Check substitution and application wiring |
| `poe boundary` | Run both groups with named results |
| `poe student-tests` | Run your own tests under `tests/student/` |
| `poe unit` | Run fast isolated behavior tests |
| `poe contract` | Check interfaces, boundaries, submissions, and repository structure |
| `poe smoke` | Check the initialized running platform |
| `poe e2e` | Run the external API-to-worker workflow |
| `poe verify` | Run the public student verification path |
| `poe scenario` | Run the supplied exception-workflow walkthrough |
| `poe load-test` | Run this repository's supplied traffic profile |
| `poe reset-baseline` | Clear exception and Redis data, then restart the worker between load runs |
| `poe restart` | Restart the existing API and worker containers **without rebuilding**; run `poe start` instead after editing source |
| `poe stop` | Remove containers and the network, keeping named volumes |
| `poe reset` | Remove containers, the network, and local named volumes |

`poe ingest` is idempotent: running it twice produces the same rows, the same counts, and the same
corpus digest. `poe reset` removes the database volume, so run `poe ingest` again after a reset.

For Task 2.2, `poe verify` starts the stack and ingests the corpus, then runs readiness, smoke
tests, the end-to-end exception workflow, the baseline retrieval evaluation, the answer-sheet
checks, the service-boundary checks, and your own tests under `tests/student/`.

The service-boundary checks in `poe boundary` need no database and no network: they run your
extracted service against the supplied doubles in `tests/doubles/`. The regression half of the
contract — that the running application still answers retrieval queries with your service on the
request path — runs inside `poe baseline`, which queries the started stack over HTTP. `poe smoke`
checks the platform itself and `poe e2e` runs the exception workflow; neither one issues a
retrieval query.

Use `poe boundary-service` after recording `answers.selected_boundary` and implementing the
selected class: it checks dependency direction, independent execution, and the behavior limits.
The factory may still return `None` at this stage. After updating the matching factory, run
`poe boundary-integration` for substitution and wiring. Both commands use supplied doubles and
need only the bootstrapped Python environment, with no running stack. `poe boundary` runs both
groups and names each result. A failure in one group does not suppress the other group's results.
`poe verify` performs `poe start`, `poe ready`, and `poe ingest` itself, so run it for the
complete public gate whether or not the stack is already up.

## Folder map

```text
repository root/
├── docs/                Student guidance, public contracts, and fidelity notes
│   ├── contracts/       Machine-readable public contracts
│   ├── fidelity/        Local-runtime boundary notes
│   ├── retrieval/       Supplied retrieval pipeline reference
│   └── student/         This Task's student contract
├── infra/               Local setup and runtime configuration
│   ├── corpus/          Supplied synthetic corpus, custody record, and query set
│   └── postgres/        Database initialization
├── loadtest/            Supplied traffic profile and provider-latency harness
├── src/
│   ├── api/             HTTP application code, the retrieval workflow, student wiring
│   ├── worker/          Background application code
│   ├── domain/          Shared domain code, contracts, service contracts, student extensions
│   ├── ports/           Application interfaces
│   └── adapters/        Technology-specific implementations
└── tests/
    ├── unit/            Isolated behavior checks
    ├── contract/        Interface, retrieval, boundary, and repository checks
    ├── doubles/         Supplied deterministic test doubles
    ├── student/         Your own tests
    ├── smoke/           Running-platform checks
    └── e2e/             Supplied workflow tools and checks
```

## Overview

Use the Task 2.2 lesson to decide what to do. This README covers local setup and repository
orientation.

1. `README.md` — local setup, commands, and permitted changes.
2. [`docs/student/task-2-2-contract.md`](docs/student/task-2-2-contract.md) — this Task's required
   module and class names, dependency rules, and checks.
3. `src/domain/services.py` — the two supplied service contracts and their behavior tables.
4. `src/api/retrieval_workflow.py` — the coupled workflow and its two injection points.
5. `src/api/extensions/wiring.py` — where you decide which service the application uses.
6. `tests/doubles/` — the supplied deterministic doubles, including the alternative
   implementations the substitution check swaps in.
7. [`docs/retrieval/pipeline.md`](docs/retrieval/pipeline.md) — the supplied stages and where each
   part lives.

The application source lives in five flat packages:

| Package | Responsibility |
|---|---|
| `api` | HTTP delivery, API use cases, the retrieval workflow, student wiring, configuration, and composition |
| `worker` | Background processing, retries, configuration, and composition |
| `domain` | Provider-neutral contracts, state rules, identity, redaction, embedding, chunking, fusion, access constraints, internal service contracts |
| `ports` | Exactly five visible application interfaces |
| `adapters` | PostgreSQL, pgvector retrieval, Redis Streams, S3-compatible object storage, deterministic model, logs, traces |

`src/api/bootstrap.py` and `src/worker/bootstrap.py` compose each process from its settings and
adapters. Process settings live in `src/api/config.py` and `src/worker/config.py`; other modules
receive settings or collaborators through function and constructor arguments.

## Inspect database and object-store evidence

After `poe ingest`, use the PostgreSQL client already installed in the supplied container.
These read-only commands show the table definitions and the stored chunk representations:

```shell
docker compose exec -T postgres psql -U coldline -d coldline -c "\d documents"
docker compose exec -T postgres psql -U coldline -d coldline -c "\d chunks"
docker compose exec -T postgres psql -U coldline -d coldline -c "SELECT chunk_id, document_id, chunk_index, vector_dims(embedding), search_document, tenant_id, access_tier FROM chunks ORDER BY chunk_id;"
```

Compare the results with `infra/postgres/002_retrieval_corpus.sql` and the supplied corpus
fixtures. For object-store evidence, use `GET /api/v1/corpus/objects?prefix=corpus/`
at the API URL above and inspect `docker compose logs localstack`. The initializer provisions
resources and uploads the supplied objects; `poe ingest` loads the searchable database rows.
Use the Task lesson to decide which observations to collect and which changes are permitted.

## The five ports

Find the available interfaces in `src/ports/`. A port describes an application capability; an
adapter provides it using a concrete technology. Determine which ports are active from your own
runtime evidence rather than from this guide.

| Port | General responsibility |
|---|---|
| `ModelProvider` | Call an AI model service |
| `Retriever` | Look up relevant context or documents |
| `ObjectStore` | Store large binary objects or files |
| `JobQueue` | Publish and consume background work |
| `SecretProvider` | Read API keys and credentials |

## Retrieval API

Two endpoints are new in this Sprint. Both are supplied and are not student work.

```text
POST /api/v1/retrieval/search
  {"query_id": "...", "text": "...",
   "authorization": {"tenant_id": "...", "clearance": "standard"},
   "explain": false}
  -> ranked results, per-stage evidence, prompt context, citations

GET  /api/v1/corpus/objects?prefix=corpus/
  -> the object keys visible through the published ObjectStore port
```

Set `"explain": true` to add the authorization stage's readable pool to the evidence. That costs
one extra query, so ordinary requests leave it off.

## Test levels

| Level | Requires Compose | Main question |
|---|---:|---|
| Unit | No | Does one responsibility behave correctly, including failures? |
| Contract | Some | Do interfaces, schemas, paths, and dependency rules stay compatible? |
| Smoke | Yes | Did the complete local platform initialize and become observable? |
| E2E | Yes | Can an external client complete the supplied workflow? |

Contract checks marked `runtime` need the running stack. `poe contract` skips them; `poe verify`
and `poe runtime-contract` run them.

## Submission checks

Run `poe verify` locally before opening your student pull request. Public GitHub CI repeats
the student checks. The course platform (CMS) runs the required protected grading separately
and associates its results with your submission commit. A green template-export check, or a
skipped student check on an `export/` branch, is not a passing grade. You do not configure
GitHub grading secrets. Follow the Task lesson's instructor-review and progression policy.

## Task boundary

Task 2.2 asks you to extract **one** of two interleaved responsibilities from
`src/api/retrieval_workflow.py` behind an internal service boundary, and to record which one.
Both choices are equally valid and both pass when implemented correctly. This is an in-process
code separation: no new container, no new network service, no new port.

These paths are student-editable:

- `submission.yaml`
- `src/api/extensions/wiring.py`
- anything you add under `src/api/extensions/`
- anything you add under `tests/student/`

Everything else is protected, including the workflow itself. You never need to edit the caller —
that is the property being assessed. Read
[`docs/student/task-2-2-contract.md`](docs/student/task-2-2-contract.md) for the required names,
the dependency rules, and what each check verifies.

The supplied defaults are `top_k = 3` and `dense_weight = 0.5`. Each arm returns a fixed
candidate pool of 12 rows before fusion, so the two parameters change what fusion selects without
changing what the arms see.

### Student walkthrough

See **Task 2.2: Define service boundaries that reduce coupling** in your course platform for the
full walkthrough. In outline: start the stack and ingest the corpus so the regression checks have
something to run against, read the coupled workflow and both supplied contracts, choose one
responsibility, record it in `submission.yaml`, implement the required class under
`src/api/extensions/`, return it from the matching factory in `src/api/extensions/wiring.py`,
run `poe boundary` and then `poe verify`, and open your pull request.

## Operational limits

This local system does not authenticate users, terminate TLS, or manage production secrets.
A retrieval request states its own tenancy and clearance, so that context is an asserted
identity rather than a verified one. The Compose PostgreSQL password and the LocalStack access keys
are local-only non-secret credentials. Never place real credentials, personal data, or production
records in this repository, including in `infra/corpus/`.

Named volumes preserve local PostgreSQL, Redis, Prometheus, Grafana, and Jaeger state across
`poe stop`. LocalStack object contents are deliberately not persisted; the initializer re-uploads
the supplied corpus artifacts on every start. The `poe reset` command deletes the named volumes.
This topology makes no backup, replication, high-availability, disaster-recovery, capacity,
latency-SLO, or availability claim.

See [JobQueue fidelity](docs/fidelity/JobQueue.md),
[ModelProvider fidelity](docs/fidelity/ModelProvider.md),
[ObjectStore fidelity](docs/fidelity/ObjectStore.md), and
[Retriever fidelity](docs/fidelity/Retriever.md) for the active adapter boundaries. The
[local runtime evidence](docs/fidelity/local-runtime.md) records the current measurement and its
qualification limits.

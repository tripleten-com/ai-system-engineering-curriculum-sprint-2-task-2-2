# Task 2.2 contract — extract one internal service boundary

Two responsibilities are interleaved in `src/api/retrieval_workflow.py`. Extract **one** of them
behind an internal service boundary. Both choices are equally valid; both pass when implemented
correctly. Nothing here asks for a diagram or a written justification.

## Your two choices

| Choice | Recorded value | Required module | Required class |
|---|---|---|---|
| Retrieval orchestration | `retrieval_orchestration` | `src/api/extensions/retrieval_orchestration.py` | `StudentRetrievalOrchestrator` |
| Context assembly | `context_assembly` | `src/api/extensions/context_assembly.py` | `StudentContextAssembler` |

Both live in the application layer, not in `domain`. A service that depends on one of the five
ports is application logic: `domain` may not import outward, so a port-dependent service cannot
live there, and the authoring integrity check rejects it if it does.

The module and class names are fixed. The automated checks import them by name, so a working
implementation under a different name still fails.

## What each responsibility owns

`src/domain/services.py` holds the supplied contracts, including the behavior table for each
method. Read it first — it is the specification, not this page.

**`retrieval_orchestration`** owns resolving the two controlled parameters, building the
`RetrievalRequest` from the caller's identity and question, invoking the `Retriever` port, and
selecting which candidates travel downstream.

```python
class StudentRetrievalOrchestrator:
    def __init__(self, retriever, *, top_k, dense_weight, citation_limit): ...
    async def orchestrate(
        self, query_id, text, authorization, *, explain=False
    ) -> OrchestratedRetrieval: ...
```

**`context_assembly`** owns token budgeting, prompt formatting, and citation construction.

```python
class StudentContextAssembler:
    def __init__(self, *, token_budget, citation_limit): ...
    def assemble(self, query_id, selected) -> AssembledContext: ...
```

The constructor signatures are the ones `src/api/extensions/wiring.py` already calls. Keep them.

## Dependency rules

A module under `src/api/extensions/` may import from `domain` and `ports`. It must not
import any of these:

```text
adapters   worker
asyncpg    boto3      botocore   fastapi   redis    sqlalchemy
psycopg    psycopg2   httpx      requests  socket   urllib
```

Two rules follow, and both are checked:

- **No cycle.** The workflow depends on the service contract; the service must never import its
  caller. Importing `api.retrieval_workflow` fails the check.
- **No concrete-infrastructure bypass.** Retrieval reaches the database through the `Retriever`
  port. An extracted service that opens its own connection fails the check, even if it works.

## Wiring

Return your instance from exactly one factory in `src/api/extensions/wiring.py` — the one matching
your recorded choice. Leave the other returning `None`. The composition root passes both results to
`RetrievalWorkflow`, which delegates the half that received a service and keeps the coupled code for
the half that did not.

An implementation that exists but is not returned from its factory fails the
application-integration check: the running application would still be executing the coupled code.

## What the checks verify

| Check | What it means |
|---|---|
| dependency rules | no forbidden import, no cycle back to the caller |
| independent execution | your class runs against the supplied doubles in `tests/doubles/`, with no database and no network |
| contract behavior | your implementation satisfies the behavior table in `domain/services.py`, including the selection cap and the token budget |
| substitutability | swapping a different implementation of the same contract into the workflow changes the output, with no caller edit between the two runs |
| application integration | the wiring factory returns your class, and the composed workflow exposes it |
| regression | the retrieval API still answers as it did before the extraction |

Use `poe boundary-service` after recording `answers.selected_boundary` and implementing the
selected class: it checks dependency direction, independent execution, and the behavior limits.
The factory may still return `None` at this stage. After updating the matching factory, run
`poe boundary-integration` for substitution and wiring. Both commands use supplied doubles and
need only the bootstrapped Python environment, with no running stack. `poe boundary` runs both
groups and names each result. A failure in one group does not suppress the other group's results.
Run `poe verify` after `poe start`, `poe ready`, and `poe ingest` for the complete public gate.

## Permitted paths

- `submission.yaml`
- `src/api/extensions/wiring.py`
- anything you add under `src/api/extensions/`
- anything you add under `tests/student/`

Everything else is protected, including `src/api/retrieval_workflow.py`. The extraction is designed
so you never need to edit the caller — that is the property being assessed.

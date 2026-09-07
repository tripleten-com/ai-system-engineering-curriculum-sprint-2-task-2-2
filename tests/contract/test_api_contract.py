"""Coldline.

===================

File:              tests/contract/test_api_contract.py
Component:         Contract tests — Test Api Contract
Purpose:           HTTP contract tests for the Coldline API.
Interacts With:    Published interfaces and repository boundaries
Sprint/Task:       Sprint 2 — Project 2
Concepts:          Compatibility, ownership, export safety
Tools:             Python 3.12, pytest
"""

from datetime import UTC, datetime

import httpx
import pytest

from api.retrieval_workflow import RetrievalWorkflow
from api.routes import create_app
from api.use_cases import ReadingApplication
from domain.contracts import (
    AccessLabel,
    AccessTier,
    Candidate,
    ExceptionRecord,
    ExceptionState,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStage,
    SensorReading,
    StageEvidence,
)
from domain.failures import ObjectStoreUnavailable


class MemoryRepository:
    """Persist records for HTTP contract tests."""

    def __init__(self) -> None:
        """Initialize empty test state."""
        self.records: dict[str, ExceptionRecord] = {}

    async def get(self, exception_id: str) -> ExceptionRecord | None:
        """Return a stored record."""
        return self.records.get(exception_id)

    async def create(self, record: ExceptionRecord) -> ExceptionRecord:
        """Create or return a record."""
        return self.records.setdefault(record.exception_id, record)

    async def transition(
        self,
        exception_id: str,
        expected: set[ExceptionState],
        target: ExceptionState,
        *,
        summary: str | None = None,
        failure_reason: str | None = None,
    ) -> ExceptionRecord:
        """Apply one test transition."""
        current = self.records[exception_id]
        assert current.state in expected
        updated = current.model_copy(
            update={
                "state": target,
                "summary": summary if summary is not None else current.summary,
                "failure_reason": failure_reason,
                "updated_at": NOW,
            }
        )
        self.records[exception_id] = updated
        return updated


class MemoryQueue:
    """Record published jobs for HTTP contract tests."""

    def __init__(self) -> None:
        """Initialize the publication counter."""
        self.count = 0

    async def publish(self, job: object) -> str:
        """Record one publication."""
        self.count += 1
        return "1-0"


class StubRetriever:
    """Return one fixed candidate so the HTTP contract can be checked offline."""

    def __init__(self) -> None:
        """Record the requests the route produced."""
        self.requests: list[RetrievalRequest] = []

    async def search_hybrid(self, request: RetrievalRequest) -> RetrievalResult:
        """Return a fixed single-candidate ranking with one stage entry."""
        self.requests.append(request)
        candidate = Candidate(
            chunk_id="sop-stub#0000",
            document_id="sop-stub",
            rank=1,
            score=0.5,
            text="stub chunk text for the HTTP contract",
            access=AccessLabel(tenant_id="tenant-stub", access_tier=AccessTier.STANDARD),
            provenance_revision="r1",
        )
        return RetrievalResult(
            query_id=request.query_id,
            results=(candidate,),
            stages=(StageEvidence(stage=RetrievalStage.FUSION, admitted=(candidate.chunk_id,)),),
            authorization_enforced=False,
        )


async def _stub_objects(prefix: str) -> list[str]:
    """Return two fixed object keys for the corpus listing contract."""
    return [f"{prefix}documents.jsonl", f"{prefix}provenance.jsonl"]


async def _failing_objects(prefix: str) -> list[str]:
    """Represent an unreachable object store."""
    raise ObjectStoreUnavailable("object store unreachable")


class ExplodingRepository(MemoryRepository):
    """Raise one unexpected persistence error for the HTTP 500 signal test."""

    async def get(self, exception_id: str) -> ExceptionRecord | None:
        """Simulate an unhandled database driver failure."""
        raise RuntimeError("database connection reset")


NOW = datetime(2026, 8, 28, tzinfo=UTC)
PAYLOAD = {
    "reading_id": "reading-syn-001",
    "shipment_id": "shipment-syn-001",
    "temperature_c": 9.2,
    "allowed_min_c": 2.0,
    "allowed_max_c": 8.0,
    "recorded_at": "2026-08-28T00:00:00Z",
}


def _app(
    application: ReadingApplication,
    repository: MemoryRepository,
    **overrides: object,
) -> object:
    """Compose the HTTP layer with in-memory retrieval and object collaborators."""
    arguments: dict[str, object] = {
        "retrieval": RetrievalWorkflow(StubRetriever(), top_k=5, dense_weight=0.5, token_budget=64),
        "objects": _stub_objects,
    }
    arguments.update(overrides)
    return create_app(
        application,
        repository,
        arguments.pop("retrieval"),  # type: ignore[arg-type]
        arguments.pop("objects"),  # type: ignore[arg-type]
        **arguments,  # type: ignore[arg-type]
    )


@pytest.fixture
def components() -> tuple[object, MemoryRepository, MemoryQueue]:
    """Return an application wired to in-memory boundary implementations."""
    repository = MemoryRepository()
    queue = MemoryQueue()
    application = ReadingApplication(repository, queue, clock=lambda: NOW)
    return _app(application, repository), repository, queue


@pytest.mark.asyncio
async def test_post_reading_returns_accepted_status_contract(
    components: tuple[object, object, object],
) -> None:
    """An exception reading must return its stable polling location."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/readings", json=PAYLOAD)

    assert response.status_code == 202
    assert response.json() == {
        "exception_id": "exc-e6a7451a-fe1a-53ca-b280-9bf67f555977",
        "state": "QUEUED",
        "status_url": "/api/v1/exceptions/exc-e6a7451a-fe1a-53ca-b280-9bf67f555977",
    }


@pytest.mark.asyncio
async def test_duplicate_post_does_not_publish_a_second_job(
    components: tuple[object, MemoryRepository, MemoryQueue],
) -> None:
    """HTTP replay must preserve the application idempotency contract."""
    app, _, queue = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        await client.post("/api/v1/readings", json=PAYLOAD)
        response = await client.post("/api/v1/readings", json=PAYLOAD)

    assert response.status_code == 202
    assert queue.count == 1


@pytest.mark.asyncio
async def test_failed_duplicate_returns_conflict(
    components: tuple[object, MemoryRepository, MemoryQueue],
) -> None:
    """A terminal failure must return 409 rather than an empty 202 promise."""
    app, repository, queue = components
    exception_id = "exc-e6a7451a-fe1a-53ca-b280-9bf67f555977"
    repository.records[exception_id] = ExceptionRecord(
        exception_id=exception_id,
        reading=SensorReading.model_validate(PAYLOAD),
        state=ExceptionState.FAILED,
        accepted_at=NOW,
        updated_at=NOW,
        failure_reason="job_queue_unavailable",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/readings", json=PAYLOAD)

    assert response.status_code == 409
    assert response.json()["detail"].endswith("terminal FAILED")
    assert queue.count == 0


@pytest.mark.asyncio
async def test_get_exception_returns_recorded_state(
    components: tuple[object, object, object],
) -> None:
    """The polling endpoint must return the durable exception record."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        accepted = await client.post("/api/v1/readings", json=PAYLOAD)
        response = await client.get(accepted.json()["status_url"])

    assert response.status_code == 200
    assert response.json()["state"] == "QUEUED"
    assert response.json()["summary"] is None


@pytest.mark.asyncio
async def test_in_range_reading_is_rejected_without_exception_work(
    components: tuple[object, MemoryRepository, MemoryQueue],
) -> None:
    """An in-range reading must not create or publish exception work."""
    app, repository, queue = components
    payload = {**PAYLOAD, "temperature_c": 5.0}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/readings", json=payload)

    assert response.status_code == 422
    assert repository.records == {}
    assert queue.count == 0


@pytest.mark.asyncio
async def test_readiness_reports_dependency_failure() -> None:
    """Readiness must fail when the runtime dependencies are unavailable."""
    repository = MemoryRepository()
    application = ReadingApplication(repository, MemoryQueue(), clock=lambda: NOW)

    async def unavailable() -> bool:
        """Represent an unavailable dependency graph."""
        return False

    app = _app(application, repository, readiness=unavailable)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_bounded_api_signal(
    components: tuple[object, object, object],
) -> None:
    """The API must expose its request signal without identifier labels."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        await client.get("/health/live")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "coldline_api_requests_total" in response.text
    assert "exception_id=" not in response.text


@pytest.mark.asyncio
async def test_unhandled_server_error_is_counted_as_http_500() -> None:
    """A server failure must remain visible in the bounded API request metric."""
    repository = ExplodingRepository()
    application = ReadingApplication(repository, MemoryQueue(), clock=lambda: NOW)
    app = _app(application, repository)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        failed = await client.get("/api/v1/exceptions/exc-failure")
        metrics = await client.get("/metrics")

    assert failed.status_code == 500
    assert 'route="/api/v1/exceptions/{exception_id}",status="500"' in metrics.text


@pytest.mark.asyncio
async def test_retrieval_search_returns_results_stages_and_context(
    components: tuple[object, object, object],
) -> None:
    """The retrieval route must return the ranking, the evidence, and the context."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/retrieval/search",
            json={
                "query_id": "q-contract",
                "text": "stub query text",
                "authorization": {"tenant_id": "tenant-stub", "clearance": "standard"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_id"] == "q-contract"
    assert [item["chunk_id"] for item in payload["results"]] == ["sop-stub#0000"]
    assert [item["stage"] for item in payload["stages"]] == ["fusion"]
    assert payload["authorization_enforced"] is False
    assert payload["citations"] == ["sop-stub@r1 (tenant-stub/standard)"]
    assert payload["used_tokens"] <= payload["token_budget"]


@pytest.mark.asyncio
async def test_retrieval_search_rejects_an_unknown_field(
    components: tuple[object, object, object],
) -> None:
    """The retrieval request contract is closed, so a stray field must fail."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/retrieval/search",
            json={
                "query_id": "q-contract",
                "text": "stub query text",
                "authorization": {"tenant_id": "tenant-stub", "clearance": "standard"},
                "top_k": 20,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_corpus_objects_route_lists_keys_through_the_port(
    components: tuple[object, object, object],
) -> None:
    """Corpus artifacts must be listable without a caller touching a cloud SDK."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/corpus/objects", params={"prefix": "corpus/"})

    assert response.status_code == 200
    assert response.json() == {
        "prefix": "corpus/",
        "keys": ["corpus/documents.jsonl", "corpus/provenance.jsonl"],
    }


@pytest.mark.asyncio
async def test_corpus_objects_route_reports_an_unavailable_object_store() -> None:
    """An object-store failure must surface as 503, not as an opaque 500."""
    repository = MemoryRepository()
    application = ReadingApplication(repository, MemoryQueue(), clock=lambda: NOW)
    app = _app(application, repository, objects=_failing_objects)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/corpus/objects")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_retrieval_metric_label_stays_bounded(
    components: tuple[object, object, object],
) -> None:
    """The new routes must not add an unbounded metric dimension."""
    app, _, _ = components
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/retrieval/search",
            json={
                "query_id": "q-contract",
                "text": "stub query text",
                "authorization": {"tenant_id": "tenant-stub", "clearance": "standard"},
            },
        )
        metrics = await client.get("/metrics")

    assert 'route="/api/v1/retrieval/search"' in metrics.text
    assert "q-contract" not in metrics.text

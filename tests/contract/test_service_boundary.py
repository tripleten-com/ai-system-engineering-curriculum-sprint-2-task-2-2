"""Coldline.

===================

File:              tests/contract/test_service_boundary.py
Component:         Contract tests — Service boundary
Purpose:           Check the extracted service for dependencies, isolation, and integration.
Interacts With:    Student extensions, the wiring factories, and the retrieval workflow
Sprint/Task:       Sprint 2 — Project 2 / Task 2.2
Concepts:          Dependency direction, independent execution, substitutability
Tools:             Python 3.12, pytest, AST
"""

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from api.extensions import wiring
from api.retrieval_workflow import RetrievalWorkflow
from domain.contracts import AccessTier, AuthorizationContext
from domain.services import ContextAssembler, RetrievalOrchestrator
from tests.doubles import (
    AlternativeContextAssembler,
    AlternativeRetrievalOrchestrator,
    StubRetriever,
    candidate,
)

# Assessed: a fresh starter has no extracted service and is supposed to fail
# these. They need no Docker: the service runs against the supplied doubles.
pytestmark = pytest.mark.assessed

TASK_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = TASK_ROOT / "src/api/extensions"

# The one module and class name each choice must provide. The names are part of
# the published Task contract so that an automated check can find the
# implementation without guessing.
REQUIRED = {
    "retrieval_orchestration": (
        "api.extensions.retrieval_orchestration",
        "StudentRetrievalOrchestrator",
    ),
    "context_assembly": (
        "api.extensions.context_assembly",
        "StudentContextAssembler",
    ),
}
# Libraries and packages an extracted service must not reach for: concrete
# infrastructure belongs behind a port, and the worker is a separate runtime.
FORBIDDEN_ROOTS = frozenset(
    {
        "adapters",
        "worker",
        "asyncpg",
        "boto3",
        "botocore",
        "fastapi",
        "redis",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "httpx",
        "requests",
        "socket",
        "urllib",
    }
)
# The module that calls the extracted service. Importing it would make the
# dependency circular, which is the property this Task is about.
CALLER_MODULE = "api.retrieval_workflow"

TOP_K = 3
DENSE_WEIGHT = 0.5
TOKEN_BUDGET = 24
CITATION_LIMIT = 3
CALLER = AuthorizationContext(tenant_id="tenant-double", clearance=AccessTier.STANDARD)
RANKING = (
    candidate("sop-alpha#0000", 1, text="alpha one two three four"),
    candidate("sop-alpha#0001", 2, text="alpha five six"),
    candidate("sop-beta#0000", 3, text="beta one two"),
    candidate("sop-gamma#0000", 4, text="gamma one two"),
)


def selected_boundary() -> str:
    """Return the recorded boundary choice or fail with actionable guidance."""
    document = yaml.safe_load((TASK_ROOT / "submission.yaml").read_text(encoding="utf-8"))
    answers = document.get("answers") if isinstance(document, dict) else None
    choice = answers.get("selected_boundary", "") if isinstance(answers, dict) else ""
    if choice not in REQUIRED:
        pytest.fail(
            "answers.selected_boundary must be either retrieval_orchestration or "
            f"context_assembly; found {choice!r}"
        )
    return str(choice)


def student_class() -> type[Any]:
    """Import the required class for the recorded choice."""
    module_name, class_name = REQUIRED[selected_boundary()]
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{module_name} is missing. The recorded choice requires "
            f"src/{module_name.replace('.', '/')}.py to define {class_name}. ({exc})"
        )
    implementation = getattr(module, class_name, None)
    if implementation is None:
        pytest.fail(f"{module_name} does not define {class_name}")
    return implementation


def _imports(path: Path) -> set[str]:
    """Collect the absolute import roots of one module."""
    return {name.split(".", maxsplit=1)[0] for name in _imported_modules(path)}


def _imported_modules(path: Path) -> set[str]:
    """Collect the dotted module names one module imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # A relative import inside api.extensions can only reach this
                # package, which is allowed; record it as such.
                names.add("api.extensions")
            elif node.module:
                names.add(node.module)
    return names


def _extension_modules() -> list[Path]:
    """Return the student extension modules, excluding the package marker."""
    return [
        path
        for path in sorted(EXTENSIONS.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]


def test_extracted_service_has_no_forbidden_dependency() -> None:
    """An extracted service must not reach its caller or concrete infrastructure."""
    student_class()
    violations: list[str] = []
    for path in _extension_modules():
        offending = sorted(_imports(path) & FORBIDDEN_ROOTS)
        if offending:
            violations.append(f"{path.relative_to(TASK_ROOT).as_posix()}: {offending}")
    assert violations == [], violations


def test_extracted_service_has_no_import_cycle() -> None:
    """The dependency must point one way: the caller depends on the service."""
    workflow_imports = _imports(TASK_ROOT / "src/api/retrieval_workflow.py")
    assert "domain" in workflow_imports
    for path in _extension_modules():
        imported = _imported_modules(path)
        assert CALLER_MODULE not in imported, (
            f"{path.name} imports {CALLER_MODULE}, its own caller, which makes the "
            "dependency circular"
        )
        assert not any(name.startswith(f"{CALLER_MODULE}.") for name in imported), path.name


async def test_extracted_service_runs_against_supplied_doubles() -> None:
    """The service must execute in isolation, with no database and no network."""
    choice = selected_boundary()
    implementation = student_class()

    if choice == "retrieval_orchestration":
        retriever = StubRetriever(RANKING)
        service = implementation(
            retriever, top_k=TOP_K, dense_weight=DENSE_WEIGHT, citation_limit=CITATION_LIMIT
        )
        assert isinstance(service, RetrievalOrchestrator)
        orchestrated = await service.orchestrate("q-double", "alpha beta", CALLER)

        request = retriever.requests[-1]
        assert (request.query_id, request.text) == ("q-double", "alpha beta")
        assert request.authorization == CALLER
        assert (request.top_k, request.dense_weight, request.explain) == (
            TOP_K,
            DENSE_WEIGHT,
            False,
        )
        chosen = [item.chunk_id for item in orchestrated.selected]
        assert chosen == ["sop-alpha#0000", "sop-beta#0000"], chosen
        assert len({item.document_id for item in orchestrated.selected}) == len(chosen)
        # The retriever answer must come back unmodified, evidence included.
        returned = [(item.chunk_id, item.rank) for item in orchestrated.result.results]
        assert returned == [
            ("sop-alpha#0000", 1),
            ("sop-alpha#0001", 2),
            ("sop-beta#0000", 3),
        ], returned
        assert len(orchestrated.result.stages) == 4
    else:
        service = implementation(token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT)
        assert isinstance(service, ContextAssembler)
        context = service.assemble("q-double", RANKING[:3])

        assert context.query_id == "q-double"
        assert context.used_tokens <= TOKEN_BUDGET
        assert context.citations == (
            "sop-alpha@r1 (tenant-double/standard)",
            "sop-alpha@r1 (tenant-double/standard)",
            "sop-beta@r1 (tenant-double/standard)",
        )
        assert context.prompt_context.startswith("[sop-alpha#0000] alpha one two three four")
        assert "\n\n" in context.prompt_context


async def test_extracted_service_respects_the_token_budget_boundary() -> None:
    """Assembly must trim rather than overflow, and orchestration must honour the cap."""
    choice = selected_boundary()
    implementation = student_class()

    if choice == "context_assembly":
        service = implementation(token_budget=6, citation_limit=CITATION_LIMIT)
        context = service.assemble("q-double", RANKING[:3])
        assert context.used_tokens == 6, context.used_tokens
        assert context.token_budget == 6
    else:
        retriever = StubRetriever(RANKING)
        service = implementation(retriever, top_k=4, dense_weight=DENSE_WEIGHT, citation_limit=1)
        orchestrated = await service.orchestrate("q-double", "alpha beta", CALLER)
        assert len(orchestrated.selected) == 1


async def test_substituting_the_service_changes_behavior_without_caller_edits() -> None:
    """A different implementation of the same contract must change the workflow output."""
    choice = selected_boundary()
    implementation = student_class()
    retriever = StubRetriever(RANKING)

    def build(service: object) -> RetrievalWorkflow:
        """Construct the same caller twice, changing only the injected service."""
        arguments: dict[str, Any] = {
            "top_k": TOP_K,
            "dense_weight": DENSE_WEIGHT,
            "token_budget": TOKEN_BUDGET,
            "citation_limit": CITATION_LIMIT,
        }
        key = (
            "retrieval_orchestrator" if choice == "retrieval_orchestration" else "context_assembler"
        )
        arguments[key] = service
        return RetrievalWorkflow(retriever, **arguments)  # type: ignore[arg-type]

    if choice == "retrieval_orchestration":
        mine = implementation(
            retriever, top_k=TOP_K, dense_weight=DENSE_WEIGHT, citation_limit=CITATION_LIMIT
        )
        alternative: object = AlternativeRetrievalOrchestrator(
            retriever, top_k=TOP_K, dense_weight=DENSE_WEIGHT, citation_limit=CITATION_LIMIT
        )
    else:
        mine = implementation(token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT)
        alternative = AlternativeContextAssembler(
            token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT
        )

    first = await build(mine).answer("q-double", "alpha beta", CALLER)
    second = await build(alternative).answer("q-double", "alpha beta", CALLER)

    assert first.context != second.context, (
        "substituting the alternative implementation produced identical output, so the "
        "workflow is not actually delegating to the injected service"
    )


def test_application_wiring_uses_the_extracted_service() -> None:
    """The application must be wired to the student's service, not to the coupled code."""
    choice = selected_boundary()
    retriever = StubRetriever(RANKING)
    if choice == "retrieval_orchestration":
        service = wiring.build_retrieval_orchestrator(
            retriever,  # type: ignore[arg-type]
            top_k=TOP_K,
            dense_weight=DENSE_WEIGHT,
            citation_limit=CITATION_LIMIT,
        )
        other = wiring.build_context_assembler(
            token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT
        )
    else:
        service = wiring.build_context_assembler(  # type: ignore[assignment]
            token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT
        )
        other = wiring.build_retrieval_orchestrator(  # type: ignore[assignment]
            retriever,  # type: ignore[arg-type]
            top_k=TOP_K,
            dense_weight=DENSE_WEIGHT,
            citation_limit=CITATION_LIMIT,
        )

    assert service is not None, (
        "the wiring factory for the recorded choice still returns None, so the application "
        "runs the coupled code and the extraction is unused"
    )
    assert type(service).__module__.startswith("api.extensions."), (
        f"the wired service comes from {type(service).__module__}, not from a module under "
        "api.extensions"
    )
    assert isinstance(service, student_class())
    assert other is None, (
        "exactly one responsibility is extracted in this Task; the other factory must still "
        "return None"
    )


async def test_wired_service_is_the_one_the_workflow_invokes() -> None:
    """The composed workflow must expose the wired service, not a second instance."""
    choice = selected_boundary()
    retriever = StubRetriever(RANKING)
    workflow = RetrievalWorkflow(
        retriever,
        top_k=TOP_K,
        dense_weight=DENSE_WEIGHT,
        token_budget=TOKEN_BUDGET,
        citation_limit=CITATION_LIMIT,
        retrieval_orchestrator=wiring.build_retrieval_orchestrator(
            retriever,  # type: ignore[arg-type]
            top_k=TOP_K,
            dense_weight=DENSE_WEIGHT,
            citation_limit=CITATION_LIMIT,
        ),
        context_assembler=wiring.build_context_assembler(
            token_budget=TOKEN_BUDGET, citation_limit=CITATION_LIMIT
        ),
    )
    injected = (
        workflow.retrieval_orchestrator
        if choice == "retrieval_orchestration"
        else workflow.context_assembler
    )
    assert injected is not None
    assert type(injected).__module__.startswith("api.extensions.")

    outcome = await workflow.answer("q-double", "alpha beta", CALLER)
    assert outcome.result.query_id == "q-double"
    assert outcome.context.used_tokens <= TOKEN_BUDGET

"""Coldline.

===================

File:              tests/unit/test_service_boundary_imports.py
Component:         Unit tests — Service-boundary assessment
Purpose:           Exercise the dependency check against temporary Python modules.
Interacts With:    tests/contract/test_service_boundary.py
Sprint/Task:       Sprint 2 — Project 2 / Task 2.2
Concepts:          Relative imports, package initialization, dependency cycles
Tools:             Python 3.12, pytest, AST
"""

from pathlib import Path

import pytest

from tests.contract import test_service_boundary as boundary


@pytest.fixture
def extension_tree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the actual contract at an isolated application source tree."""
    extensions = tmp_path / "src/api/extensions"
    extensions.mkdir(parents=True)
    (extensions.parent / "retrieval_workflow.py").write_text("import domain\n", encoding="utf-8")
    monkeypatch.setattr(boundary, "TASK_ROOT", tmp_path)
    monkeypatch.setattr(boundary, "EXTENSIONS", extensions)
    monkeypatch.setattr(boundary, "student_class", lambda: object)
    return extensions


def write_module(extensions: Path, relative_path: str, source: str) -> Path:
    """Create source that the unchanged contract entry points can inspect."""
    path = extensions / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("relative_path", "source"),
    [
        ("service.py", "from .. import retrieval_workflow\n"),
        ("service.py", "from ..retrieval_workflow import RetrievalWorkflow\n"),
        ("service.py", "from api import retrieval_workflow\n"),
        ("__init__.py", "from .. import retrieval_workflow\n"),
        ("nested/service.py", "from ... import retrieval_workflow\n"),
        ("nested/__init__.py", "from ... import retrieval_workflow\n"),
    ],
)
def test_contract_rejects_imports_of_the_caller(
    extension_tree: Path, relative_path: str, source: str
) -> None:
    """Relative levels, package initializers, and from-import aliases cannot hide the caller."""
    write_module(extension_tree, relative_path, source)

    with pytest.raises(AssertionError, match="api.retrieval_workflow"):
        boundary.test_extracted_service_has_no_import_cycle()


@pytest.mark.parametrize(
    ("relative_path", "source", "expected"),
    [
        ("service.py", "from . import helper\n", "api.extensions.helper"),
        ("nested/service.py", "from .. import helper\n", "api.extensions.helper"),
        ("nested/__init__.py", "from . import helper\n", "api.extensions.nested.helper"),
        ("nested/service.py", "from .helper import build\n", "api.extensions.nested.helper"),
    ],
)
def test_contract_allows_local_relative_dependencies(
    extension_tree: Path, relative_path: str, source: str, expected: str
) -> None:
    """Package-relative helpers retain their actual identity and remain allowed."""
    path = write_module(extension_tree, relative_path, source)

    assert expected in boundary._imported_modules(path)
    boundary.test_extracted_service_has_no_forbidden_dependency()
    boundary.test_extracted_service_has_no_import_cycle()


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("from . import second\n", "from . import first\n"),
        ("from .second import build\n", "from .first import build\n"),
    ],
)
def test_contract_rejects_extension_import_cycles(
    extension_tree: Path, first: str, second: str
) -> None:
    """A cycle between extension modules must fail even without a caller import."""
    write_module(extension_tree, "first.py", first)
    write_module(extension_tree, "second.py", second)

    with pytest.raises(AssertionError, match="cycle"):
        boundary.test_extracted_service_has_no_import_cycle()


def test_contract_allows_shared_helpers_without_a_cycle(extension_tree: Path) -> None:
    """Two services depending on the same helper form an allowed acyclic graph."""
    write_module(extension_tree, "first.py", "from . import helper\n")
    write_module(extension_tree, "second.py", "from .helper import build\n")
    write_module(extension_tree, "helper.py", "def build(): pass\n")

    boundary.test_extracted_service_has_no_import_cycle()


@pytest.mark.parametrize(
    "source", ["from . import helper\n", "from api.extensions.nested import helper\n"]
)
@pytest.mark.parametrize("cycle", [False, True])
def test_package_helper_imports_only_fail_for_a_real_cycle(
    extension_tree: Path, source: str, cycle: bool
) -> None:
    """Both import spellings keep the helper edge without an artificial self-cycle."""
    write_module(extension_tree, "nested/__init__.py", source)
    write_module(
        extension_tree,
        "nested/helper.py",
        "import api.extensions.nested\n" if cycle else "def build(): pass\n",
    )

    if cycle:
        with pytest.raises(AssertionError, match="cycle"):
            boundary.test_extracted_service_has_no_import_cycle()
    else:
        boundary.test_extracted_service_has_no_import_cycle()


def test_contract_checks_forbidden_dependencies_in_package_initializers(
    extension_tree: Path,
) -> None:
    """Infrastructure imports in an extension package initializer cannot escape scanning."""
    write_module(extension_tree, "nested/__init__.py", "import asyncpg\n")

    with pytest.raises(AssertionError, match="asyncpg"):
        boundary.test_extracted_service_has_no_forbidden_dependency()

"""Coldline.

===================

File:              src/api/extensions/wiring.py
Component:         API — Student service wiring
Purpose:           Decide which extracted internal service the application uses.
Interacts With:    api/bootstrap.py, api/retrieval_workflow.py, domain extensions
Sprint/Task:       Sprint 2 — Project 2 / Task 2.2
Concepts:          Composition, dependency injection, bounded student surface
Tools:             Python 3.12

This file is student-editable. It is the only place the application decides
which implementation of an extracted service it uses.

Both factories return ``None`` in the starter, which means "keep running the
coupled code inside the workflow". Return your implementation from exactly one
of them - the one matching the responsibility you recorded in
``answers.selected_boundary``.

Do not change the factory names or signatures: the composition root and the
automated checks both call them exactly as written here.
"""

from domain.services import ContextAssembler, RetrievalOrchestrator
from ports import Retriever


def build_retrieval_orchestrator(
    retriever: Retriever,
    *,
    top_k: int,
    dense_weight: float,
    citation_limit: int,
) -> RetrievalOrchestrator | None:
    """Return the retrieval-orchestration service the application should use.

    Return ``None`` to keep the coupled implementation. For the
    ``retrieval_orchestration`` choice, construct and return your
    ``api.extensions.retrieval_orchestration.StudentRetrievalOrchestrator``
    with the arguments this factory receives.
    """
    return None


def build_context_assembler(
    *,
    token_budget: int,
    citation_limit: int,
) -> ContextAssembler | None:
    """Return the context-assembly service the application should use.

    Return ``None`` to keep the coupled implementation. For the
    ``context_assembly`` choice, construct and return your
    ``api.extensions.context_assembly.StudentContextAssembler`` with the
    arguments this factory receives.
    """
    return None

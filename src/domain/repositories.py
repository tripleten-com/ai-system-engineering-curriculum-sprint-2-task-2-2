"""Coldline.

===================

File:              src/domain/repositories.py
Component:         Domain — Repositories
Purpose:           Define internal persistence collaborators outside the five application ports.
Interacts With:    API and worker use cases
Sprint/Task:       Sprint 1 — Project 1
Concepts:          Business rules, immutable contracts, state
Tools:             Python 3.12
"""

from typing import Protocol

from domain.contracts import ExceptionRecord, ExceptionState


class StateConflict(RuntimeError):
    """Report a concurrent exception-state transition outside the expected set."""


class ExceptionRepository(Protocol):
    """Persist and transition exception records without exposing a provider."""

    async def get(self, exception_id: str) -> ExceptionRecord | None:
        """Return one exception record when it exists."""
        ...

    async def create(self, record: ExceptionRecord) -> ExceptionRecord:
        """Create a record or return the existing idempotent record."""
        ...

    async def transition(
        self,
        exception_id: str,
        expected: set[ExceptionState],
        target: ExceptionState,
        *,
        summary: str | None = None,
        failure_reason: str | None = None,
    ) -> ExceptionRecord:
        """Apply one compare-and-set state transition."""
        ...

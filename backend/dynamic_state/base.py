"""B2 dynamic-state resolver boundary.

The resolver consumes B1's stable ``RetrievalResult`` contract and produces the
full ``QueryResponse`` contract.  Callers therefore do not depend on the
implementation being rule based today or LLM assisted later.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.schemas import QueryResponse, RetrievalResult


@runtime_checkable
class DynamicStateResolver(Protocol):
    def resolve(self, retrieval: RetrievalResult) -> QueryResponse:
        """Resolve relations, effective memories, answer, and evidence."""

        ...

from pydantic import BaseModel, Field

from tracegraph.constants.engine import DEFAULT_MAX_ROWS, MAX_ROWS_LIMIT
from tracegraph.engine import ir
from tracegraph.engine.answer import Answer


class QueryRequest(BaseModel):
    """
    #Feature: Query API (PRD 13.1 POST /query)
    #Scenario: Typed IR query against a repo's snapshot (latest ready snapshot when omitted)
    #Complexity: Time O(1) - constant
    """

    repo_id: int = Field(ge=1)
    snapshot_id: int | None = Field(default=None, ge=1)
    query: ir.Query
    max_rows: int = Field(default=DEFAULT_MAX_ROWS, ge=1, le=MAX_ROWS_LIMIT)


__all__ = ["Answer", "QueryRequest"]

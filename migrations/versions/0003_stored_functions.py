"""stored functions for ontology, repos, snapshots, jobs, graph, overlays and answers

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""
from collections.abc import Sequence

from alembic import op

from tracegraph.utilities import apply_sql_functions, drop_sql_functions

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_FUNCTIONS: list[str] = [
    "ontology/tg_ontology_sync.sql",
    "ontology/tg_ontology_get_current.sql",
    "repo/tg_repo_create.sql",
    "repo/tg_repo_get.sql",
    "repo/tg_repo_list.sql",
    "snapshot/tg_snapshot_create.sql",
    "snapshot/tg_snapshot_get.sql",
    "snapshot/tg_snapshot_list.sql",
    "snapshot/tg_snapshot_latest_ready.sql",
    "snapshot/tg_snapshot_set_status.sql",
    "job/tg_index_job_enqueue.sql",
    "job/tg_index_job_claim.sql",
    "job/tg_index_job_finish.sql",
    "job/tg_index_job_get.sql",
    "graph/tg_node_commit.sql",
    "graph/tg_edge_commit.sql",
    "graph/tg_evidence_commit.sql",
    "graph/tg_coverage_hole_commit.sql",
    "graph/tg_graph_validate.sql",
    "graph/tg_graph_stats.sql",
    "graph/tg_node_list_at.sql",
    "graph/tg_edge_list_at.sql",
    "graph/tg_node_search.sql",
    "graph/tg_evidence_for_edges.sql",
    "graph/tg_coverage_hole_list.sql",
    "overlay/tg_overlay_create.sql",
    "overlay/tg_overlay_get.sql",
    "answer/tg_answer_insert.sql",
    "answer/tg_answer_get.sql",
]


def upgrade() -> None:
    apply_sql_functions(op, SQL_FUNCTIONS)


def downgrade() -> None:
    drop_sql_functions(op, SQL_FUNCTIONS)

from tracegraph.routers.health import router as health_router
from tracegraph.routers.impact import router as impact_router
from tracegraph.routers.ontology import router as ontology_router
from tracegraph.routers.query import router as query_router
from tracegraph.routers.repos import router as repos_router
from tracegraph.routers.snapshots import router as snapshots_router

ALL_ROUTERS = [health_router, ontology_router, repos_router, snapshots_router, query_router, impact_router]

__all__ = [
    "ALL_ROUTERS",
    "health_router",
    "impact_router",
    "ontology_router",
    "query_router",
    "repos_router",
    "snapshots_router",
]

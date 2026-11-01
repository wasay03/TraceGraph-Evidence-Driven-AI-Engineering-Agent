from tracegraph.routers.health import router as health_router
from tracegraph.routers.ontology import router as ontology_router
from tracegraph.routers.repos import router as repos_router
from tracegraph.routers.snapshots import router as snapshots_router

ALL_ROUTERS = [health_router, ontology_router, repos_router, snapshots_router]

__all__ = ["ALL_ROUTERS", "health_router", "ontology_router", "repos_router", "snapshots_router"]

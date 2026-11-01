from tracegraph.routers.health import router as health_router

ALL_ROUTERS = [health_router]

__all__ = ["ALL_ROUTERS", "health_router"]

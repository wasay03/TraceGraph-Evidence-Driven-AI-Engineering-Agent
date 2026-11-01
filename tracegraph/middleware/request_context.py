import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from tracegraph.constants import REQUEST_ID_HEADER
from tracegraph.core.context import set_request_id

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    #Feature: Observability
    #Scenario: Bind a request id to every request and log its latency
    #Complexity: Time O(1) - constant overhead per request
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        #Feature: Observability
        #Scenario: Propagate or mint X-Request-ID and log method, path, status and latency
        #Complexity: Time O(1) - constant

        Args:
            request: Incoming request.
            call_next: Next handler in the chain.

        Returns:
            Response with X-Request-ID set.
        """
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

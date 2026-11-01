import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tracegraph.core.context import get_request_id
from tracegraph.errors.errors import AppError

logger = logging.getLogger(__name__)


def _error_body(code: str, message: str, details: dict) -> dict:
    """
    #Feature: Error handling
    #Scenario: Shape every error response the same way
    #Complexity: Time O(1) - constant

    Args:
        code: Stable machine readable code.
        message: Human readable message.
        details: Structured context.

    Returns:
        JSON-serialisable error envelope.
    """
    return {"error": {"code": code, "message": message, "details": details}, "request_id": get_request_id()}


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """
    #Feature: Error handling
    #Scenario: Map a deliberate AppError to its HTTP status
    #Complexity: Time O(1) - constant

    Args:
        request: Incoming request.
        exc: The raised application error.

    Returns:
        JSON error response.
    """
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(exc.message, extra={"code": exc.code, "path": request.url.path, "request_id": get_request_id()})
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message, exc.details))


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    #Feature: Error handling
    #Scenario: Request body or query failed schema validation
    #Complexity: Time O(e) - linear in number of validation errors

    Args:
        request: Incoming request.
        exc: Pydantic validation error raised by FastAPI.

    Returns:
        JSON error response with status 422.
    """
    details = {"errors": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]}
    return JSONResponse(status_code=422, content=_error_body("validation_error", "Request validation failed.", details))


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """
    #Feature: Error handling
    #Scenario: Last-resort handler for unexpected exceptions
    #Complexity: Time O(1) - constant

    Args:
        request: Incoming request.
        exc: Unhandled exception.

    Returns:
        JSON error response with status 500 and no internal details.
    """
    logger.exception("Unhandled error", extra={"path": request.url.path, "request_id": get_request_id()})
    return JSONResponse(status_code=500, content=_error_body("internal_error", "Unexpected server error.", {}))


def register_error_handlers(app: FastAPI) -> None:
    """
    #Feature: Error handling
    #Scenario: Attach all exception handlers to the application
    #Complexity: Time O(1) - constant

    Args:
        app: FastAPI application.

    Raises:
        ValueError: When app is None.
    """
    if app is None:
        raise ValueError("[register_error_handlers] 'app' is required and must not be None.")
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """
    #Feature: Observability
    #Scenario: Read the request id bound to the current async context
    #Complexity: Time O(1) - constant

    Returns:
        The request id, or None outside a request.
    """
    try:
        return _request_id.get()
    except LookupError:
        return None


def set_request_id(request_id: str) -> None:
    """
    #Feature: Observability
    #Scenario: Bind a request id to the current async context
    #Complexity: Time O(1) - constant

    Args:
        request_id: Identifier to bind.

    Raises:
        ValueError: When request_id is None or empty.
    """
    if not request_id:
        raise ValueError("[set_request_id] 'request_id' is required and must be a non-empty string.")
    _request_id.set(request_id)

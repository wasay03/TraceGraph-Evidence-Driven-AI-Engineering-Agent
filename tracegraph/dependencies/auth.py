import hmac
from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from tracegraph.config import Settings, get_settings
from tracegraph.constants import API_KEY_HEADER, API_KEY_USER_ID, DEFAULT_TENANT_ID, ROLE_ADMIN, ROLE_PERMISSIONS
from tracegraph.errors import Errors
from tracegraph.schemas.auth import AuthContext

_api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def authenticate(
    request: Request,
    api_key: str | None = Depends(_api_key_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """
    #Feature: Authentication
    #Scenario: Validate the API key and attach the resolved context to request.state.auth
    #Complexity: Time O(k) - constant-time comparison over key length

    Args:
        request: Incoming request.
        api_key: Value of the X-API-Key header.
        settings: Application settings holding the expected key.

    Returns:
        The resolved AuthContext.

    Raises:
        Errors.HTTP.Unauthorized: When the key is missing or wrong.
    """
    if not api_key:
        raise Errors.HTTP.Unauthorized(f"Missing {API_KEY_HEADER} header.")
    if not hmac.compare_digest(api_key.encode(), settings.api_key.encode()):
        raise Errors.HTTP.Unauthorized("Invalid API key.")
    auth = AuthContext(user_id=API_KEY_USER_ID, role_id=ROLE_ADMIN, tenant_id=DEFAULT_TENANT_ID)
    request.state.auth = auth
    return auth


def require_permission(permission: str) -> Callable[..., AuthContext]:
    """
    #Feature: Authorization
    #Scenario: Build a dependency that rejects callers whose role lacks a permission
    #Complexity: Time O(1) - constant

    Args:
        permission: Permission string from constants.permissions, e.g. repo.create.

    Returns:
        FastAPI dependency returning the AuthContext.

    Raises:
        ValueError: When permission is empty.
    """
    if not permission:
        raise ValueError("[require_permission] 'permission' is required and must be non-empty.")

    def _check(auth: AuthContext = Depends(authenticate)) -> AuthContext:
        if permission not in ROLE_PERMISSIONS.get(auth.role_id, frozenset()):
            raise Errors.HTTP.Forbidden(f"Role {auth.role_id!r} lacks permission {permission!r}.")
        return auth

    return _check

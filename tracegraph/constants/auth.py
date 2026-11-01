from tracegraph.constants.permissions import ALL_PERMISSIONS

API_KEY_HEADER = "X-API-Key"
REQUEST_ID_HEADER = "X-Request-ID"

ROLE_ADMIN = "admin"
DEFAULT_TENANT_ID = "default"
API_KEY_USER_ID = "api-key"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {ROLE_ADMIN: ALL_PERMISSIONS}

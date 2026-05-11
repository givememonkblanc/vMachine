from fastapi import Header, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config.settings import get_settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Dependency guard for lifecycle API endpoints.

    Reads the configured ``api_key`` from settings.  If it is empty
    (the development default) the guard is a no-op — all requests
    pass through without authentication.

    If a key is configured, the ``X-API-Key`` header MUST match it
    exactly, otherwise a 403 is returned.
    """
    settings = get_settings()
    if not settings.api_key:
        return
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header"
        )
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )

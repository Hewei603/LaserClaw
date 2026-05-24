"""Optional API-key authentication and RBAC dependency."""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from ..config import get_settings


@dataclass
class Principal:
    actor: str
    role: str
    user_id: int | None = None


async def get_current_principal(
    x_laserclaw_api_key: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
    x_user_id: int | None = Header(default=None),
) -> Principal:
    """Return the current principal.

    Authentication is optional by default so local demos and tests continue to
    work. Set REQUIRE_AUTH=true and API_KEY to require X-LaserClaw-API-Key.
    """
    settings = get_settings()
    if settings.require_auth:
        if not settings.api_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API_KEY is not configured")
        if x_laserclaw_api_key != settings.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return Principal(actor=x_user_email or "anonymous", role=x_user_role or "user", user_id=x_user_id)


def require_role(*allowed_roles: str):
    async def dependency(principal: Principal = Depends(get_current_principal)):
        if allowed_roles and principal.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency

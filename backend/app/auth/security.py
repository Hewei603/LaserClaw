"""Optional API-key authentication and RBAC dependency."""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User


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
    db: Session = Depends(get_db),
) -> Principal:
    """Return the current principal.

    Authentication is optional by default so local demos and tests continue to
    work. Set REQUIRE_AUTH=true and API_KEY to require X-LaserClaw-API-Key.

    Privilege (``role``) is resolved from the persisted ``User`` record whenever
    ``X-User-Id`` maps to a real user, so a provisioned account cannot escalate
    itself by sending a forged ``X-User-Role`` header. The header role is only
    honored as a bootstrap fallback for an ``X-User-Id`` that has no user row
    yet (e.g. the first admin before any user exists). When REQUIRE_AUTH is on,
    an ``X-User-Id`` that names a missing or inactive user is rejected outright.
    """
    settings = get_settings()
    if settings.require_auth:
        if not settings.api_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API_KEY is not configured")
        if x_laserclaw_api_key != settings.api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    role = x_user_role or "user"
    email = x_user_email or "anonymous"
    if x_user_id is not None:
        user = db.get(User, x_user_id)
        if user is not None:
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
            # The database is the source of truth for privilege.
            role = user.role or "user"
            email = user.email
        elif settings.require_auth:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return Principal(actor=email, role=role, user_id=x_user_id)


def require_role(*allowed_roles: str):
    async def dependency(principal: Principal = Depends(get_current_principal)):
        if allowed_roles and principal.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency

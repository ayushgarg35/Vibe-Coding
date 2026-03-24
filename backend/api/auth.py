"""
Clerk authentication — FastAPI dependency for route protection.
Validates Clerk JWT tokens, resolves org + user context, enforces data region.
"""
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import get_settings
from storage.database import get_db
from storage.models import Organisation, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()
settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)


class AuthContext:
    """Resolved auth context — attached to every authenticated request."""
    def __init__(
        self,
        user_id: str,
        org_id: str,
        clerk_user_id: str,
        email: str,
        role: str,
        data_region: str,
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.clerk_user_id = clerk_user_id
        self.email = email
        self.role = role
        self.data_region = data_region


async def _verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk session token and return the decoded claims.
    Uses Clerk's backend API to validate.
    """
    try:
        from clerk_backend_api import Clerk
        clerk = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)
        # Verify the JWT using Clerk's JWKS endpoint
        # Clerk SDK handles key fetching and validation
        claims = clerk.verify_token(token)
        return claims
    except Exception as e:
        log.warning("Clerk token verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency — resolves authenticated user from Clerk JWT.
    Inject into any protected route: `user: AuthContext = Depends(get_current_user)`
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = await _verify_clerk_token(credentials.credentials)

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    # Resolve internal user from Clerk user ID
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision user on first login (internal tool mode)
        # In SaaS mode: require explicit org invitation
        if settings.APP_ENV == "development":
            user = await _provision_dev_user(clerk_user_id, claims, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not provisioned. Contact your administrator.",
            )

    # Resolve org data region
    org_result = await db.execute(select(Organisation).where(Organisation.id == user.org_id))
    org = org_result.scalar_one_or_none()
    data_region = org.data_region if org else settings.DEFAULT_DATA_REGION

    return AuthContext(
        user_id=str(user.id),
        org_id=str(user.org_id),
        clerk_user_id=clerk_user_id,
        email=user.email,
        role=user.role,
        data_region=data_region,
    )


async def require_role(*allowed_roles: str):
    """
    Role-check dependency factory.
    Usage: `user: AuthContext = Depends(require_role("admin", "pm"))`
    """
    async def _check(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted for this action. Required: {allowed_roles}",
            )
        return user
    return _check


async def _provision_dev_user(clerk_user_id: str, claims: dict, db: AsyncSession) -> User:
    """
    Development-only: auto-create user + default org on first login.
    In production, users must be explicitly invited to an org.
    """
    import uuid as _uuid
    from storage.models import Organisation

    log.warning("Auto-provisioning dev user", clerk_user_id=clerk_user_id)

    # Create default org if none exists
    org_result = await db.execute(select(Organisation).limit(1))
    org = org_result.scalar_one_or_none()

    if not org:
        org = Organisation(
            id=_uuid.uuid4(),
            name="Default Org",
            slug="default",
            plan="internal",
            data_region=settings.DEFAULT_DATA_REGION,
        )
        db.add(org)
        await db.flush()

    email = claims.get("email", f"{clerk_user_id}@dev.local")
    user = User(
        id=_uuid.uuid4(),
        org_id=org.id,
        clerk_user_id=clerk_user_id,
        email=email,
        role="admin",  # First user is admin in dev
    )
    db.add(user)
    await db.flush()
    return user

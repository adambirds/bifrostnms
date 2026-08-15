from fastapi import HTTPException, Request, status

from bifrostnms.auth.security import SessionData, get_session_user
from bifrostnms.models import User


async def require_superuser(request: Request) -> tuple[User, SessionData]:
    """Require an authenticated installation superuser for an endpoint."""
    user, session = await get_session_user(request)
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Installation superuser access required",
        )
    return user, session

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from uuid import UUID
import jwt

from app.adapters.db.session import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.domain.auth.models import User

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = UUID(user_id_str)
    except jwt.InvalidTokenError:
        raise credentials_exception

    from app.domain.auth.models import OrganizationMember
    stmt = select(User).options(joinedload(User.memberships).joinedload(OrganizationMember.org)).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.unique().scalar_one_or_none()
    
    if user is None or user.status != 'active':
        raise credentials_exception
        
    return user

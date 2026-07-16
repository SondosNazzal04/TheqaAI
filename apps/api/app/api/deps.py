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

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    for membership in current_user.memberships:
        if membership.org.type == "platform":
            return current_user
            
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="The user doesn't have enough privileges"
    )

from fastapi import Security
from fastapi.security import APIKeyHeader
from app.domain.auth.models import ApiClient

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def get_api_client(
    api_key_header: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> ApiClient | None:
    if not api_key_header:
        return None
    
    # Header format should be "Bearer pk_live_XXX"
    if not api_key_header.startswith("Bearer "):
        return None
        
    api_key = api_key_header.replace("Bearer ", "")
    if "_" not in api_key:
        return None
        
    # Example format: sk_test_keyid12345.restofhash
    # But wait, the prompt said: "The key_id will be the prefix (e.g., first 12 chars) stored in plaintext, and the rest will be stored as an argon2/bcrypt hash in key_hash."
    # Let's say the API key provided by the user is `sk_test_{12_chars_key_id}{rest}`
    # We can split by '_' or just take the prefix.
    # Actually, a common standard is `sk_test_keyid_rest`.
    parts = api_key.split("_")
    if len(parts) < 3:
        return None
        
    prefix = f"{parts[0]}_{parts[1]}" # e.g. sk_test
    # We can assume key_id is the first 12 chars of the third part, or we just store the whole string except the secret part as key_id.
    # Let's assume the key provided is `{prefix}_{key_id}_{secret}`
    # Example: sk_test_theqademo123_secret
    if len(parts) != 4:
        return None
        
    key_id = parts[2]
    secret = parts[3]
    
    from sqlalchemy.orm import selectinload
    stmt = select(ApiClient).options(selectinload(ApiClient.org)).where(ApiClient.key_id == key_id)
    result = await db.execute(stmt)
    client = result.scalar_one_or_none()
    
    if not client:
        return None
        
    import bcrypt
    if not bcrypt.checkpw(secret.encode('utf-8'), client.key_hash.encode('utf-8')):
        return None
        
    return client

async def get_current_user_or_partner(
    credentials: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    # Check if it's a JWT or API Key
    # Our API keys start with Bearer sk_test_ or Bearer sk_live_
    # JWTs start with Bearer eyJ
    if "sk_test_" in credentials or "sk_live_" in credentials:
        client = await get_api_client(api_key_header=credentials, db=db)
        if client:
            return client
    else:
        # It's a JWT, use the existing security scheme
        auth_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=credentials.replace("Bearer ", ""))
        try:
            user = await get_current_user(credentials=auth_creds, db=db)
            return user
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Could not validate credentials")

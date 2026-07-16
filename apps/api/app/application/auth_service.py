import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status
import re

from app.domain.auth.models import User, Organization, OrganizationMember, UserSession
from app.schemas.auth import RegisterRequest, LoginRequest, RegisterResponse, TokenResponse
from app.core.security import get_password_hash, verify_password, create_access_token

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)

def _sanitize_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

async def create_user_session(db: AsyncSession, user: User, refresh_token: str) -> None:
    token_hash = _hash_token(refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(session)

async def register_user(db: AsyncSession, req: RegisterRequest) -> RegisterResponse:
    if not req.email and not req.phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email or phone is required")

    stmt = select(User).where(or_(
        User.email == req.email if req.email else False,
        User.phone_e164 == req.phone if req.phone else False
    ))
    existing_user = (await db.execute(stmt)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email or phone already registered")

    user = User(
        email=req.email,
        phone_e164=req.phone,
        password_hash=get_password_hash(req.password)
    )
    db.add(user)
    
    org_type = "merchant" if req.account_type == "merchant" else "personal"
    org = Organization(
        type=org_type,
        name=req.full_name,
        slug=f"{_sanitize_slug(req.full_name)}-{secrets.token_hex(4)}"
    )
    db.add(org)
    
    await db.flush() # flush to get IDs generated (since uuid7 is default in model)

    member = OrganizationMember(
        org_id=org.id,
        user_id=user.id,
        role="owner"
    )
    db.add(member)

    access_token = create_access_token(data={"sub": str(user.id), "org_id": str(org.id), "role": "owner"})
    refresh_token = _generate_refresh_token()
    
    await create_user_session(db, user, refresh_token)
    await db.commit()
    
    return RegisterResponse(
        user=user,
        org=org,
        access_token=access_token,
        refresh_token=refresh_token
    )

async def authenticate_user(db: AsyncSession, req: LoginRequest) -> TokenResponse:
    stmt = select(User).where(or_(
        User.email == req.email_or_phone,
        User.phone_e164 == req.email_or_phone
    ))
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is not active")

    # For MVP, inject the first org id
    org_stmt = select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    org_member = (await db.execute(org_stmt)).scalars().first()
    org_id = str(org_member.org_id) if org_member else ""
    role = org_member.role if org_member else ""

    access_token = create_access_token(data={"sub": str(user.id), "org_id": org_id, "role": role})
    refresh_token = _generate_refresh_token()
    
    await create_user_session(db, user, refresh_token)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

async def refresh_token_logic(db: AsyncSession, refresh_token: str) -> TokenResponse:
    token_hash = _hash_token(refresh_token)
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    session = (await db.execute(stmt)).scalar_one_or_none()
    
    if not session or session.revoked_at or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user_stmt = select(User).where(User.id == session.user_id)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is not active")
        
    org_stmt = select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    org_member = (await db.execute(org_stmt)).scalars().first()
    org_id = str(org_member.org_id) if org_member else ""
    role = org_member.role if org_member else ""

    new_access_token = create_access_token(data={"sub": str(user.id), "org_id": org_id, "role": role})
    return TokenResponse(access_token=new_access_token)

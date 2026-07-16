from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.session import get_db
from app.schemas.auth import RegisterRequest, RegisterResponse, LoginRequest, RefreshRequest, TokenResponse, MeResponse
from app.application import auth_service
from app.api.deps import get_current_user
from app.domain.auth.models import User

router = APIRouter()

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and create their default organization."""
    return await auth_service.register_user(db, req)

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate a user and return access & refresh tokens."""
    return await auth_service.authenticate_user(db, req)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh an access token using a valid refresh token."""
    return await auth_service.refresh_token_logic(db, req.refresh_token)

@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile and organizations."""
    orgs = [member.org for member in current_user.memberships]
    return MeResponse(user=current_user, orgs=orgs)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport
import asyncio
import uuid

from app.core.settings import settings
from app.api.deps import get_db
from app.main import app
from app.domain.auth.models import User, Organization

# Create a test engine with NullPool to prevent asyncpg InterfaceError across tests
test_engine = create_async_engine(settings.async_database_uri, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=test_engine, class_=AsyncSession)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the whole session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def db():
    async with TestingSessionLocal() as session:
        yield session

from app.api.deps import get_db, get_current_user

@pytest_asyncio.fixture(scope="function")
async def db_data(db: AsyncSession):
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    
    user = User(id=user_id, email=f"test_{user_id}@example.com", status="active")
    org = Organization(id=org_id, name="Test Org", type="merchant")
    
    db.add(user)
    db.add(org)
    await db.commit()
    
    return {"user_id": user_id, "org_id": org_id}

@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession, db_data):
    async def override_get_db():
        yield db
        
    async def override_get_current_user():
        return User(id=db_data["user_id"], email=f"test_{db_data['user_id']}@example.com", status="active")
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

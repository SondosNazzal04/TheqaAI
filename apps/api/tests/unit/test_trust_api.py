import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.domain.trust.models import TrustSignal, TrustScore
from app.adapters.db.session import AsyncSessionLocal
import pytest_asyncio

@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session

@pytest.mark.asyncio
async def test_mock_signal_ingestion_and_background_recompute(db: AsyncSession):
    entity_id = uuid.uuid4()
    
    # 1. Inject a new signal via the API
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/trust/internal/trust-signals/mock",
            json={
                "entity_type": "individual",
                "entity_id": str(entity_id),
                "signal_type": "identity_verification",
                "value": 1.0,
                "metadata_payload": {"level": "verified"}
            }
        )
    
    assert response.status_code == 201
    assert response.json()["status"] == "success"
    
    # 2. Check that the signal was written to the database
    result = await db.execute(select(TrustSignal).where(
        TrustSignal.entity_type == 'individual',
        TrustSignal.entity_id == entity_id,
        TrustSignal.signal_type == "identity_verification"
    ))
    signal = result.scalar_one_or_none()
    assert signal is not None
    assert signal.value == 1.0
    
    # In a real test we might wait or execute the background task directly,
    # but the FastAPI TestClient/AsyncClient actually executes BackgroundTasks immediately after the response.
    # 3. Check that the score was calculated and cached in the database
    result = await db.execute(select(TrustScore).where(
        TrustScore.entity_type == 'individual',
        TrustScore.entity_id == entity_id
    ))
    score = result.scalar_one_or_none()
    assert score is not None
    # Since only identity is verified, the rest are cold-start defaults
    # Score should be 25 (identity) + 17.5 (success) + 20 (disputes) + 10.5 (ratings) + 3 (age) = 76.0


import pytest
import uuid
import hmac
import hashlib
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.deal.models import Deal
from app.domain.payment.models import PaymentIntent, EscrowHold, LedgerTransaction, LedgerEntry
from app.application.deal_state_machine import DealState
from app.adapters.payment.mock_provider import MockLicensedEscrowProvider

@pytest.mark.asyncio
async def test_create_payment_intent(client, db_data, db: AsyncSession):
    # Create a random seller
    seller_id = uuid.uuid4()
    from app.domain.auth.models import User
    seller = User(id=seller_id, email=f"seller_{seller_id}@example.com", status="active")
    db.add(seller)
    await db.commit()
    
    # Seller creates a deal in DB
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=seller_id,
        title="Test Deal for Payment",
        description="Test",
        amount=100,
        currency="JOD",
        fulfillment_mode="standard",
        fee_bps=200,
        fee_payer="buyer",
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    # Buyer (the default client user) accepts deal
    response_accept = await client.post(f"/v1/deals/{deal.id}/accept")
    assert response_accept.status_code == 200
    
    # Buyer creates payment intent
    idempotency_key = f"idemp_{uuid.uuid4()}"
    response_pi = await client.post(
        f"/v1/deals/{deal.id}/payment-intents",
        headers={"Idempotency-Key": idempotency_key}
    )
    assert response_pi.status_code == 200
    pi_data = response_pi.json()
    assert "intent_id" in pi_data
    assert pi_data["amount_minor"] == 10000
    
    # Test idempotency
    response_pi2 = await client.post(
        f"/v1/deals/{deal.id}/payment-intents",
        headers={"Idempotency-Key": idempotency_key}
    )
    assert response_pi2.status_code == 200
    assert response_pi2.json()["intent_id"] == pi_data["intent_id"]

@pytest.mark.asyncio
async def test_webhook_hmac_signature(client):
    payload = {"intent_id": "mock_pi_123", "status": "succeeded"}
    payload_bytes = json.dumps(payload).encode('utf-8')
    
    # Missing signature
    response = await client.post(
        "/v1/webhooks/mock-provider",
        content=payload_bytes,
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401
    
    # Invalid signature
    response_invalid = await client.post(
        "/v1/webhooks/mock-provider",
        content=payload_bytes,
        headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": "invalid"}
    )
    assert response_invalid.status_code == 401
    
    # Valid signature
    provider = MockLicensedEscrowProvider()
    valid_signature = hmac.new(
        provider.webhook_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    response_valid = await client.post(
        "/v1/webhooks/mock-provider",
        content=payload_bytes,
        headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": valid_signature}
    )
    assert response_valid.status_code == 200

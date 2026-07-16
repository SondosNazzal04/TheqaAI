import pytest
import uuid
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.deal.models import Deal
from app.application.deal_state_machine import DealState

@pytest.mark.asyncio
async def test_fulfillment_and_release_flow(client, db_data, db: AsyncSession):
    # 1. Create Seller manually
    seller_id = uuid.uuid4()
    from app.domain.auth.models import User
    seller = User(id=seller_id, email=f"seller_{seller_id}@example.com", status="active")
    db.add(seller)
    await db.commit()
    
    # 2. Seller creates a deal in DB
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=seller_id,
        title="Test Deal",
        amount=100,
        currency="JOD",
        fulfillment_mode="standard",
        fee_bps=200,
        fee_payer="seller",
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    # 3. Buyer (the default client user) accepts deal
    resp = await client.post(f"/v1/deals/{deal.id}/accept")
    assert resp.status_code == 200
    
    # 4. Buyer funds deal
    resp = await client.post(
        f"/v1/deals/{deal.id}/payment-intents",
        headers={"Idempotency-Key": f"idemp_{uuid.uuid4()}"}
    )
    assert resp.status_code == 200
    intent_id = resp.json()["provider_intent_id"]
    
    # Manually trigger webhook for payment
    db.expire_all()
    import json, hmac, hashlib
    payload = json.dumps({"intent_id": intent_id, "status": "succeeded", "event_type": "payment.succeeded"}).encode('utf-8')
    sig = hmac.new(b"super_secret_hmac_key", payload, hashlib.sha256).hexdigest()
    resp = await client.post("/v1/webhooks/mock-provider", content=payload, headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": sig})
    assert resp.status_code == 200
    
    # Verify Funded
    await db.refresh(deal)
    assert deal.status == DealState.FUNDED.value
    
    # 5. Seller ships the deal.
    from app.domain.fulfillment.models import Shipment
    from app.application.deal_state_machine import DealStateMachine
    
    shipment = Shipment(deal_id=deal.id, tracking_number="123", carrier="test", status="shipped")
    db.add(shipment)
    await DealStateMachine.transition(db, deal, DealState.IN_FULFILLMENT.value, actor_id=seller_id)
    await db.commit()
    
    # 6. Buyer confirms delivery (HTTP)
    resp = await client.post(f"/v1/deals/{deal.id}/confirmations", json={"notes": "good"})
    assert resp.status_code == 200
    
    # 7. Release Funds (Admin/System - any auth works for this endpoint currently)
    resp = await client.post(f"/v1/deals/{deal.id}/release")
    assert resp.status_code == 200
    
    # Manually trigger webhook for release
    db.expire_all()
    payload = json.dumps({"intent_id": intent_id, "status": "succeeded", "event_type": "release.succeeded"}).encode('utf-8')
    sig = hmac.new(b"super_secret_hmac_key", payload, hashlib.sha256).hexdigest()
    resp = await client.post("/v1/webhooks/mock-provider", content=payload, headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": sig})
    assert resp.status_code == 200
    
    # Verify Released
    await db.refresh(deal)
    assert deal.status == DealState.RELEASED.value
    
    # Also test the refund path
    # Create another deal
    deal2 = Deal(
        org_id=db_data["org_id"],
        seller_user_id=seller_id,
        title="Test Refund Deal",
        amount=100,
        currency="JOD",
        fulfillment_mode="standard",
        fee_bps=0,
        fee_payer="seller",
        status=DealState.DRAFT.value
    )
    db.add(deal2)
    await db.commit()
    await db.refresh(deal2)
    
    # Buyer accepts & funds
    await client.post(f"/v1/deals/{deal2.id}/accept")
    resp = await client.post(f"/v1/deals/{deal2.id}/payment-intents", headers={"Idempotency-Key": f"idemp_{uuid.uuid4()}"})
    intent2_id = resp.json()["provider_intent_id"]
    
    db.expire_all()
    payload = json.dumps({"intent_id": intent2_id, "status": "succeeded", "event_type": "payment.succeeded"}).encode('utf-8')
    sig = hmac.new(b"super_secret_hmac_key", payload, hashlib.sha256).hexdigest()
    await client.post("/v1/webhooks/mock-provider", content=payload, headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": sig})
    
    # Trigger refund
    resp = await client.post(f"/v1/deals/{deal2.id}/refunds")
    assert resp.status_code == 200, resp.json()
    
    db.expire_all()
    payload = json.dumps({"intent_id": intent2_id, "status": "succeeded", "event_type": "refund.succeeded"}).encode('utf-8')
    sig = hmac.new(b"super_secret_hmac_key", payload, hashlib.sha256).hexdigest()
    await client.post("/v1/webhooks/mock-provider", content=payload, headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": sig})
    
    await db.refresh(deal2)
    assert deal2.status == DealState.REFUNDED.value

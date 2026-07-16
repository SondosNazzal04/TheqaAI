import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.api.deps import get_db, get_current_admin_user
from app.domain.auth.models import User
from app.domain.deal.models import Deal
from app.schemas.deal import DealResponse
from app.application.deal_state_machine import DealState, DealStateMachine
from app.application.payment_service import PaymentService
from app.domain.fulfillment.models import Shipment

router = APIRouter(dependencies=[Depends(get_current_admin_user)])

@router.get("/deals", response_model=List[DealResponse])
async def list_all_deals(
    db: AsyncSession = Depends(get_db)
):
    """List all deals across the platform (Admin)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
    )
    deals = result.scalars().all()
    for deal in deals:
        deal.net_amount = deal.compute_net_amount()
        deal.fee_amount = deal.compute_fee_amount()
    return deals

class ForceTransitionRequest(BaseModel):
    target_state: str # e.g. "released" or "refunded"

@router.post("/deals/{id}/force-transition")
async def force_transition(
    req: ForceTransitionRequest,
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Admin override to force a release or refund if stuck."""
    result = await db.execute(select(Deal).where(Deal.id == id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if req.target_state == DealState.RELEASED.value:
        # Instead of just calling DealStateMachine.transition, we call PaymentService
        # But wait, trigger_release advances to RELEASE_PENDING and waits for webhook.
        # The user wants to "force a release or refund if the demo gets stuck".
        # We can just call trigger_release (if it's not already RELEASE_PENDING) 
        # and then manually simulate the webhook, or just do the ledger entries directly.
        # Actually, if we just want to force the state, we can use PaymentService's webhook processing logic.
        # But `trigger_release` requires state to be `delivery_confirmed`. If it's stuck, we might need to bypass that!
        
        # We will directly implement the financial logic from PaymentService to force it, OR
        # transition to delivery_confirmed if needed, then call trigger_release, then mock the webhook.
        
        # Since this is an admin override to fix stuck demos, let's just forcefully run the release logic:
        # First, ensure it's in a state that can be released.
        if deal.status not in [DealState.DELIVERY_CONFIRMED.value, DealState.RELEASE_PENDING.value]:
            # Force it to DELIVERY_CONFIRMED first if it's FUNDED or IN_FULFILLMENT
            if deal.status in [DealState.FUNDED.value, DealState.IN_FULFILLMENT.value]:
                await DealStateMachine.transition(db, deal, DealState.DELIVERY_CONFIRMED.value, actor_id=admin_user.id)
            else:
                raise HTTPException(status_code=400, detail=f"Cannot force release from {deal.status}")
                
        # Now trigger the release logic
        if deal.status == DealState.DELIVERY_CONFIRMED.value:
            await PaymentService.trigger_release(db, deal, admin_user.id)
            
        # The state is now RELEASE_PENDING.
        # To instantly push it to RELEASED without the provider webhook:
        # The provider returns a webhook, which processes the ledger. We can just simulate the webhook payload!
        from app.domain.payment.models import PaymentIntent
        stmt = select(PaymentIntent).where(PaymentIntent.deal_id == deal.id, PaymentIntent.status == "succeeded")
        intent = (await db.execute(stmt)).scalar_one_or_none()
        if not intent:
            raise HTTPException(status_code=400, detail="No succeeded payment intent found to release")
            
        import json, hmac, hashlib
        from app.application.payment_service import provider
        payload_dict = {"intent_id": intent.provider_intent_id, "status": "succeeded", "event_type": "release.succeeded"}
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        signature = hmac.new(provider.webhook_secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
        
        await PaymentService.process_webhook(db, payload_bytes, signature)
        
        return {"status": "success", "message": "Forced release successful"}
        
    elif req.target_state == DealState.REFUNDED.value:
        if deal.status not in [DealState.FUNDED.value, DealState.IN_FULFILLMENT.value, DealState.DELIVERY_CONFIRMED.value, DealState.RELEASE_PENDING.value, DealState.REFUND_PENDING.value]:
            raise HTTPException(status_code=400, detail=f"Cannot force refund from {deal.status}")
            
        if deal.status != DealState.REFUND_PENDING.value:
            await PaymentService.trigger_refund(db, deal, admin_user.id)
            
        from app.domain.payment.models import PaymentIntent
        stmt = select(PaymentIntent).where(PaymentIntent.deal_id == deal.id, PaymentIntent.status == "succeeded")
        intent = (await db.execute(stmt)).scalar_one_or_none()
        if not intent:
            raise HTTPException(status_code=400, detail="No succeeded payment intent found to refund")
            
        import json, hmac, hashlib
        from app.application.payment_service import provider
        payload_dict = {"intent_id": intent.provider_intent_id, "status": "succeeded", "event_type": "refund.succeeded"}
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        signature = hmac.new(provider.webhook_secret.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()
        
        await PaymentService.process_webhook(db, payload_bytes, signature)
        
        return {"status": "success", "message": "Forced refund successful"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported target state: {req.target_state}")

@router.post("/mock/carrier/{deal_id}/deliver")
async def mock_carrier_deliver(
    deal_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Instantly update a shipment's status to delivered and transition deal to delivery_confirmed."""
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.status != DealState.IN_FULFILLMENT.value:
        raise HTTPException(status_code=400, detail=f"Deal must be in fulfillment to deliver, currently {deal.status}")
        
    # Get the latest shipment
    stmt = select(Shipment).where(Shipment.deal_id == deal.id).order_by(Shipment.created_at.desc())
    shipment = (await db.execute(stmt)).scalars().first()
    
    if not shipment:
        # Create a dummy shipment if none exists so the demo works
        shipment = Shipment(deal_id=deal.id, tracking_number="MOCK_TRK_001", carrier="MockCarrier", status="shipped")
        db.add(shipment)
        await db.flush()
        
    shipment.status = "delivered"
    
    # Transition deal
    await DealStateMachine.transition(db, deal, DealState.DELIVERY_CONFIRMED.value, actor_id=admin_user.id)
    await db.commit()
    
    return {"status": "success", "message": "Carrier webhook mocked successfully"}

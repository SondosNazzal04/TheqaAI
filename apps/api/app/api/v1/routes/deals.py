from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
import uuid
from typing import List

from app.api.deps import get_db, get_current_user
from app.domain.auth.models import User
from app.domain.deal.models import Deal, DealParticipant
from app.schemas.deal import DealCreate, DealResponse
from app.application.deal_state_machine import DealStateMachine, StateTransitionError, DealState

router = APIRouter()

@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    req: DealCreate, 
    db: AsyncSession = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Create a new deal as a seller."""
    deal = Deal(
        org_id=req.org_id,
        seller_user_id=current_user.id,
        title=req.title,
        description=req.description,
        amount=req.amount,
        currency=req.currency,
        fulfillment_mode=req.fulfillment_mode,
        fee_bps=req.fee_bps,
        fee_payer=req.fee_payer,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.flush() # flush to get deal.id

    # Add the seller as a participant
    participant = DealParticipant(
        deal_id=deal.id,
        user_id=current_user.id,
        org_id=req.org_id,
        role="seller"
    )
    db.add(participant)
    await db.commit()
    
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(Deal.id == deal.id)
        .execution_options(populate_existing=True)
    )
    deal_eager = result.scalar_one()
    deal_eager.net_amount = deal_eager.compute_net_amount()
    deal_eager.fee_amount = deal_eager.compute_fee_amount()
    return deal_eager

@router.get("", response_model=List[DealResponse])
async def list_deals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List deals where the current user is a seller or buyer."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(
            or_(
                Deal.seller_user_id == current_user.id,
                Deal.buyer_user_id == current_user.id
            )
        )
    )
    deals = result.scalars().all()
    for deal in deals:
        deal.net_amount = deal.compute_net_amount()
        deal.fee_amount = deal.compute_fee_amount()
    return deals

@router.get("/{id}", response_model=DealResponse)
async def get_deal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific deal by ID."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(Deal.id == id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    # Check authorization
    if deal.seller_user_id != current_user.id and deal.buyer_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this deal")
        
    deal.net_amount = deal.compute_net_amount()
    deal.fee_amount = deal.compute_fee_amount()
    return deal

@router.get("/by-code/{code}", response_model=DealResponse)
async def get_deal_by_code(
    code: str = Path(...),
    db: AsyncSession = Depends(get_db)
):
    """Public endpoint to fetch a deal via its public_code (e.g. for a buyer checking out)."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(Deal.public_code == code)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    deal.net_amount = deal.compute_net_amount()
    deal.fee_amount = deal.compute_fee_amount()
    return deal

@router.post("/{id}/accept", response_model=DealResponse)
async def accept_deal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Accept a draft deal as a buyer."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(Deal.id == id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.seller_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Seller cannot accept their own deal")
        
    try:
        # Transition state
        await DealStateMachine.transition(db, deal, DealState.AWAITING_FUNDING.value, actor_id=current_user.id)
        
        # Attach buyer
        deal.buyer_user_id = current_user.id
        
        # Add the buyer as a participant
        participant = DealParticipant(
            deal_id=deal.id,
            user_id=current_user.id,
            role="buyer"
        )
        db.add(participant)
        
        await db.commit()
        
        # Re-query to eagerly load relations and populate existing identity map
        result = await db.execute(
            select(Deal)
            .options(selectinload(Deal.events), selectinload(Deal.participants))
            .where(Deal.id == deal.id)
            .execution_options(populate_existing=True)
        )
        deal_eager = result.scalar_one()
        deal_eager.net_amount = deal_eager.compute_net_amount()
        deal_eager.fee_amount = deal_eager.compute_fee_amount()
        return deal_eager
    except StateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.post("/{id}/cancel", response_model=DealResponse)
async def cancel_deal(
    id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a deal."""
    result = await db.execute(
        select(Deal)
        .options(selectinload(Deal.events), selectinload(Deal.participants))
        .where(Deal.id == id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.seller_user_id != current_user.id and deal.buyer_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this deal")
        
    try:
        await DealStateMachine.transition(db, deal, DealState.CANCELLED.value, actor_id=current_user.id)
        await db.commit()
        
        result = await db.execute(
            select(Deal)
            .options(selectinload(Deal.events), selectinload(Deal.participants))
            .where(Deal.id == deal.id)
            .execution_options(populate_existing=True)
        )
        deal_eager = result.scalar_one()
        deal_eager.net_amount = deal_eager.compute_net_amount()
        deal_eager.fee_amount = deal_eager.compute_fee_amount()
        return deal_eager
    except StateTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))

from fastapi import Header
from app.application.payment_service import PaymentService

@router.post("/{id}/payment-intents")
async def create_deal_payment_intent(
    id: uuid.UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a payment intent for a deal. Requires an Idempotency-Key header."""
    result = await db.execute(
        select(Deal)
        .where(Deal.id == id)
    )
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.buyer_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the buyer can create a payment intent")
        
    if deal.status != DealState.AWAITING_FUNDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot create payment intent in state {deal.status}")
        
    amount_minor = int(deal.amount * 100) # Assuming amount is full JOD (e.g., 500 = 50000 minor)
    
    intent = await PaymentService.create_intent(
        db=db,
        deal=deal,
        amount_minor=amount_minor,
        currency=deal.currency,
        idempotency_key=idempotency_key
    )
    
    return {
        "intent_id": str(intent.id),
        "provider_intent_id": intent.provider_intent_id,
        "status": intent.status,
        "amount_minor": amount_minor,
        "currency": intent.currency
    }

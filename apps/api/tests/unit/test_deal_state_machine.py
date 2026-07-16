import pytest
import uuid
from app.domain.deal.models import Deal, DealEvent
from app.application.deal_state_machine import DealStateMachine, DealState, StateTransitionError

@pytest.mark.asyncio
async def test_valid_state_transition(db, db_data):
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=db_data["user_id"],
        title="Test Deal",
        amount=100.0,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    # Transition to AWAITING_FUNDING
    actor_id = db_data["user_id"]
    await DealStateMachine.transition(db, deal, DealState.AWAITING_FUNDING.value, actor_id=actor_id)
    await db.commit()
    await db.refresh(deal)
    
    assert deal.status == DealState.AWAITING_FUNDING.value
    
    # Check event
    from sqlalchemy import select
    result = await db.execute(select(DealEvent).where(DealEvent.deal_id == deal.id))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].from_state == DealState.DRAFT.value
    assert events[0].to_state == DealState.AWAITING_FUNDING.value
    assert events[0].actor_id == actor_id

@pytest.mark.asyncio
async def test_invalid_state_transition(db, db_data):
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=db_data["user_id"],
        title="Test Deal",
        amount=100.0,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    # Draft -> Funded is invalid
    with pytest.raises(StateTransitionError):
        await DealStateMachine.transition(db, deal, DealState.FUNDED.value)

from enum import Enum
from typing import Dict, List, Any
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.domain.deal.models import Deal, DealEvent

class DealState(str, Enum):
    DRAFT = "draft"
    AWAITING_FUNDING = "awaiting_funding"
    FUNDED = "funded"
    IN_FULFILLMENT = "in_fulfillment"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    RELEASE_PENDING = "release_pending"
    RELEASED = "released"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"

# Define the valid transitions from each state
ALLOWED_TRANSITIONS: Dict[DealState, List[DealState]] = {
    DealState.DRAFT: [DealState.AWAITING_FUNDING, DealState.CANCELLED],
    DealState.AWAITING_FUNDING: [DealState.FUNDED, DealState.CANCELLED, DealState.EXPIRED],
    DealState.FUNDED: [DealState.IN_FULFILLMENT, DealState.REFUND_PENDING],
    DealState.IN_FULFILLMENT: [DealState.DELIVERY_CONFIRMED, DealState.REFUND_PENDING],
    DealState.DELIVERY_CONFIRMED: [DealState.RELEASE_PENDING, DealState.REFUND_PENDING],
    DealState.RELEASE_PENDING: [DealState.RELEASED, DealState.REFUND_PENDING],
    DealState.RELEASED: [], # Terminal state
    DealState.CANCELLED: [], # Terminal state
    DealState.EXPIRED: [], # Terminal state
    DealState.REFUND_PENDING: [DealState.REFUNDED],
    DealState.REFUNDED: [] # Terminal state
}

class StateTransitionError(Exception):
    """Exception raised for invalid state transitions."""
    pass

class DealStateMachine:
    @staticmethod
    def _is_valid_transition(from_state: str, to_state: str) -> bool:
        try:
            from_enum = DealState(from_state)
            to_enum = DealState(to_state)
        except ValueError:
            return False # Invalid state strings
        
        return to_enum in ALLOWED_TRANSITIONS.get(from_enum, [])

    @staticmethod
    async def transition(
        db: AsyncSession, 
        deal: Deal, 
        to_state: str, 
        actor_id: uuid.UUID = None, 
        metadata: Dict[str, Any] = None
    ) -> Deal:
        """
        Transitions a deal to a new state if allowed, increments the version for optimistic locking,
        and records a DealEvent in the database session.
        """
        from_state = deal.status
        
        if not DealStateMachine._is_valid_transition(from_state, to_state):
            raise StateTransitionError(f"Invalid transition from '{from_state}' to '{to_state}'")
        
        # 1. Update the Deal status
        deal.status = to_state
        # Note: optimistic locking `version` is automatically handled by SQLAlchemy via `version_id_col` mapping
        # when we commit the session, but we change the status here.
        
        # 2. Record the event
        event = DealEvent(
            deal_id=deal.id,
            from_state=from_state,
            to_state=to_state,
            actor_id=actor_id,
            metadata_payload=metadata or {}
        )
        db.add(event)
        
        # 3. Create OutboxEvent if the deal reached a milestone state
        if to_state in [DealState.FUNDED.value, DealState.RELEASED.value]:
            from app.domain.deal.models import OutboxEvent
            outbox_event = OutboxEvent(
                deal_id=deal.id,
                event_type=f"deal.{to_state}",
                payload={"deal_id": str(deal.id), "status": to_state, "public_code": deal.public_code}
            )
            db.add(outbox_event)
        
        return deal

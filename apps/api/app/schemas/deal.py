from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

class DealEventResponse(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    from_state: Optional[str] = None
    to_state: str
    metadata_payload: Optional[Dict[str, Any]] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class DealParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    org_id: Optional[uuid.UUID] = None
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DealCreate(BaseModel):
    org_id: uuid.UUID
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    amount: float = Field(..., gt=0)
    currency: str = "JOD"
    fulfillment_mode: str = "standard"
    fee_bps: int = Field(0, ge=0)
    fee_payer: str = "seller" # "seller", "buyer", "split"

class DealResponse(BaseModel):
    id: uuid.UUID
    public_code: str
    org_id: uuid.UUID
    seller_user_id: uuid.UUID
    buyer_user_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    amount: float
    currency: str
    status: str
    fulfillment_mode: str
    fee_bps: int
    fee_payer: str
    net_amount: Optional[float] = None # Calculated field
    fee_amount: Optional[float] = None # Calculated field
    version: int
    created_at: datetime
    updated_at: datetime
    
    events: Optional[List[DealEventResponse]] = None
    participants: Optional[List[DealParticipantResponse]] = None

    model_config = ConfigDict(from_attributes=True)

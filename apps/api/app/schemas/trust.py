import uuid
from pydantic import BaseModel, ConfigDict
from typing import Dict, Optional
from datetime import datetime

class SignalBreakdown(BaseModel):
    weight: float
    value: float
    contribution: float
    raw_value: Optional[float] = None
    applied_prior: bool = False

class TrustScoreResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    score: float
    breakdown: Dict[str, SignalBreakdown]
    last_calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TrustSignalCreate(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    signal_type: str
    value: float
    metadata_payload: Optional[Dict[str, float | str | int]] = None

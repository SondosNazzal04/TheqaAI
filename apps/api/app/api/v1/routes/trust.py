import uuid
from fastapi import APIRouter, Depends, HTTPException, Path, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.application.trust_service import TrustService
from app.schemas.trust import TrustScoreResponse, TrustSignalCreate

router = APIRouter()

@router.get("/scores/{type}/{id}", response_model=TrustScoreResponse)
async def get_trust_score(
    type: str = Path(..., description="Entity type: 'individual' or 'merchant'"),
    id: uuid.UUID = Path(..., description="Entity ID"),
    db: AsyncSession = Depends(get_db)
):
    if type not in ('individual', 'merchant'):
        raise HTTPException(status_code=400, detail="Type must be 'individual' or 'merchant'")
    
    try:
        response = await TrustService.get_score(db, type, id)
        if not response:
            raise HTTPException(status_code=404, detail="Trust score not found")
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/internal/trust-signals/mock", status_code=201)
async def mock_trust_signal(
    signal_data: TrustSignalCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    from app.domain.trust.models import TrustSignal
    
    # Check if a signal already exists for this type and entity, and update or insert
    from sqlalchemy import select
    result = await db.execute(select(TrustSignal).where(
        TrustSignal.entity_type == signal_data.entity_type,
        TrustSignal.entity_id == signal_data.entity_id,
        TrustSignal.signal_type == signal_data.signal_type
    ))
    existing_signal = result.scalar_one_or_none()
    
    if existing_signal:
        existing_signal.value = signal_data.value
        existing_signal.metadata_payload = signal_data.metadata_payload
    else:
        new_signal = TrustSignal(
            entity_type=signal_data.entity_type,
            entity_id=signal_data.entity_id,
            signal_type=signal_data.signal_type,
            value=signal_data.value,
            metadata_payload=signal_data.metadata_payload
        )
        db.add(new_signal)
        
    await db.commit()
    
    # Enqueue background recalculation
    from app.application.trust_service import trust_recompute
    background_tasks.add_task(trust_recompute, signal_data.entity_type, signal_data.entity_id)
    
    return {"status": "success", "message": "Signal ingested and recalculation queued"}

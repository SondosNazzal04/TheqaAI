from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.application.payment_service import PaymentService

router = APIRouter()

@router.post("/mock-provider")
async def mock_provider_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook endpoint for the Mock Licensed Escrow Provider.
    Receives async confirmation of payment success.
    Requires X-Mock-Provider-Signature header for HMAC validation.
    """
    signature = request.headers.get("X-Mock-Provider-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
        
    payload_bytes = await request.body()
    
    await PaymentService.process_webhook(db, payload_bytes, signature)
    
    return {"status": "ok"}

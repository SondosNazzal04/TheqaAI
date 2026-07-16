import uuid
import hmac
import hashlib
import json
import httpx
import asyncio
from app.domain.payment.ports import ProviderEscrowPort
from app.core.settings import settings

class MockLicensedEscrowProvider(ProviderEscrowPort):
    def __init__(self, webhook_secret: str = "super_secret_hmac_key"):
        self.webhook_secret = webhook_secret

    async def create_payment_intent(self, amount_minor: int, currency: str, idempotency_key: str, deal_id: str) -> str:
        """
        Simulate creating a payment intent.
        Returns a mock intent ID.
        """
        intent_id = f"mock_pi_{uuid.uuid4().hex[:12]}"
        
        # DEMO SPEED OPTIMIZATION: 
        # Schedule a background task to immediately fire the webhook 
        # simulating a successful payment, allowing instant state changes.
        asyncio.create_task(self._fire_webhook(intent_id))
        
        return intent_id

    async def _fire_webhook(self, intent_id: str):
        # Small delay to ensure the caller has time to commit the intent to the DB
        await asyncio.sleep(0.5)
        
        payload = {
            "intent_id": intent_id,
            "status": "succeeded"
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        
        # Generate HMAC signature
        signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        # Fire to localhost (assuming local dev server)
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    "http://127.0.0.1:8000/v1/webhooks/mock-provider",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Mock-Provider-Signature": signature
                    }
                )
            except Exception as e:
                print(f"Failed to fire mock webhook: {e}")

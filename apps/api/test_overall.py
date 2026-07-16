import httpx
import asyncio

async def test():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy import select
    from app.domain.auth.models import Organization, ApiClient
    
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/theqa")
    async with AsyncSession(engine) as session:
        result = await session.execute(select(ApiClient))
        client = result.scalar_one_or_none()
        if not client:
            print("No API Client found. Run seed script first.")
            return
            
        merchant_org_id = client.org_id
        
    print(f"Using merchant_org_id: {merchant_org_id}")
    
    async with httpx.AsyncClient(base_url="http://localhost:8000") as ac:
        print("\n--- 1. Creating Deal Programmatically ---")
        response = await ac.post(
            "/v1/deals",
            headers={
                "Authorization": "Bearer sk_test_theqademo123_secretkey123",
                "Content-Type": "application/json"
            },
            json={
                "org_id": str(merchant_org_id),
                "title": "API Created Deal for Overall Test",
                "description": "This deal was created by a third-party partner integration.",
                "amount": 1500.00,
                "currency": "JOD",
                "fulfillment_mode": "standard",
                "fee_bps": 200,
                "fee_payer": "seller"
            }
        )
        if response.status_code != 201:
            print(f"Failed to create deal: {response.status_code} {response.text}")
            return
            
        deal_data = response.json()
        print(f"Deal Created! ID: {deal_data['id']}, Status: {deal_data['status']}")
        print(f"Checkout URL generated: {deal_data.get('checkout_url')}")
        
        deal_id = deal_data['id']
        
        # 2. Accept as Buyer
        print("\n--- 2. Accepting as Buyer ---")
        # I need a JWT token for the buyer. Let's just login.
        login_response = await ac.post(
            "/v1/auth/login",
            data={
                "username": "buyer@example.com",
                "password": "password"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.text}")
            return
            
        buyer_token = login_response.json()["access_token"]
        
        accept_resp = await ac.post(
            f"/v1/deals/{deal_id}/accept",
            headers={"Authorization": f"Bearer {buyer_token}"}
        )
        print(f"Accepted. Status: {accept_resp.status_code}")
        
        # 3. Fund
        print("\n--- 3. Funding Deal ---")
        intent_resp = await ac.post(
            f"/v1/deals/{deal_id}/payment-intents",
            headers={"Authorization": f"Bearer {buyer_token}", "Idempotency-Key": "test_idempotency_key_1"}
        )
        intent_id = intent_resp.json()["provider_intent_id"]
        
        import json, hmac, hashlib
        payload = json.dumps({"intent_id": intent_id, "status": "succeeded", "event_type": "payment.succeeded"}).encode('utf-8')
        sig = hmac.new(b"super_secret_hmac_key", payload, hashlib.sha256).hexdigest()
        webhook_resp = await ac.post("/v1/webhooks/mock-provider", content=payload, headers={"Content-Type": "application/json", "X-Mock-Provider-Signature": sig})
        print(f"Webhook (payment.succeeded) sent. Status: {webhook_resp.status_code}")
        
        deal_resp = await ac.get(f"/v1/deals/{deal_id}", headers={"Authorization": f"Bearer {buyer_token}"})
        print(f"Deal status after funding: {deal_resp.json()['status']}")
        
        # 4. Outbox events
        print("\n--- 4. Checking Outbox Events ---")
        async with AsyncSession(engine) as session:
            from app.domain.deal.models import OutboxEvent
            result = await session.execute(select(OutboxEvent).where(OutboxEvent.deal_id == deal_id))
            events = result.scalars().all()
            for ev in events:
                print(f"Outbox Event: {ev.event_type} - {ev.payload}")

if __name__ == "__main__":
    asyncio.run(test())

import asyncio
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.adapters.db.session import AsyncSessionLocal
from app.domain.auth.models import User, Organization, OrganizationMember
from app.domain.deal.models import Deal
from app.domain.payment.models import PaymentIntent, EscrowHold
from app.domain.fulfillment.models import Shipment, FulfillmentConfirmation
from app.domain.trust.models import TrustSignal
from app.application.deal_state_machine import DealStateMachine, DealState
from app.application.payment_service import PaymentService
from app.application.trust_service import TrustService

# Mock Password Hash for testing (this is just "password")
MOCK_PASSWORD_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"

async def run_seed():
    print("Starting Seed Process...")
    async with AsyncSessionLocal() as db:
        
        # Clear existing seed data safely
        from sqlalchemy import text
        await db.execute(text("TRUNCATE TABLE ledger_entries CASCADE"))
        await db.execute(text("TRUNCATE TABLE ledger_transactions CASCADE"))
        await db.execute(text("TRUNCATE TABLE escrow_holds CASCADE"))
        await db.execute(text("TRUNCATE TABLE payment_intents CASCADE"))
        await db.execute(text("TRUNCATE TABLE trust_signals CASCADE"))
        await db.execute(text("TRUNCATE TABLE trust_scores CASCADE"))
        await db.execute(text("TRUNCATE TABLE shipments CASCADE"))
        await db.execute(text("TRUNCATE TABLE fulfillment_confirmations CASCADE"))
        await db.execute(text("TRUNCATE TABLE deal_events CASCADE"))
        await db.execute(text("TRUNCATE TABLE deal_participants CASCADE"))
        await db.execute(text("TRUNCATE TABLE deals CASCADE"))
        await db.execute(text("TRUNCATE TABLE organization_members CASCADE"))
        await db.execute(text("TRUNCATE TABLE organizations CASCADE"))
        await db.execute(text("TRUNCATE TABLE users CASCADE"))
        await db.commit()
        print("Cleared all existing tables for clean seed.")
        
        # 1. Platform Admin
        admin_id = uuid.uuid4()
        admin_org_id = uuid.uuid4()
        
        admin_user = User(
            id=admin_id,
            email="admin@theqa.ai",
            password_hash=MOCK_PASSWORD_HASH,
            status="active"
        )
        admin_org = Organization(
            id=admin_org_id,
            type="platform",
            name="Theqa Platform",
            status="active"
        )
        admin_member = OrganizationMember(
            org_id=admin_org_id,
            user_id=admin_id,
            role="owner"
        )
        db.add_all([admin_user, admin_org, admin_member])
        
        # 2. Merchant
        merchant_id = uuid.uuid4()
        merchant_org_id = uuid.uuid4()
        
        merchant_user = User(
            id=merchant_id,
            email="seller@example.com",
            password_hash=MOCK_PASSWORD_HASH,
            status="active"
        )
        merchant_org = Organization(
            id=merchant_org_id,
            type="merchant",
            name="Alpha Electronics",
            status="active"
        )
        merchant_member = OrganizationMember(
            org_id=merchant_org_id,
            user_id=merchant_id,
            role="owner"
        )
        db.add_all([merchant_user, merchant_org, merchant_member])
        
        # 3. Buyer (Personal)
        buyer_id = uuid.uuid4()
        buyer_org_id = uuid.uuid4()
        
        buyer_user = User(
            id=buyer_id,
            email="buyer@example.com",
            password_hash=MOCK_PASSWORD_HASH,
            status="active"
        )
        buyer_org = Organization(
            id=buyer_org_id,
            type="personal",
            name="John Doe",
            status="active"
        )
        buyer_member = OrganizationMember(
            org_id=buyer_org_id,
            user_id=buyer_id,
            role="owner"
        )
        db.add_all([buyer_user, buyer_org, buyer_member])
        
        await db.commit()
        print("Created Users and Organizations.")
        
        # 4. Inject Trust Signals for Merchant (Target > 80 score)
        # completed_orders (weight 0.20): 50 = 100 points
        db.add(TrustSignal(
            entity_type="merchant",
            entity_id=merchant_org_id,
            signal_type="completed_orders",
            value=50.0
        ))
        
        # transaction_volume (weight 0.15): 20000 = 100 points
        db.add(TrustSignal(
            entity_type="merchant",
            entity_id=merchant_org_id,
            signal_type="transaction_volume",
            value=25000.0
        ))
        
        # refund_rate (weight 0.25): 0.0 = 100 points
        db.add(TrustSignal(
            entity_type="merchant",
            entity_id=merchant_org_id,
            signal_type="refund_rate",
            value=0.0,
            metadata_payload={"deals": 50}
        ))
        
        # dispute_rate (weight 0.25): 0.0 = 100 points
        db.add(TrustSignal(
            entity_type="merchant",
            entity_id=merchant_org_id,
            signal_type="dispute_rate",
            value=0.0,
            metadata_payload={"deals": 50}
        ))
        
        # response_time (weight 0.15): 2 hours = 100 points
        db.add(TrustSignal(
            entity_type="merchant",
            entity_id=merchant_org_id,
            signal_type="response_time",
            value=2.0
        ))
        await db.commit()
        
        # Recompute trust score for merchant
        await TrustService.calculate_and_save_score(db, "merchant", merchant_org_id)
        print("Injected Trust Signals for Merchant.")
        
        # 5. Create Historic Deal (Released)
        # We will create a deal, accept it, fund it, ship it, confirm it, release it.
        # But we can also just construct it directly in DB to bypass the HTTP API constraints.
        deal = Deal(
            org_id=merchant_org_id,
            seller_user_id=merchant_id,
            buyer_user_id=buyer_id,
            title="MacBook Pro M3",
            description="Historic completed deal for demo dashboard",
            amount=2000.0,
            currency="JOD",
            fulfillment_mode="standard",
            fee_bps=200,
            fee_payer="seller",
            status=DealState.DRAFT.value
        )
        db.add(deal)
        await db.flush()
        
        await DealStateMachine.transition(db, deal, DealState.AWAITING_FUNDING.value, actor_id=buyer_id)
        
        amount_minor = 200000
        
        # Use PaymentService to fund the deal correctly to get ledger entries
        intent = await PaymentService.create_intent(
            db, deal, amount_minor, "JOD", f"idemp_seed_{uuid.uuid4()}"
        )
        
        # Simulate successful payment webhook
        import json, hmac, hashlib
        from app.application.payment_service import provider
        
        payload = json.dumps({
            "intent_id": intent.provider_intent_id,
            "status": "succeeded",
            "event_type": "payment.succeeded"
        }).encode('utf-8')
        sig = hmac.new(provider.webhook_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        
        await PaymentService.process_webhook(db, payload, sig)
        
        # Refresh deal to pick up status change
        await db.refresh(deal)
        
        # Ship
        shipment = Shipment(deal_id=deal.id, tracking_number="HISTORIC_123", carrier="Aramex", status="delivered")
        db.add(shipment)
        await DealStateMachine.transition(db, deal, DealState.IN_FULFILLMENT.value, actor_id=merchant_id)
        await db.commit()
        
        # Confirm
        conf = FulfillmentConfirmation(deal_id=deal.id, user_id=buyer_id, notes="Received in good condition")
        db.add(conf)
        await DealStateMachine.transition(db, deal, DealState.DELIVERY_CONFIRMED.value, actor_id=buyer_id)
        await db.commit()
        
        # Release
        await PaymentService.trigger_release(db, deal, admin_id)
        
        # Simulate successful release webhook
        payload = json.dumps({
            "intent_id": intent.provider_intent_id,
            "status": "succeeded",
            "event_type": "release.succeeded"
        }).encode('utf-8')
        sig = hmac.new(provider.webhook_secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        
        await PaymentService.process_webhook(db, payload, sig)
        
        # 6. Inject API Client for Merchant
        import bcrypt
        
        # We will use 'sk_test_theqademo123' and a static secret
        api_key_plaintext = "sk_test_theqademo123_secretkey123"
        key_hash = bcrypt.hashpw(b"secretkey123", bcrypt.gensalt()).decode('utf-8')
        
        from app.domain.auth.models import ApiClient
        api_client = ApiClient(
            org_id=merchant_org_id,
            key_id="theqademo123",
            key_hash=key_hash,
            scopes=["deals:write", "deals:read"]
        )
        db.add(api_client)
        await db.commit()
        
        # 7. Generate demo_partner.sh
        script_content = f"""#!/bin/bash
# Demo Partner Script to create a deal programmatically

echo "Creating a deal via API as Alpha Electronics (Partner)"
curl -X POST http://localhost:8000/v1/deals \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {api_key_plaintext}" \\
  -d '{{
    "org_id": "{merchant_org_id}",
    "title": "API Created Deal",
    "description": "This deal was created by a third-party partner integration.",
    "amount": 1500.00,
    "currency": "JOD",
    "fulfillment_mode": "standard",
    "fee_bps": 200,
    "fee_payer": "seller"
  }}' | jq .
"""
        import os
        script_path = os.path.join(os.path.dirname(__file__), 'demo_partner.sh')
        with open(script_path, "w") as f:
            f.write(script_content)
            
        print("Created API Client for Merchant.")
        
        print("\nSeed Data Summary:")
        print(f"Admin Email: admin@theqa.ai (Password: password)")
        print(f"Seller Email: seller@example.com (Password: password)")
        print(f"Buyer Email: buyer@example.com (Password: password)")
        print(f"Partner API Key: {api_key_plaintext}")
        print(f"Generated demo script at: {script_path}")
        print("\nSeed process completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_seed())

import hmac
import hashlib
import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.domain.payment.models import PaymentIntent, EscrowHold, LedgerTransaction, LedgerEntry
from app.domain.deal.models import Deal
from app.application.deal_state_machine import DealStateMachine, DealState
from app.adapters.payment.mock_provider import MockLicensedEscrowProvider

provider = MockLicensedEscrowProvider()

class PaymentService:
    @staticmethod
    async def create_intent(db: AsyncSession, deal: Deal, amount_minor: int, currency: str, idempotency_key: str) -> PaymentIntent:
        # Check idempotency
        stmt = select(PaymentIntent).where(PaymentIntent.idempotency_key == idempotency_key)
        existing_intent = (await db.execute(stmt)).scalar_one_or_none()
        
        if existing_intent:
            if existing_intent.deal_id != deal.id:
                raise HTTPException(status_code=400, detail="Idempotency key used for a different deal")
            return existing_intent

        # Call provider
        provider_intent_id = await provider.create_payment_intent(
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
            deal_id=str(deal.id)
        )
        
        # Save intent
        intent = PaymentIntent(
            deal_id=deal.id,
            amount=amount_minor / 100.0, # Wait, models.py amount is Numeric(10,2) float
            currency=currency,
            provider_intent_id=provider_intent_id,
            status="pending",
            idempotency_key=idempotency_key
        )
        db.add(intent)
        await db.commit()
        await db.refresh(intent)
        return intent

    @staticmethod
    async def process_webhook(db: AsyncSession, payload_bytes: bytes, signature: str):
        # 1. Validate signature
        expected_signature = hmac.new(
            provider.webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
            
        payload = json.loads(payload_bytes.decode('utf-8'))
        intent_id = payload.get("intent_id")
        status = payload.get("status")
        
        if status != "succeeded":
            return # Ignore non-success for MVP
            
        # 2. Find intent
        stmt = select(PaymentIntent).where(PaymentIntent.provider_intent_id == intent_id)
        intent = (await db.execute(stmt)).scalar_one_or_none()
        
        if not intent or intent.status == "succeeded":
            return # Already processed or unknown
            
        # Update intent
        intent.status = "succeeded"
        
        # Fetch deal
        stmt = select(Deal).where(Deal.id == intent.deal_id)
        deal = (await db.execute(stmt)).scalar_one()
        
        # 3. Create EscrowHold
        amount_minor = int(intent.amount * 100)
        fee_bps = deal.fee_bps
        
        # Fee logic (as requested in open question response)
        fee_minor = int(amount_minor * (fee_bps / 10000))
        seller_net_minor = amount_minor
        if deal.fee_payer == 'seller':
            seller_net_minor -= fee_minor
        elif deal.fee_payer == 'split':
            seller_net_minor -= fee_minor // 2
            
        escrow_hold = EscrowHold(
            deal_id=deal.id,
            payment_intent_id=intent.id,
            amount_minor=amount_minor,
            fee_minor=fee_minor,
            seller_net_minor=seller_net_minor,
            status="held"
        )
        db.add(escrow_hold)
        
        # 4. Shadow Ledger
        tx = LedgerTransaction(
            deal_id=deal.id,
            type="fund_escrow",
            idempotency_key=f"tx_fund_{intent.id}"
        )
        db.add(tx)
        await db.flush() # get tx.id
        
        # Balanced Entry
        # Debit external buyer account (we received the funds)
        debit_entry = LedgerEntry(
            transaction_id=tx.id,
            account_code="buyer_external",
            type="DEBIT",
            amount_minor=amount_minor
        )
        # Credit the escrow mirror (we are holding the funds)
        credit_entry = LedgerEntry(
            transaction_id=tx.id,
            account_code="provider_escrow_mirror",
            type="CREDIT",
            amount_minor=amount_minor
        )
        
        db.add(debit_entry)
        db.add(credit_entry)
        
        # 5. State Machine Transition
        await DealStateMachine.transition(db, deal, DealState.FUNDED.value, actor_id=deal.buyer_user_id)
        
        await db.commit()

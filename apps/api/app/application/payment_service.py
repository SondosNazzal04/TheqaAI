import hmac
import hashlib
import json
import uuid
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.domain.payment.models import PaymentIntent, EscrowHold, LedgerTransaction, LedgerEntry
from app.domain.deal.models import Deal
from app.application.deal_state_machine import DealStateMachine, DealState
from app.adapters.payment.mock_provider import MockLicensedEscrowProvider
from app.application.trust_service import trust_recompute

provider = MockLicensedEscrowProvider()

class PaymentService:
    @staticmethod
    async def create_intent(db: AsyncSession, deal: Deal, amount_minor: int, currency: str, idempotency_key: str) -> PaymentIntent:
        stmt = select(PaymentIntent).where(PaymentIntent.idempotency_key == idempotency_key)
        existing_intent = (await db.execute(stmt)).scalar_one_or_none()
        
        if existing_intent:
            if existing_intent.deal_id != deal.id:
                raise HTTPException(status_code=400, detail="Idempotency key used for a different deal")
            return existing_intent

        provider_intent_id = await provider.create_payment_intent(
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
            deal_id=str(deal.id)
        )
        
        intent = PaymentIntent(
            deal_id=deal.id,
            amount=amount_minor / 100.0,
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
    async def trigger_release(db: AsyncSession, deal: Deal, actor_id: uuid.UUID):
        # Only allow if state is DELIVERY_CONFIRMED
        if deal.status != DealState.DELIVERY_CONFIRMED.value:
            raise HTTPException(status_code=400, detail=f"Cannot release funds from state {deal.status}")
            
        stmt = select(PaymentIntent).where(PaymentIntent.deal_id == deal.id, PaymentIntent.status == "succeeded")
        intent = (await db.execute(stmt)).scalar_one()
        
        hold_stmt = select(EscrowHold).where(EscrowHold.payment_intent_id == intent.id)
        hold = (await db.execute(hold_stmt)).scalar_one()
        
        # Advance state to release_pending
        await DealStateMachine.transition(db, deal, DealState.RELEASE_PENDING.value, actor_id=actor_id)
        
        await provider.release_funds(
            intent_id=intent.provider_intent_id,
            seller_net_minor=hold.seller_net_minor,
            fee_minor=hold.fee_minor
        )
        await db.commit()

    @staticmethod
    async def trigger_refund(db: AsyncSession, deal: Deal, actor_id: uuid.UUID):
        if deal.status not in [DealState.FUNDED.value, DealState.IN_FULFILLMENT.value, DealState.DELIVERY_CONFIRMED.value, DealState.RELEASE_PENDING.value]:
            raise HTTPException(status_code=400, detail=f"Cannot refund from state {deal.status}")
            
        stmt = select(PaymentIntent).where(PaymentIntent.deal_id == deal.id, PaymentIntent.status == "succeeded")
        intent = (await db.execute(stmt)).scalar_one()
        
        hold_stmt = select(EscrowHold).where(EscrowHold.payment_intent_id == intent.id)
        hold = (await db.execute(hold_stmt)).scalar_one()
        
        await DealStateMachine.transition(db, deal, DealState.REFUND_PENDING.value, actor_id=actor_id)
        
        await provider.refund_funds(
            intent_id=intent.provider_intent_id,
            amount_minor=hold.amount_minor
        )
        await db.commit()

    @staticmethod
    async def process_webhook(db: AsyncSession, payload_bytes: bytes, signature: str):
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
        event_type = payload.get("event_type", "payment.succeeded")
        
        if status != "succeeded":
            return
            
        stmt = select(PaymentIntent).where(PaymentIntent.provider_intent_id == intent_id)
        intent = (await db.execute(stmt)).scalar_one_or_none()
        if not intent:
            return
            
        deal_stmt = select(Deal).where(Deal.id == intent.deal_id)
        deal = (await db.execute(deal_stmt)).scalar_one()
        
        if event_type == "payment.succeeded":
            if intent.status == "succeeded":
                return # Already processed
            intent.status = "succeeded"
            
            amount_minor = int(intent.amount * 100)
            fee_bps = deal.fee_bps
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
            
            tx = LedgerTransaction(deal_id=deal.id, type="fund_escrow", idempotency_key=f"tx_fund_{intent.id}")
            db.add(tx)
            await db.flush()
            
            db.add(LedgerEntry(transaction_id=tx.id, account_code="buyer_external", type="DEBIT", amount_minor=amount_minor))
            db.add(LedgerEntry(transaction_id=tx.id, account_code="provider_escrow_mirror", type="CREDIT", amount_minor=amount_minor))
            
            await DealStateMachine.transition(db, deal, DealState.FUNDED.value, actor_id=deal.buyer_user_id)
            
        elif event_type == "release.succeeded":
            if deal.status == DealState.RELEASED.value:
                return
            
            hold_stmt = select(EscrowHold).where(EscrowHold.payment_intent_id == intent.id)
            hold = (await db.execute(hold_stmt)).scalar_one()
            hold.status = "released"
            
            tx = LedgerTransaction(deal_id=deal.id, type="release_funds", idempotency_key=f"tx_rel_{uuid.uuid4()}")
            db.add(tx)
            await db.flush()
            
            db.add(LedgerEntry(transaction_id=tx.id, account_code="provider_escrow_mirror", type="DEBIT", amount_minor=hold.amount_minor))
            db.add(LedgerEntry(transaction_id=tx.id, account_code="provider_seller_payable_mirror", type="CREDIT", amount_minor=hold.seller_net_minor))
            db.add(LedgerEntry(transaction_id=tx.id, account_code="platform_fee_receivable_mirror", type="CREDIT", amount_minor=hold.fee_minor))
            
            await DealStateMachine.transition(db, deal, DealState.RELEASED.value)
            
            # Trust score hooks
            asyncio.create_task(trust_recompute('individual', deal.buyer_user_id))
            asyncio.create_task(trust_recompute('merchant', deal.org_id))
            
        elif event_type == "refund.succeeded":
            if deal.status == DealState.REFUNDED.value:
                return
                
            hold_stmt = select(EscrowHold).where(EscrowHold.payment_intent_id == intent.id)
            hold = (await db.execute(hold_stmt)).scalar_one()
            hold.status = "refunded"
            
            tx = LedgerTransaction(deal_id=deal.id, type="refund_funds", idempotency_key=f"tx_ref_{uuid.uuid4()}")
            db.add(tx)
            await db.flush()
            
            db.add(LedgerEntry(transaction_id=tx.id, account_code="provider_escrow_mirror", type="DEBIT", amount_minor=hold.amount_minor))
            db.add(LedgerEntry(transaction_id=tx.id, account_code="buyer_external", type="CREDIT", amount_minor=hold.amount_minor))
            
            await DealStateMachine.transition(db, deal, DealState.REFUNDED.value)

        await db.commit()

from typing import Optional, List
import uuid
import uuid6
from sqlalchemy import String, Numeric, ForeignKey, Integer, UniqueConstraint, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.adapters.db.base import Base

class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    
    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, default="JOD", nullable=False)
    provider_intent_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), onupdate=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)

    deal = relationship("Deal", backref="payment_intents")


class EscrowHold(Base):
    __tablename__ = "escrow_holds"
    
    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False)
    payment_intent_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=False)
    
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    seller_net_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    
    status: Mapped[str] = mapped_column(String, default="held", nullable=False)
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), onupdate=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)

    deal = relationship("Deal", backref="escrow_holds")
    payment_intent = relationship("PaymentIntent", backref="escrow_hold")


class LedgerTransaction(Base):
    __tablename__ = "ledger_transactions"
    
    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False) # e.g., 'fund_escrow', 'release_funds'
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)

    entries: Mapped[List["LedgerEntry"]] = relationship("LedgerEntry", back_populates="transaction", cascade="all, delete-orphan")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    
    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    transaction_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_transactions.id"), nullable=False)
    
    account_code: Mapped[str] = mapped_column(String, nullable=False) # provider_escrow_mirror, provider_seller_payable_mirror, platform_fee_receivable_mirror
    type: Mapped[str] = mapped_column(String, nullable=False) # CREDIT / DEBIT
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False)

    transaction = relationship("LedgerTransaction", back_populates="entries")

import uuid6
from datetime import datetime, timezone
from sqlalchemy import Column, String, text, CheckConstraint, ForeignKey, Integer, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional, List, Dict, Any
import string
import random

from app.adapters.db.base import Base

def generate_uuid7():
    return uuid6.uuid7()

def generate_public_code(length=8):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    public_code: Mapped[str] = mapped_column(String, unique=True, index=True, default=generate_public_code)
    org_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    seller_user_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    buyer_user_id: Mapped[Optional[uuid6.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, default="JOD", server_default="JOD")
    status: Mapped[str] = mapped_column(String, default="draft", server_default="draft")
    
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    fulfillment_mode: Mapped[str] = mapped_column(String, default="standard", server_default="standard")
    
    fee_bps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fee_payer: Mapped[str] = mapped_column(String, default="seller", server_default="seller")
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    events: Mapped[List["DealEvent"]] = relationship("DealEvent", back_populates="deal", cascade="all, delete-orphan")
    participants: Mapped[List["DealParticipant"]] = relationship("DealParticipant", back_populates="deal", cascade="all, delete-orphan")

    __mapper_args__ = {
        "version_id_col": version
    }

    def compute_fee_amount(self) -> float:
        return float(self.amount) * (self.fee_bps / 10000.0)

    def compute_net_amount(self) -> float:
        fee = self.compute_fee_amount()
        if self.fee_payer == "seller":
            return float(self.amount) - fee
        elif self.fee_payer == "buyer":
            # Buyer pays fee on top, seller gets amount
            return float(self.amount)
        elif self.fee_payer == "split":
            return float(self.amount) - (fee / 2.0)
        return float(self.amount)

class DealParticipant(Base):
    __tablename__ = "deal_participants"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    user_id: Mapped[Optional[uuid6.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    org_id: Mapped[Optional[uuid6.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False) # buyer, seller
    
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)")
    )

    deal: Mapped["Deal"] = relationship("Deal", back_populates="participants")

class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    actor_id: Mapped[Optional[uuid6.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    from_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    to_state: Mapped[str] = mapped_column(String, nullable=False)
    
    metadata_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)")
    )

    deal: Mapped["Deal"] = relationship("Deal", back_populates="events")

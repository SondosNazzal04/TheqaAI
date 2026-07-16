import uuid6
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from typing import Optional

from app.adapters.db.base import Base

def generate_uuid7():
    return uuid6.uuid7()

class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False)
    tracking_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    carrier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    deal = relationship("Deal", backref="shipments")


class FulfillmentConfirmation(Base):
    __tablename__ = "fulfillment_confirmations"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    deal_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), nullable=False)
    user_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"), nullable=False
    )

    deal = relationship("Deal", backref="fulfillment_confirmations")

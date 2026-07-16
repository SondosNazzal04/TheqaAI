import uuid6
from datetime import datetime, timezone
from sqlalchemy import String, Float, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.db.base import Base

def generate_uuid7():
    return uuid6.uuid7()

class TrustSignal(Base):
    __tablename__ = "trust_signals"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    entity_type: Mapped[str] = mapped_column(
        String,
        CheckConstraint("entity_type IN ('individual', 'merchant')"),
        nullable=False
    )
    entity_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

class TrustScore(Base):
    __tablename__ = "trust_scores"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    entity_type: Mapped[str] = mapped_column(
        String,
        CheckConstraint("entity_type IN ('individual', 'merchant')"),
        nullable=False
    )
    entity_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

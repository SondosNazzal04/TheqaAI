# pyrefly: ignore [missing-import]
import uuid6
from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from sqlalchemy import Column, String, text, CheckConstraint, ForeignKey, UniqueConstraint, DateTime, CHAR
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.postgresql import UUID, CITEXT
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional, List

from app.adapters.db.base import Base

def generate_uuid7():
    return uuid6.uuid7()

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    email: Mapped[Optional[str]] = mapped_column(CITEXT, unique=True, nullable=True)
    phone_e164: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, 
        CheckConstraint("status IN ('active', 'suspended', 'deleted')"), 
        default="active",
        nullable=False
    )
    locale: Mapped[str] = mapped_column(String, server_default=text("'ar'"), default="ar", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    memberships: Mapped[List["OrganizationMember"]] = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[List["UserSession"]] = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    kyc_profile: Mapped[Optional["KycProfile"]] = relationship("KycProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    type: Mapped[str] = mapped_column(
        String,
        CheckConstraint("type IN ('personal', 'merchant', 'platform')"),
        nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(CITEXT, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        CheckConstraint("status IN ('active', 'suspended')"),
        default="active",
        nullable=False
    )
    country: Mapped[str] = mapped_column(CHAR(2), server_default=text("'JO'"), default="JO", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    members: Mapped[List["OrganizationMember"]] = relationship("OrganizationMember", back_populates="org", cascade="all, delete-orphan")

class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_user"),
    )

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    org_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(
        String,
        CheckConstraint("role IN ('owner', 'admin', 'operator', 'viewer')"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="memberships")
    org: Mapped["Organization"] = relationship("Organization", back_populates="members")

class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    user_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")

class KycProfile(Base):
    __tablename__ = "kyc_profiles"

    id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid7)
    user_id: Mapped[uuid6.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    level: Mapped[str] = mapped_column(
        String,
        CheckConstraint("level IN ('none', 'basic', 'verified')"),
        default="none",
        nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String,
        CheckConstraint("provider IN ('mock', 'sanad')"),
        default="mock",
        nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="kyc_profile")

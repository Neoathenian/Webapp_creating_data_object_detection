from sqlalchemy import (
    BigInteger, Integer, String, Column, ForeignKey, UniqueConstraint,
    CheckConstraint, Index, func, TIMESTAMP
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class AppUser(Base):
    """Maps user's app id to google´s oauth id (or other login providers in the future)"""
    __tablename__ = "app_user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    oauth_sub = Column(String(255), unique=True, nullable=False, index=True)

class Payment(Base):
    """Historical record of Stripe payments."""
    __tablename__ = "payment"
    provider = Column(String(32), nullable=False)
    provider_event_id = Column(String(255), primary_key=True)  # UNIQUE
    user_id = Column(Integer, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_cents = Column(BigInteger, nullable=False)
    credits_granted = Column(BigInteger, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    user = relationship("AppUser")

class CreditLedger(Base):
    """Append-only log of all credit changes."""
    __tablename__ = "credit_ledger"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True)
    delta = Column(BigInteger, nullable=False)
    reason = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False)
    source_id = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_ledger_source"),
        CheckConstraint("delta <> 0", name="ck_delta_nonzero"),
        Index("ix_ledger_user_created", "user_id", "created_at"),
    )
    user = relationship("AppUser")

class UserBalance(Base):
    """Cached current balance per user."""
    __tablename__ = "user_balance"
    user_id = Column(Integer, ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True)
    balance = Column(BigInteger, nullable=False)
    user = relationship("AppUser")


class UserApiKey(Base):
    """Stores hashed API keys for programmatic access per user."""
    __tablename__ = "user_api_key"

    user_id = Column(Integer, ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True)
    key_hash = Column(String(128), nullable=False, unique=True)
    key_prefix = Column(String(32), nullable=False)
    storage_uid = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP(timezone=False), server_default=func.now(), nullable=False)
    last_used_at = Column(TIMESTAMP(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_user_api_key_storage_uid", "storage_uid"),
    )

    user = relationship("AppUser")

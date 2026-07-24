"""
models.py – SQLAlchemy ORM models for the Korean learning app.
Tables:
  - User       : authenticated Google users
  - Card       : flash-cards (jamo, syllables, vocab, …)
  - ReviewLog  : every review event
  - DailyStudy : daily study-time tracking
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # active-days / rest-points gamification
    active_days_this_month = Column(Integer, default=0)
    rest_points            = Column(Integer, default=0)
    last_active_date       = Column(Date, nullable=True)

    # ── User-configurable daily targets ────────────────────
    target_daily_minutes   = Column(Integer, default=20)   # soft cap in minutes
    target_daily_new_cards = Column(Integer, default=5)    # new cards per day via Learn
    strict_mode            = Column(Boolean, default=False) # True → hard redirect to Zen

    reviews = relationship("ReviewLog", back_populates="user", cascade="all, delete-orphan")
    daily_studies = relationship("DailyStudy", back_populates="user", cascade="all, delete-orphan")
    user_cards = relationship("UserCard", back_populates="user", cascade="all, delete-orphan")


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    # Didactic phase: jamo | syllable | vocab | phrase
    phase = Column(String, nullable=False, index=True)
    # Group within phase: vowels | consonants | basic-syllables | etc.
    group_name = Column(String, nullable=True, index=True)
    front = Column(String, nullable=False)          # character / word shown
    back = Column(String, nullable=False)           # reading / meaning
    romanji = Column(String, nullable=True)         # romanisation (romanization / romaja)
    audio_file = Column(String, nullable=True)      # filename in static/audio/
    notes = Column(Text, nullable=True)             # mnemonic hint

    user_cards = relationship("UserCard", back_populates="card")


class UserCard(Base):
    """Per-user SRS state for each card (SM-2 inspired)."""
    __tablename__ = "user_cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False, index=True)

    # SRS stage: 0=unseen, 1=introduced via Learn, 2+=active SRS
    srs_stage       = Column(Integer, default=0)
    # Date when srs_stage first went from 0→1 (Learn introduction)
    introduced_date = Column(Date, nullable=True)
    # SM-2 fields
    interval = Column(Integer, default=1)       # days until next review
    repetitions = Column(Integer, default=0)    # successful reviews in a row
    ease_factor = Column(Float, default=2.5)    # SM-2 ease factor
    due_date = Column(DateTime, default=datetime.now)
    last_reviewed = Column(Date, nullable=True)

    is_new = Column(Boolean, default=True)

    user = relationship("User", back_populates="user_cards")
    card = relationship("Card", back_populates="user_cards")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    quality = Column(Integer, nullable=False)   # 0-5 rating
    time_spent_ms = Column(Integer, nullable=True)

    user = relationship("User", back_populates="reviews")


class DailyStudy(Base):
    """Tracks total focused study seconds per user per day."""
    __tablename__ = "daily_studies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    study_date = Column(Date, default=date.today, nullable=False)
    seconds_studied = Column(Integer, default=0)

    user = relationship("User", back_populates="daily_studies")

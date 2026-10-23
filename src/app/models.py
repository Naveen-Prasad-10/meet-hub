"""SQLAlchemy models."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass



class Meeting(Base):
    """Meeting model to store processed results."""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    speakers: Mapped[str] = mapped_column(Text)  # JSON string of speakers
    transcript: Mapped[str] = mapped_column(Text)
    processed_data: Mapped[str] = mapped_column(Text)  # JSON string of all extracted results
    
    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, title={self.title})>"


class CalendarEvent(Base):
    """CalendarEvent model to store tasks and deadlines."""

    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[str] = mapped_column(String(100), nullable=False) # Store as string for flexibility (e.g. "2026-04-10" or "Friday")
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(50), default="MEDIUM")
    source_meeting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE") # ACTIVE, RESOLVED, CANCELLED
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CalendarEvent(id={self.id}, title={self.title}, date={self.date})>"

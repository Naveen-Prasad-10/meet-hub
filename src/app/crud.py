"""CRUD operations for database models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEvent
from app.schemas import CalendarEventCreate


# CalendarEvent CRUD operations
def get_calendar_events(db: Session, skip: int = 0, limit: int = 100) -> list[CalendarEvent]:
    """Get a list of calendar events."""
    stmt = select(CalendarEvent).order_by(CalendarEvent.date.asc()).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def create_calendar_event(db: Session, event: CalendarEventCreate) -> CalendarEvent:
    """Create a new calendar event."""
    db_event = CalendarEvent(**event.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


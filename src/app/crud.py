"""CRUD operations for database models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CalendarEvent
from app.schemas import CalendarEventCreate


# CalendarEvent CRUD operations
def get_calendar_events(
    db: Session, 
    skip: int = 0, 
    limit: int = 100, 
    include_resolved: bool = True
) -> list[CalendarEvent]:
    """Get a list of calendar events."""
    stmt = select(CalendarEvent)
    if not include_resolved:
        stmt = stmt.where(CalendarEvent.status == "ACTIVE")
    stmt = stmt.order_by(CalendarEvent.date.asc()).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def create_calendar_event(db: Session, event: CalendarEventCreate) -> CalendarEvent:
    """Create a new calendar event."""
    db_event = CalendarEvent(**event.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def resolve_calendar_event(
    db: Session, 
    event_id: int, 
    reason: str, 
    status: str = "RESOLVED"
) -> CalendarEvent | None:
    """Mark a calendar event as resolved or cancelled with an explicit reasoning."""
    event = db.get(CalendarEvent, event_id)
    if event:
        event.status = status
        event.resolution_reason = reason
        db.commit()
        db.refresh(event)
    return event


def delete_calendar_event(db: Session, event_id: int) -> bool:
    """Delete a calendar event."""
    event = db.get(CalendarEvent, event_id)
    if event:
        db.delete(event)
        db.commit()
        return True
    return False


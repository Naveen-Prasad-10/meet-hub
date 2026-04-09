import os
import datetime
import json

from dotenv import load_dotenv

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.settings import get_settings
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import crud
from app.database import get_db, init_db
from app.schemas import (
    TranscriptProcessRequest, TranscriptProcessResponse,
    MeetingQueryRequest, MeetingQueryResponse,
    SentimentAnalysisRequest, SentimentAnalysisResponse,
    MeetingSummaryRequest, MeetingSummaryResponse,
    CrossMeetingAnalysisRequest, CrossMeetingAnalysisResponse,
    IntelligenceExtractionRequest, IntelligenceExtractionResponse,
    CalendarEventCreate, CalendarEventResponse
)
from app.services import (
    process_transcript, answer_query, analyze_transcript_sentiment,
    generate_summary, analyze_cross_meeting_query, extract_intelligence
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database tables on startup
    init_db()
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Meeting intelligence platform — extract decisions, actions, and sentiment from transcripts",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse



@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Transcript processing endpoints
@app.post("/transcripts/process", response_model=TranscriptProcessResponse)
async def process_transcript_endpoint(request: TranscriptProcessRequest):
    """Process a meeting transcript and return structured metadata."""
    result = process_transcript(request.transcript)
    return result


# Intelligence Extraction endpoint
@app.post("/transcripts/extract", response_model=IntelligenceExtractionResponse)
async def extract_intelligence_endpoint(request: IntelligenceExtractionRequest):
    """Extract high-value, deduplicated, prioritized intelligence from a transcript."""
    processed = process_transcript(request.transcript)
    result = extract_intelligence(processed)
    return result


# Meeting Q&A endpoints
@app.post("/meetings/query", response_model=MeetingQueryResponse)
async def meeting_query_endpoint(request: MeetingQueryRequest):
    """Answer questions based on meeting transcript context."""
    result = answer_query(request.query, request.context)
    return result


# Sentiment Analysis endpoints
@app.post("/meetings/sentiment", response_model=SentimentAnalysisResponse)
async def sentiment_analysis_endpoint(request: SentimentAnalysisRequest):
    """Analyze sentiment and tone in a meeting transcript."""
    result = analyze_transcript_sentiment(request.transcript)
    return result


# Meeting Summary endpoints
@app.post("/meetings/summary", response_model=MeetingSummaryResponse)
async def meeting_summary_endpoint(request: MeetingSummaryRequest):
    """Generate a high-level summary of a meeting."""
    result = generate_summary(
        decisions=request.decisions,
        action_items=request.action_items,
        sentiment_timeline=request.sentiment_timeline,
        speaker_summary=request.speaker_summary
    )
    return result


# Cross-Meeting Analysis endpoints
@app.post("/meetings/cross-analyze", response_model=CrossMeetingAnalysisResponse)
async def cross_meeting_analysis_endpoint(request: CrossMeetingAnalysisRequest):
    """Answer complex queries requiring information from multiple meetings."""
    result = analyze_cross_meeting_query(
        query=request.query,
        meetings=request.meetings
    )
    return result


# Meeting Management
@app.get("/meetings", status_code=200)
async def list_meetings(db: Session = Depends(get_db)):
    """List all processed meetings."""
    from app.models import Meeting
    stmt = select(Meeting).order_by(Meeting.date.desc())
    meetings = list(db.execute(stmt).scalars().all())
    return meetings


@app.post("/meetings", status_code=201)
async def save_meeting(data: dict, db: Session = Depends(get_db)):
    """Save a processed meeting and auto-assign action items to calendar."""
    from app.models import Meeting
    
    # 1. Save Meeting
    processed_data_dict = data.get("processed_data", {})
    db_meeting = Meeting(
        title=data.get("title", "Untitled Meeting"),
        word_count=data.get("word_count", 0),
        speakers=json.dumps(data.get("speakers", [])),
        transcript=data.get("transcript", ""),
        processed_data=json.dumps(processed_data_dict)
    )
    db.add(db_meeting)
    db.commit()
    db.refresh(db_meeting)

    # 2. Auto-assign Action Items to Calendar
    action_items = processed_data_dict.get("action_items", [])
    for item in action_items:
        # If no deadline, default to 3 days from now for "upcoming"
        deadline = item.get("deadline")
        if not deadline or deadline.lower() in ["tbd", "unknown", "none", "-"]:
            deadline = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        
        event_data = CalendarEventCreate(
            title=item.get("task", "Unnamed Task"),
            description=f"Action item from meeting: {db_meeting.title}",
            date=deadline,
            owner=item.get("owner", "Unassigned"),
            priority=item.get("priority", "MEDIUM"),
            source_meeting_id=db_meeting.id
        )
        crud.create_calendar_event(db, event_data)

    return db_meeting


# Calendar Endpoints
@app.get("/calendar", response_model=list[CalendarEventResponse])
async def list_calendar_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all upcoming work/calendar events."""
    return crud.get_calendar_events(db, skip=skip, limit=limit)


@app.post("/calendar", response_model=CalendarEventResponse, status_code=201)
async def create_calendar_event(event: CalendarEventCreate, db: Session = Depends(get_db)):
    """Manually add an event to the calendar."""
    return crud.create_calendar_event(db, event)


@app.post("/calendar/sync", status_code=200)
async def sync_calendar_from_meetings(db: Session = Depends(get_db)):
    """Rebuild calendar events from all saved meetings.
    
    Scans every meeting's processed_data for action items and creates
    calendar events for any that don't already have one. Safe to call
    multiple times — skips meetings that already have events linked.
    """
    from app.models import Meeting, CalendarEvent
    from sqlalchemy import select as sa_select

    meetings = list(db.execute(sa_select(Meeting)).scalars().all())
    created = 0

    for meeting in meetings:
        # Check if this meeting already has calendar events
        existing = db.execute(
            sa_select(CalendarEvent).where(CalendarEvent.source_meeting_id == meeting.id)
        ).scalars().first()
        if existing:
            continue  # already synced

        try:
            processed_data_dict = json.loads(meeting.processed_data or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        action_items = processed_data_dict.get("action_items", [])
        for item in action_items:
            deadline = item.get("deadline")
            if not deadline or str(deadline).lower() in ["tbd", "unknown", "none", "-"]:
                deadline = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d")

            event_data = CalendarEventCreate(
                title=item.get("task", "Unnamed Task"),
                description=f"Action item from meeting: {meeting.title}",
                date=deadline,
                owner=item.get("owner", "Unassigned"),
                priority=item.get("priority", "MEDIUM"),
                source_meeting_id=meeting.id
            )
            crud.create_calendar_event(db, event_data)
            created += 1

    return {"synced_meetings": len(meetings), "events_created": created}

# Mount the static frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )

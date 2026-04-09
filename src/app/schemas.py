"""Pydantic schemas for request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict



# Transcript processing schemas
class TranscriptMetadata(BaseModel):
    """Schema for transcript metadata."""

    meeting_date: str | None = None
    word_count: int = 0
    num_speakers: int = 0
    speakers: list[str] = []


class Decision(BaseModel):
    """Schema for a decision made during a meeting."""

    decision: str
    context: str | None = None


class ActionItem(BaseModel):
    """Schema for an action item from a meeting."""

    who: str
    what: str
    when: str | None = None
    context: str | None = None


class TranscriptProcessResponse(BaseModel):
    """Schema for transcript processing response."""

    clean_text: str
    metadata: TranscriptMetadata
    decisions: list[Decision] = []
    action_items: list[ActionItem] = []


class TranscriptProcessRequest(BaseModel):
    """Schema for transcript processing request."""

    transcript: str


# Meeting Q&A schemas
class Source(BaseModel):
    """Schema for a cited source."""

    meeting: str
    snippet: str


class MeetingQueryResponse(BaseModel):
    """Schema for meeting Q&A response."""

    answer: str
    sources: list[Source] = []


class MeetingQueryRequest(BaseModel):
    """Schema for meeting Q&A request."""

    query: str
    context: list[str]  # List of transcript chunks to search


# Sentiment Analysis schemas
class TimelineSegment(BaseModel):
    """Schema for a timeline segment in sentiment analysis."""

    segment: str
    sentiment: str
    tone: str | None = None
    speaker: str


class SpeakerSummary(BaseModel):
    """Schema for speaker sentiment summary."""

    speaker: str
    overall_sentiment: str
    dominant_tone: str | None = None


class SentimentAnalysisResponse(BaseModel):
    """Schema for sentiment analysis response."""

    timeline: list[TimelineSegment]
    speaker_summary: list[SpeakerSummary]


class SentimentAnalysisRequest(BaseModel):
    """Schema for sentiment analysis request."""

    transcript: str


# Meeting Summary schemas
class MeetingSummary(BaseModel):
    """Schema for meeting summary."""

    total_decisions: int
    total_actions: int
    overall_sentiment: str
    key_decision: str | None = None
    urgent_action: str | None = None


class MeetingSummaryResponse(BaseModel):
    """Schema for meeting summary response."""

    summary: MeetingSummary


class MeetingSummaryRequest(BaseModel):
    """Schema for meeting summary request."""

    decisions: list[dict]
    action_items: list[dict]
    sentiment_timeline: list[dict]
    speaker_summary: list[dict]


# Intelligence Extraction schemas
class ExtractedDecision(BaseModel):
    """Schema for a prioritized, confidence-scored decision."""

    text: str
    priority: str  # HIGH | MEDIUM | LOW
    confidence: float  # 0.0–1.0


class ExtractedActionItem(BaseModel):
    """Schema for a prioritized, confidence-scored action item."""

    owner: str
    task: str
    deadline: str | None = None
    priority: str  # HIGH | MEDIUM | LOW
    confidence: float  # 0.0–1.0


class IntelligenceExtractionResponse(BaseModel):
    """Schema for intelligence extraction response."""

    decisions: list[ExtractedDecision] = []
    action_items: list[ExtractedActionItem] = []


class IntelligenceExtractionRequest(BaseModel):
    """Schema for intelligence extraction request."""

    transcript: str


# Cross-Meeting Analysis schemas
class CrossMeetingSource(BaseModel):
    """Schema for a cross-meeting source citation."""

    meeting: str
    date: str
    snippet: str


class CrossMeetingAnalysisResponse(BaseModel):
    """Schema for cross-meeting analysis response."""

    answer: str
    cross_meeting_insights: str
    sources: list[CrossMeetingSource] = []


class CrossMeetingAnalysisRequest(BaseModel):
    """Schema for cross-meeting analysis request."""

    query: str
    meetings: list[dict]  # List of meeting data with decisions, actions, sentiment, etc.


# Calendar schemas
class CalendarEventBase(BaseModel):
    """Base calendar event schema."""

    title: str
    description: str | None = None
    date: str
    owner: str | None = None
    priority: str = "MEDIUM"
    source_meeting_id: int | None = None


class CalendarEventCreate(CalendarEventBase):
    """Schema for creating a calendar event."""

    pass


class CalendarEventResponse(CalendarEventBase):
    """Schema for calendar event response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

# meet-hub

This file provides context about the project for AI assistants.

## Project Overview

MeetHub is a meeting intelligence platform. Users upload transcripts and the system extracts decisions, action items, sentiment, summaries, and supports cross-meeting queries.

- **Ecosystem**: Python

## Tech Stack

- Web Framework: FastAPI
- ORM: SQLAlchemy
- Validation: Pydantic
- Migrations: Alembic

## Project Structure

```
meet-hub/
├── pyproject.toml        # Project config & dependencies
├── alembic.ini           # Migration config
├── src/
│   └── app/              # Application code
│       ├── main.py       # FastAPI app & all endpoints
│       ├── models.py     # Meeting, CalendarEvent models
│       ├── schemas.py    # Request/response schemas
│       ├── crud.py       # CalendarEvent CRUD
│       ├── database.py   # DB engine & session
│       ├── settings.py   # Pydantic settings
│       └── services/     # Business logic
│           ├── transcript_processor.py
│           ├── intelligence_extractor.py
│           ├── sentiment_analyzer.py
│           ├── meeting_summary.py
│           ├── meeting_qa.py
│           └── cross_meeting_analyzer.py
├── frontend/             # Static HTML/CSS/JS dashboard
├── tests/                # Test suite
└── migrations/           # Alembic migrations
```

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /transcripts/process` - Process meeting transcript → structured insights
  - Accepts: `{"transcript": "raw transcript text"}`
  - Returns: `{clean_text, metadata, decisions, action_items}`
- `POST /transcripts/extract` - Extract prioritized, confidence-scored intelligence
  - Accepts: `{"transcript": "raw transcript text"}`
  - Returns: `{decisions: [{text, priority, confidence}], action_items: [{owner, task, deadline, priority, confidence}]}`
- `POST /meetings/query` - Answer questions based on transcript context
  - Accepts: `{"query": "question", "context": ["chunks"]}`
  - Returns: `{answer, sources}`
- `POST /meetings/sentiment` - Analyze sentiment and tone
  - Accepts: `{"transcript": "clean text"}`
  - Returns: `{timeline, speaker_summary}`
- `POST /meetings/summary` - Generate meeting summary
  - Accepts: `{decisions, action_items, sentiment_timeline, speaker_summary}`
  - Returns: `{summary: {total_decisions, total_actions, overall_sentiment, key_decision, urgent_action}}`
- `POST /meetings/cross-analyze` - Cross-meeting analysis
  - Accepts: `{query, meetings: [...]}`
  - Returns: `{answer, cross_meeting_insights, sources}`
- `GET /meetings` - List all saved meetings
- `POST /meetings` - Save a processed meeting (auto-assigns action items to calendar)
- `GET /calendar` - List calendar events
- `POST /calendar` - Create a calendar event
- `POST /calendar/sync` - Rebuild calendar events from all saved meetings (recovery endpoint)

## Common Commands

- `uv sync` - Install dependencies
- `cd src && python -m uvicorn app.main:app --reload` - Start dev server
- `python -m pytest` - Run tests

## Maintenance

Keep CLAUDE.md updated when:

- Adding/removing dependencies
- Changing project structure
- Adding new features or services
- Modifying build/dev workflows

AI assistants should suggest updates to this file when they notice relevant changes.

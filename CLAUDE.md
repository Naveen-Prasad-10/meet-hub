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
│           ├── cross_meeting_analyzer.py
│           └── structured_extractor.py
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
- `POST /transcripts/analyze` - Evidence-anchored structured report (typed transcript)
  - Accepts: `{"transcript": "raw transcript text"}`
  - Returns: `{meeting_title, summary, decisions: [{decision, evidence}], tasks: [{title, description, assignee, due_date, evidence}], blockers: [{issue, evidence}]}`
- `POST /transcripts/analyze/file` - Same report from an uploaded file (multipart)
  - Accepts: `file` (`.txt`, `.vtt`, `.md`; other suffixes → 400)
  - Returns: same shape as `/transcripts/analyze`
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

- `uv sync --extra dev` - Install dependencies (includes pytest)
- `cd src && python -m uvicorn app.main:app --reload` - Start dev server
- `python -m pytest` - Run tests
- `uv pip install en_core_web_sm` - Reinstall the spaCy model if `uv sync` prunes it
  (`transcript_processor` downloads it on first import if it is missing)

## Extraction Guarantees

`structured_extractor.py` implements a strict no-hallucination contract:

- Nothing is emitted that the transcript does not explicitly support.
- Every decision / task / blocker carries the verbatim transcript line as `evidence`.
- `assignee` is null unless a named person is identified (pronouns and collectives
  such as "we"/"the team" never resolve to an individual).
- `due_date` is null unless a concrete date is stated and resolves to `YYYY-MM-DD`.
- Hedged language ("maybe", "not decided", "let's consider") never yields a decision.
- An empty transcript returns nulls and empty lists.

Keep these invariants when editing that module — `tests/test_structured_extractor.py`
pins them.

## Maintenance

Keep CLAUDE.md updated when:

- Adding/removing dependencies
- Changing project structure
- Adding new features or services
- Modifying build/dev workflows

AI assistants should suggest updates to this file when they notice relevant changes.

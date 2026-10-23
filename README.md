# meet-hub

An intelligent meeting operations platform — upload transcripts and extract decisions, action items, sentiment analysis, and summaries.

## Features

- **Transcript Processing** — Extract speakers, decisions, and action items from raw transcripts
- **Structured Extraction** — Evidence-anchored report (`/transcripts/analyze`) with decisions, tasks, blockers and verbatim evidence
- **Intelligence Extraction** — Prioritized, confidence-scored, deduplicated insights
- **Sentiment Analysis** — Per-speaker sentiment timeline and tone detection
- **Meeting Summaries** — High-level overview with key decisions and urgent actions
- **Cross-Meeting Analysis** — Query patterns across multiple meetings
- **Meeting Q&A** — Ask questions against transcript context
- **Calendar Integration** — Auto-assign action items to a project calendar

## Tech Stack

- **FastAPI** — Async web framework
- **SQLAlchemy** — ORM and database toolkit
- **Pydantic** — Data validation
- **Alembic** — Database migrations

## Prerequisites

- [Python](https://www.python.org/) 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (Recommended package manager)

## Getting Started

```bash
cp .env.example .env
uv sync --extra dev
cd src && python -m uvicorn app.main:app --reload
```

The API will be running at [http://localhost:8000](http://localhost:8000).

> `uv sync` prunes packages that are not in the lock file. If the spaCy model
> disappears, reinstall it with
> `uv pip install en_core_web_sm` (or just import the app once — it downloads
> the model automatically).

## Transcript Input

Transcripts can be supplied two ways — both reach the same extraction pipeline:

1. **Typed / pasted** in the *Add Meeting* view, sent as JSON to
   `POST /transcripts/analyze`.
2. **Uploaded file** — drag & drop a `.txt`, `.vtt` or `.md` transcript, sent as
   multipart to `POST /transcripts/analyze/file` (unsupported suffixes return `400`).

## Structured Extraction Contract

`/transcripts/analyze` returns only what the transcript explicitly supports:

```json
{
  "meeting_title": "Q3 Pricing Launch Sync",
  "summary": "Sarah, Marcus and Dana met on 2026-09-28 and recorded 1 finalized decision ...",
  "decisions": [{ "decision": "...", "evidence": "Sarah: We decided to ..." }],
  "tasks": [{
    "title": "Draft the migration plan",
    "description": "Priya will draft the migration plan by Friday",
    "assignee": "Priya",
    "due_date": "2026-10-02",
    "evidence": "Marcus: Priya will draft the migration plan by Friday."
  }],
  "blockers": [{ "issue": "...", "evidence": "Priya: I'm blocked on the legal sign-off." }]
}
```

Guarantees: every item keeps the verbatim transcript line as `evidence`;
`assignee` and `due_date` are `null` unless the transcript states them; hedged
language never becomes a decision; an empty transcript returns nulls and empty
lists.

## Project Structure

```
meet-hub/
├── pyproject.toml           # Project configuration and dependencies
├── alembic.ini              # Alembic migration configuration
├── migrations/              # Database migrations
│   ├── env.py
│   └── script.py.mako
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py          # FastAPI app & endpoints
│       ├── settings.py      # Pydantic settings
│       ├── database.py      # DB engine & session
│       ├── models.py        # Meeting & CalendarEvent models
│       ├── schemas.py       # Request/response schemas
│       ├── crud.py          # CalendarEvent CRUD ops
│       └── services/        # Business logic
│           ├── transcript_processor.py
│           ├── intelligence_extractor.py
│           ├── sentiment_analyzer.py
│           ├── meeting_summary.py
│           ├── meeting_qa.py
│           ├── cross_meeting_analyzer.py
│           └── structured_extractor.py
├── frontend/
│   ├── index.html           # Dashboard UI
│   ├── styles.css           # Styling
│   └── app.js               # Frontend logic
├── tests/                   # Test suite
├── .env.example             # Environment template
└── .gitignore
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Root |
| `GET` | `/health` | Health check |
| `POST` | `/transcripts/process` | Process a transcript → structured metadata |
| `POST` | `/transcripts/extract` | Extract prioritized intelligence |
| `POST` | `/transcripts/analyze` | Structured report from a typed transcript |
| `POST` | `/transcripts/analyze/file` | Structured report from an uploaded file |
| `POST` | `/meetings/query` | Q&A against transcript context |
| `POST` | `/meetings/sentiment` | Sentiment & tone analysis |
| `POST` | `/meetings/summary` | Generate meeting summary |
| `POST` | `/meetings/cross-analyze` | Cross-meeting analysis |
| `GET` | `/meetings` | List all meetings |
| `POST` | `/meetings` | Save a processed meeting |
| `GET` | `/calendar` | List calendar events |
| `POST` | `/calendar` | Create calendar event |

## Commands

```bash
uv sync --extra dev                                  # Install dependencies + test tools
cd src && python -m uvicorn app.main:app --reload     # Dev server
python -m pytest                                      # Run tests
uv run alembic revision --autogenerate -m "desc"      # Generate migration
uv run alembic upgrade head                           # Apply migrations
```

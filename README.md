# meet-hub

An intelligent meeting operations platform — upload transcripts and extract decisions, action items, sentiment analysis, and summaries.

## Features

- **Transcript Processing** — Extract speakers, decisions, and action items from raw transcripts
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
uv sync
cd src && python -m uvicorn app.main:app --reload
```

The API will be running at [http://localhost:8000](http://localhost:8000).

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
│           └── cross_meeting_analyzer.py
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
uv sync                                              # Install dependencies
cd src && python -m uvicorn app.main:app --reload     # Dev server
python -m pytest                                      # Run tests
uv run alembic revision --autogenerate -m "desc"      # Generate migration
uv run alembic upgrade head                           # Apply migrations
```

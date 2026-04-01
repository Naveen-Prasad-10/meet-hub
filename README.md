# meet-hub

This project was created with [Better Fullstack](https://github.com/Marve10s/Better-Fullstack), a high-performance Python stack.

## Features

- **Python** - Modern, readable programming language
- **FastAPI** - Modern, fast (high-performance) async web framework
- **SQLAlchemy** - The SQL toolkit and ORM for Python
- **Alembic** - Database migrations for SQLAlchemy
- **Pydantic** - Data validation using Python type hints
- **pydantic-settings** - Settings management with environment variables

## Prerequisites

- [Python](https://www.python.org/) 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (Recommended package manager)

## Getting Started

First, copy the environment file:

```bash
cp .env.example .env
```

Then, install dependencies using uv:

```bash
uv sync
```

Start the FastAPI development server:

```bash
uv run uvicorn app.main:app --reload
```

The API will be running at [http://localhost:8000](http://localhost:8000).

## Project Structure

```
meet-hub/
├── pyproject.toml        # Project configuration and dependencies
├── alembic.ini           # Alembic migration configuration
├── migrations/           # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/
│   └── app/
│       ├── __init__.py
│       └── main.py       # Application entry point
│       ├── settings.py   # Application settings (pydantic-settings)
│       ├── database.py   # Database configuration
│       ├── models.py     # SQLAlchemy models
│       ├── schemas.py    # Pydantic schemas
│       └── crud.py       # CRUD operations
├── tests/
│   ├── __init__.py
│   └── test_main.py      # Test suite
│   └── test_database.py  # Database tests
├── .env.example          # Environment variables template
└── .gitignore
```

## Available Commands

- `uv run uvicorn app.main:app --reload`: Start FastAPI dev server
- `uv run uvicorn app.main:app`: Start FastAPI production server
- `uv run pytest`: Run tests
- `uv run alembic revision --autogenerate -m "description"`: Generate migration
- `uv run alembic upgrade head`: Apply migrations
- `uv run alembic downgrade -1`: Rollback last migration

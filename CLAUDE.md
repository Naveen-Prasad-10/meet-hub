# meet-hub

This file provides context about the project for AI assistants.

## Project Overview

- **Ecosystem**: Python

## Tech Stack

- Web Framework: fastapi
- ORM: sqlalchemy
- Validation: pydantic

## Project Structure

```
meet-hub/
├── pyproject.toml   # Project config
├── src/
│   └── app/         # Application code
├── tests/           # Test suite
├── migrations/      # Database migrations
```

## Common Commands

- `uv sync` - Install dependencies
- `uv run uvicorn app.main:app --reload` - Start dev server
- `uv run pytest` - Run tests

## Maintenance

Keep CLAUDE.md updated when:

- Adding/removing dependencies
- Changing project structure
- Adding new features or services
- Modifying build/dev workflows

AI assistants should suggest updates to this file when they notice relevant changes.

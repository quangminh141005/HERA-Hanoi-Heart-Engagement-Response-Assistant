# HERA - Hanoi Heart Engagement Response Assistant

HERA is a customer-care assistant scaffold for Hanoi Heart Hospital. It is
designed for official hospital knowledge-based QA, emergency symptom handling,
human handoff, and future integration with appointment, doctor schedule, and
service systems.

This repository reuses a proven full-stack architecture while removing the old
previous product domain and replacing the previous frontend framework with a
React + Vite shell.

## Structure

```text
├── AGENT.md
├── .env.example
├── docker-compose.yml
├── apps/
│   ├── backend/       # FastAPI, SQLAlchemy, Alembic, AI architecture
│   └── frontend/      # React, TypeScript, Vite, React Router
├── packages/
│   └── shared/        # Shared contracts and cross-app notes
├── docs/
├── scripts/
└── tests/
```

## Backend

```bash
cd apps/backend
python -m pip install -r requirements.txt
python -m pip install -r ../../requirements-dev.txt
uvicorn app.main:app --reload
```

RAG answer generation uses the FPT Cloud/OpenAI-compatible API first and falls
back to Gemini when both keys are present:

```bash
cp .env.example .env
# Fill these in .env:
LLM_PROVIDER=fpt
LLM_FALLBACK_PROVIDER=gemini
LLM_MODEL=your-fpt-chat-model
OPEN_API_KEY=...
OPEN_API_BASE_URL=https://mkp-api.fptcloud.com
OPEN_API_EMBEDDING_MODEL=Vietnamese_Embedding
GEMINI_API_KEY=...
```

Health endpoints:

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/health/db`

No hospital domain schema has been created yet. The backend includes the
database engine, session dependency, SQLAlchemy base, Alembic environment, and
database connectivity health check only.

## Frontend

```bash
cd apps/frontend
npm install
npm run dev
```

The frontend uses `VITE_API_BASE_URL`, defaulting to
`http://localhost:8000/api/v1`.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Services:

- PostgreSQL with pgvector
- Redis for production-style rate limiting
- FastAPI backend
- Vite-built frontend served by Nginx

## Safety Scope

HERA is not a doctor AI. It should not diagnose, prescribe, or provide
treatment instructions. Emergency language is routed to urgent-care guidance,
and administrative answers must be grounded in official hospital sources.

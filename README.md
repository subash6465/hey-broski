# Hey Broski

Hey Broski is a local-first personal admin copilot. It turns email, calendar, and document context into a grounded daily brief and explicit action proposals. Demo mode supplies sample data without connected accounts; chat answers still require a local model.

## What works today

- Grounded chat over demo or uploaded data for attention summaries, follow-ups, renewals, and calendar conflicts
- Answers generated only by a local Ollama `qwen3:4b` model; inference errors are reported rather than replaced with canned text
- Persistent SQLite conversations, action cards, documents, and audit events
- Approval and dismissal workflow—no proposal executes silently
- Local PDF, TXT, Markdown, and CSV upload and keyword retrieval
- Responsive action inbox, document vault, source citations, and audit log
- Production-style multi-stage frontend image and non-root API image

The current UI is a local React chat shell rather than hosted ChatKit. The current ChatKit session API expects an OpenAI workflow and returns an OpenAI client secret, which conflicts with this project's zero-paid-API and local-inference rules. The backend contracts are kept separate so a future fully self-hosted ChatKit adapter can replace the shell without changing the domain services.

Gmail, Outlook, calendar sync, semantic vector search, and live n8n workflow execution remain planned integrations. The UI does not pretend they are connected.

## Quickstart

Prerequisites: Docker Desktop (or Docker Engine with Compose v2). The CPU-only local model works best with at least 8 GB of memory available to Docker.

```bash
git clone <repo>
cd hey-broski
cp .env.example .env
docker compose up --build
```

On PowerShell, use `Copy-Item .env.example .env`, or run `./scripts/bootstrap.ps1`.

Open:

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- n8n: http://localhost:5678

The `ollama-model` service downloads `qwen3:4b` on the first Compose start. This can take several minutes; the app shows when the model is ready. Demo data and document upload remain available while it downloads. Check progress with:

```bash
docker compose logs -f ollama-model
```

If you already have an `.env` from an earlier version, set `HEYBROSKI_USE_OLLAMA=true`, `HEYBROSKI_CHAT_MODEL=qwen3:4b`, and `OLLAMA_TIMEOUT_SECONDS=45`, then run `docker compose up --build --force-recreate`. Existing environment files are never overwritten automatically. If inference is disabled or unavailable, chat returns an actionable error and does not save a partial turn.

To verify that a real local model answered, run `bash scripts/verify-local-chat.sh` from the Codespaces terminal. It exits nonzero unless Ollama generated the response. In the UI, successful answers say **Answered by local model**. If the check fails, inspect `docker compose logs --tail=100 ollama-model ollama api` and `docker compose exec ollama ollama list`.

Docker Compose routes internal HTTP calls through `host.docker.internal` and
the published ports. This is intentional: some Codespaces Docker environments
resolve sibling service names but filter direct bridge traffic between them.

Then ask: `What needs my attention this week?`

## Local development

Backend (Python 3.11+):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r apps/api/requirements-dev.txt
uvicorn apps.api.app.main:app --reload
```

Frontend (Node 20+):

```bash
cd apps/web
npm install
npm run dev
```

Run checks:

```bash
pytest apps/api/tests
cd apps/web && npm run build
```

## Architecture

```text
Browser / Next.js
        │ relative /api proxy
        ▼
FastAPI routes ── Assistant service ── Ollama (optional)
        │                 │
        └──── SQLite repository ── local documents
                    │
              immutable audit events
```

The API is separated into configuration, validation schemas, the assistant/domain service, and a SQLite repository. This keeps the MVP small while leaving clear boundaries for connector and vector-index implementations.

Data defaults to `.hey-broski/` locally and `/data/heybroski` in Docker. The Docker named volume persists it across restarts.

## Safety model

- Read-only retrieval is allowed immediately.
- Suggested writes become pending action cards.
- A user must approve or dismiss each card.
- Decisions and uploads are recorded in the local audit log.
- OAuth credentials are not implemented yet; no token is stored by this MVP.
- Never commit `.env` or the `.hey-broski/` directory.

Approval currently creates a persisted local reminder and records its result before reporting completion. Live email/calendar/n8n adapters must keep the same policy boundary and mark an action complete only after a confirmed tool result.

## Configuration

Important variables are documented in `.env.example`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HEYBROSKI_DEMO_MODE` | `true` | Enables bundled evaluation data |
| `HEYBROSKI_DATA_DIR` | `./.hey-broski` | Local SQLite/data directory |
| `OLLAMA_BASE_URL` | Docker service URL | Local inference endpoint |
| `HEYBROSKI_CHAT_MODEL` | `qwen3:4b` | Local chat model |
| `OLLAMA_TIMEOUT_SECONDS` | `45` | Model request timeout |

## API surface

- `GET /api/health`
- `POST/GET /api/chat/sessions`
- `POST /api/chat/sessions/{id}/messages`
- `GET /api/actions`
- `POST /api/actions/{id}/decision`
- `GET /api/reminders`
- `POST/GET /api/documents`
- `GET /api/audit`

Interactive request and response schemas are at `/docs`.

## Roadmap

1. Encrypted OAuth token storage and Gmail/Outlook read sync
2. Google and Microsoft calendar conflict detection
3. Embeddings and LanceDB for semantic document retrieval
4. Approved n8n workflow execution with idempotency keys
5. Background synchronization and connector health reporting
6. Playwright coverage for the full browser flow

See `plan.md` for the product vision and complete scope.

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

## Run locally on Windows (no Docker)

Install [Python 3.11+](https://www.python.org/downloads/), [Node.js 20.9+](https://nodejs.org/en/download), and [Ollama for Windows](https://ollama.com/download/windows). Open PowerShell in the repository root. Ollama must be running in the background; its Windows app normally starts the server. The first model download and first response can take longer than later responses.

1. Create your private environment file once. If `.env` already exists, keep it and check the values below instead of overwriting it.

   ```powershell
   Copy-Item .env.example .env
   ```

   For this native setup, `.env` should contain `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `API_BASE_URL=http://127.0.0.1:8000`, `HEYBROSKI_USE_OLLAMA=true`, and `HEYBROSKI_CHAT_MODEL=qwen3:4b`. Both the Python API and the web development command read the root `.env` automatically; no `$env:...` commands or activation are needed. Restart both servers after editing `.env`.

2. Download the model once and confirm Ollama is responding:

   ```powershell
   ollama pull qwen3:4b
   ollama list
   ```

3. Install the API and web dependencies once:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
   npm --prefix apps/web ci
   ```

4. Start the API in one PowerShell window, from the repository root:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn apps.api.app.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. Start the web app in a second PowerShell window, also from the repository root:

   ```powershell
   npm --prefix apps/web run dev
   ```

Open http://localhost:3000. Check http://localhost:8000/api/health: `services.ollama` should be `available`. On later runs, keep Ollama running and repeat only steps 4 and 5. Stop each foreground server with Ctrl+C. n8n is not needed for the current demo chat, upload, and action inbox; the Compose setup below includes it.

If `py -3.11` is unavailable but `python --version` reports 3.11 or newer, use `python -m venv .venv` instead. If port 11434 does not answer, start the Ollama Windows app before starting the API. Chat requires the model; it does not fall back to canned replies.

## Run in GitHub Codespaces (Docker Compose)

Use a Codespace with Docker Compose available and enough memory for the CPU model (at least 8 GB available is recommended). In its Bash terminal, from the repository root:

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f ollama-model
```

If you already have `.env`, do not copy over it; use `docker compose up -d --build` directly. The `ollama-model` service downloads `qwen3:4b` on the first start. Exit the log view with Ctrl+C; the containers keep running. Forward port 3000 in Codespaces and open the forwarded web URL. Port 8000 serves the API and port 5678 serves n8n.

Compose overrides the native URLs in `.env` inside its containers: web reaches the API through `host.docker.internal:8000`, and the API reaches Ollama through `host.docker.internal:11434`. Do not change `.env` back and forth between local Windows and Codespaces. This host-gateway routing also handles Codespaces environments where sibling-container bridge traffic is filtered.

Check readiness and verify an actual model-generated answer:

```bash
docker compose ps
curl -s http://localhost:8000/api/health
bash scripts/verify-local-chat.sh
```

If chat fails, inspect `docker compose logs --tail=100 ollama-model ollama api web` and `docker compose exec ollama ollama list`. After changing an existing `.env`, recreate the services with `docker compose up -d --build --force-recreate`. Stop the stack with `docker compose down`; named volumes retain your data and model downloads.

For either setup, ask `What needs my attention this week?` after the model is ready.

## Development checks

From PowerShell at the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests
npm --prefix apps/web run build
```

## Architecture

```text
Browser / Next.js
        │ relative /api proxy
        ▼
FastAPI routes ── Assistant service ── Ollama (required for chat)
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
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Native Ollama endpoint; Compose overrides it in the API container |
| `HEYBROSKI_CHAT_MODEL` | `qwen3:4b` | Local chat model |
| `OLLAMA_TIMEOUT_SECONDS` | `45` | Model request timeout |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Native web proxy target; Compose overrides it in the web container |

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

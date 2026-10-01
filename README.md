# Hey Broski

Hey Broski is a local-first personal admin copilot. First-time setup collects a local profile, connects at least one read-only Gmail or Outlook mailbox, and lets the owner choose an import window and sync interval before entering the workspace. Chat answers still require a local Ollama model.

## What works today

- Grounded chat over imported mail and uploaded documents; legacy demo fixtures remain for API tests but are not used once an account is connected
- Gmail and Outlook OAuth connection, mailbox verification, background import, and configurable polling sync
- Local profile with name, date of birth, country code and phone number, gender, and machine-detected time zone; age is calculated from the birth date
- Answers generated only by a local Ollama `qwen3:4b-instruct` model; inference errors are reported rather than replaced with canned text
- Persistent SQLite conversations, action cards, documents, and internal safety events
- Approval and dismissal workflow—no proposal executes silently
- Local PDF, TXT, Markdown, and CSV upload and keyword retrieval
- Responsive action inbox, document vault, source citations, and conversation history
- Production-style multi-stage frontend image and non-root API image

The current UI is a local React chat shell rather than hosted ChatKit. The current ChatKit session API expects an OpenAI workflow and returns an OpenAI client secret, which conflicts with this project's zero-paid-API and local-inference rules. The backend contracts are kept separate so a future fully self-hosted ChatKit adapter can replace the shell without changing the domain services.

Calendar sync, semantic vector search, and live n8n workflow execution remain planned. Imported mail can produce reminder proposals when it contains an explicit due or renewal date in day-month-year format. More general commitment extraction remains planned.

## First-time setup and connected mail

Run the API and web app on your own computer using the instructions below, then open `http://localhost:3000`. Setup runs in three steps: profile, mail connection, and import/sync choices. The time zone is read from the browser's machine settings; it is not requested as a preference. Existing profiles are asked for a birth date and separate country code because those cannot be derived reliably from the old age and phone fields. A successfully verified Gmail or Outlook account and a completed first import are required to enter the workspace. Setup shows import progress and retry; the Accounts view shows later syncs, errors, manual sync, disconnect, and a way to change settings.

The Gmail card walks the owner through every Google Cloud Console step, from creating a project to downloading a **Desktop app** OAuth client JSON. Import that JSON in the card. Hey Broski then opens Google sign-in and verifies `gmail.readonly` with a profile and one-message list request. The JSON is not a mailbox password or an access token. Google says [standard Gmail API usage has no additional cost](https://developers.google.com/workspace/gmail/api/reference/quota); this personal setup does not ask for billing or a quota increase. An external Google app left in Testing can issue refresh tokens that expire after seven days for Gmail access; reconnect when prompted, or review Google's publishing rules for personal use.

For Outlook, setup accepts a Microsoft Entra **Application (client) ID** for a public/mobile-desktop registration. Register `http://localhost:8000/api/accounts/outlook/callback` as the redirect URI and request delegated `Mail.Read`, `User.Read`, and `offline_access`. Alternatively, the app owner can set `MICROSOFT_CLIENT_ID` in `.env` to offer direct sign-in. Work accounts can require administrator approval. The Microsoft card links to registration instructions.

Provider access tokens and imported OAuth client details are encrypted locally outside SQLite. On Windows, the encryption key is stored in the OS credential store when available; otherwise `vault.key` in `.hey-broski/` is used. For a backup, keep `credentials.enc.json`, `vault.key` when present, and the SQLite database together; an OS-stored key may require reconnecting accounts after moving to a different machine. Do not commit any of these files. Disconnect removes that account's tokens, imported mail, and generated pending actions. Existing conversation answers and saved source excerpts remain until their conversations are deleted.

OAuth redirects currently target `localhost:8000` and require the browser and API to run on the same computer. Codespaces can still run the demo, but real account connection needs a separately configured public callback before it can work from a remote browser.

## Run locally on Windows (no Docker)

Install [Python 3.11+](https://www.python.org/downloads/), [Node.js 20.9+](https://nodejs.org/en/download), and [Ollama for Windows](https://ollama.com/download/windows). Open PowerShell in the repository root. Ollama must be running in the background; its Windows app normally starts the server. The first model download and first response can take longer than later responses.

1. Create your private environment file once. If `.env` already exists, keep it and check the values below instead of overwriting it.

   ```powershell
   Copy-Item .env.example .env
   ```

   For this native setup, `.env` should contain `OLLAMA_BASE_URL=http://127.0.0.1:11434`, `API_BASE_URL=http://127.0.0.1:8000`, `HEYBROSKI_USE_OLLAMA=true`, and `HEYBROSKI_CHAT_MODEL=qwen3:4b-instruct`. If upgrading an existing `.env`, change any old `qwen3:4b` setting to `qwen3:4b-instruct` and set `OLLAMA_NUM_PREDICT=768`. Both the Python API and the web development command read the root `.env` automatically; no `$env:...` commands or activation are needed. Restart both servers after editing `.env`.

2. Download the model once and confirm Ollama is responding:

   ```powershell
   ollama pull qwen3:4b-instruct
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

Open http://localhost:3000. Check http://localhost:8000/api/health: `services.ollama` should be `available`. On later runs, keep Ollama running and repeat only steps 4 and 5. Stop each foreground server with Ctrl+C. n8n is not needed for onboarding or mail import; the Compose setup below includes it.

Chat displays a short source-checking status while the local model prepares an answer; it never displays the model's private reasoning. Completed turns are stored in SQLite with a conversation ID, a shared turn ID, separate user/assistant message IDs, source metadata, timestamps, and response time. Use **Conversation history** or the recent-chat list to reopen them; **New conversation** no longer discards past chats.

Conversation history and document cards each have a Delete control with confirmation. Deleting a conversation removes its messages and related actions/reminders. Deleting a document removes its vault record and search chunks, so new chats cannot retrieve it; existing conversations, answers, and saved source excerpts remain unchanged. Follow-ups in an existing conversation can still refer to information already written in its chat history. These deletions cannot be undone.

Uploaded files are text-extracted and split into overlapping excerpts. Chat searches those excerpts and sends the most relevant ones to Ollama as cited sources. Existing uploads are indexed automatically when the API starts. Ask about a file by name for the clearest results, for example, `When does policy.txt renew?`. This MVP uses keyword retrieval, not semantic search; very long documents are represented by selected excerpts rather than the full text.

If `py -3.11` is unavailable but `python --version` reports 3.11 or newer, use `python -m venv .venv` instead. If port 11434 does not answer, start the Ollama Windows app before starting the API. Chat requires the model; it does not fall back to canned replies.

## Run in GitHub Codespaces (Docker Compose)

Use a Codespace with Docker Compose available and enough memory for the CPU model (at least 8 GB available is recommended). In its Bash terminal, from the repository root:

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f ollama-model
```

If you already have `.env`, do not copy over it; update `HEYBROSKI_CHAT_MODEL=qwen3:4b-instruct` and `OLLAMA_NUM_PREDICT=768`, then use `docker compose up -d --build`. The `ollama-model` service downloads the configured model on its first start. Exit the log view with Ctrl+C; the containers keep running. Forward port 3000 in Codespaces and open the forwarded web URL. Port 8000 serves the API and port 5678 serves n8n. First-time mailbox connection currently requires a browser on the same computer as the API, so a fresh Codespace cannot complete onboarding without a supported remote OAuth callback implementation.

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
- Decisions and uploads retain internal safety records; the UI shows conversation history instead of an audit-log page.
- OAuth credentials are encrypted in a device-local vault; read-only scopes are requested for both mail providers.
- Never commit `.env` or the `.hey-broski/` directory.

Approval currently creates a persisted local reminder and records its result before reporting completion. Live email/calendar/n8n adapters must keep the same policy boundary and mark an action complete only after a confirmed tool result.

## Configuration

Important variables are documented in `.env.example`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HEYBROSKI_DEMO_MODE` | `true` | Enables bundled evaluation data |
| `HEYBROSKI_DATA_DIR` | `./.hey-broski` | Local SQLite/data directory |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Native Ollama endpoint; Compose overrides it in the API container |
| `HEYBROSKI_CHAT_MODEL` | `qwen3:4b-instruct` | Local direct-answer chat model |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Model idle read timeout for streaming chat |
| `OLLAMA_NUM_PREDICT` | `768` | Maximum generated tokens per answer |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Native web proxy target; Compose overrides it in the web container |

## API surface

- `GET /api/onboarding`, `PUT /api/profile`
- `POST /api/accounts/gmail/client`, `POST /api/accounts/outlook/client`
- `POST /api/accounts/{gmail|outlook}/start`, `GET /api/accounts/{gmail|outlook}/callback`
- `GET /api/accounts`, `DELETE /api/accounts/{id}`
- `PUT /api/accounts/{id}/sync-preferences`, `GET/POST /api/accounts/{id}/sync`
- `GET /api/health`
- `POST/GET /api/chat/sessions`
- `POST /api/chat/sessions/{id}/messages`
- `GET /api/chat/sessions/{id}/messages` (saved conversation)
- `DELETE /api/chat/sessions/{id}` (permanently delete a conversation)
- `POST /api/chat/sessions/{id}/messages/stream` (NDJSON status, content, completion events)
- `GET /api/actions`
- `POST /api/actions/{id}/decision`
- `GET /api/reminders`
- `POST/GET /api/documents`
- `DELETE /api/documents/{id}` (permanently delete a document and its search index)
- `GET /api/audit`

Interactive request and response schemas are at `/docs`.

## Roadmap

1. Live Gmail and Outlook account smoke tests with real owner credentials
2. More complete mail fact extraction, calendar conflict detection, and reply tracking
3. Embeddings and LanceDB for semantic document retrieval
4. Approved n8n workflow execution with idempotency keys
5. Incremental provider cursors and richer connector health reporting
6. Playwright coverage for the full browser flow

See `plan.md` for the product vision and complete scope.

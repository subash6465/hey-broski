# Hey Broski - Build Plan

Last updated: 2026-08-13
Owner intent: Build a finished, production-style, zero-paid-API personal admin AI product with a polished chat interface, local LLMs, MCP tools, n8n automations, multi-account email/calendar/document connectivity, action cards, and human approval before real-world actions.

Product name: **Hey Broski**. The repo, UI, docs, package names, Docker services, and user-facing copy must use this name. Do not use the previous working name except in migration notes if absolutely required.

---

## 0. Instructions for the coding agent

This file is the source of truth for building Hey Broski. Follow it exactly unless a later `plan.md` update explicitly changes the scope.

Non-negotiable rules:

1. Do not use paid LLM APIs.
2. Do not require OpenAI, Anthropic, Gemini, Mistral API keys, or any paid cloud inference service.
3. Use local inference through Ollama by default.
4. Use ChatKit for the frontend chat interface in self-hosted mode. Do not route messages to OpenAI-hosted inference.
5. Keep data local-first by default.
6. Store OAuth tokens securely through OS keychain where possible. Do not store raw access tokens in plaintext SQLite.
7. The AI must never send email, delete email, move files, share documents, create external events, or trigger external workflows without explicit user approval.
8. Every final answer involving user data must include source references from emails, documents, calendar events, or action cards.
9. Build demo mode first so the product can be evaluated without real Gmail/Outlook accounts.
10. The MVP must be usable from `docker compose up`.
11. Favor a working product over over-engineering. Build stable foundations, then expand.

Primary MVP product:

> Hey Broski: Daily Action Inbox - a local-first personal admin copilot that reads connected emails, calendars, and documents; detects commitments, deadlines, renewals, and follow-ups; answers questions through chat; creates action cards; and triggers approved automations.

---

## 1. Product vision

Hey Broski is a personal admin operating system. Users connect their personal and work accounts, documents, local folders, and automations. The product continuously turns hidden information into useful action cards.

Example user question:

```text
What needs my attention this week?
```

Expected product answer:

```text
You have 6 items needing attention:

1. Gmail / Personal: Credit card bill due on 2026-08-18.
2. Outlook / Work: Manager asked for updated report and no reply was found.
3. Documents: Headphones warranty expires in 9 days.
4. Calendar / Work: Two meetings overlap tomorrow.
5. Gmail / Personal: Canva trial renewal detected.
6. Documents: Insurance policy renewal window opens next week.

Suggested actions:
- Create reminders for due dates.
- Draft a reply to the work email.
- Add the warranty expiry to the tracker.

Approval required before any action is executed.
```

The key product differentiation is that Hey Broski is not only a chatbot. It is a chat-driven action inbox with grounded sources, safe tool calls, workflow automation, and local privacy.

---

## 2. Target users

Primary users:

1. Professionals managing personal plus work inboxes.
2. Freelancers and consultants who forget follow-ups and invoices.
3. Job seekers tracking recruiter emails, interview prep, resumes, and deadlines.
4. Busy individuals managing bills, renewals, warranties, documents, and calendar commitments.
5. Small-business owners who want personal admin automation without enterprise tools.

The MVP should feel valuable to a single user on their own laptop.

---

## 3. Core use cases

### 3.1 Daily attention summary

User asks:

```text
What needs my attention today?
```

System finds:

- Important unread emails.
- Unanswered emails where the user likely owes a reply.
- People waiting on the user.
- Upcoming bills, due dates, renewals, expiries, and warranties.
- Calendar conflicts.
- Upcoming meetings that need preparation.
- Document-based actions extracted from PDFs and images.

### 3.2 Follow-up tracking

User asks:

```text
Who is waiting on me?
```

System finds commitments in Gmail, Outlook, documents, and calendar notes.

### 3.3 Renewal and deadline detection

User asks:

```text
Show upcoming renewals and deadlines.
```

System detects renewals from emails, invoices, receipts, policy PDFs, subscription emails, and local documents.

### 3.4 Document vault Q&A

User asks:

```text
Find my warranty documents and tell me which ones are expiring soon.
```

System searches indexed local documents and provides source-grounded answers.

### 3.5 Natural-language automation

User asks:

```text
Whenever you detect a trial renewal, remind me 3 days before it renews.
```

System creates an automation rule, optionally backed by n8n.

### 3.6 Email drafting

User asks:

```text
Draft a reply to the work email asking for the project update.
```

System drafts the email but does not send it until the user approves.

---

## 4. MVP scope

Build the following in the first complete version:

1. Chat UI using ChatKit.
2. Local FastAPI backend.
3. Local LLM through Ollama.
4. Qwen3 model as default.
5. SQLite metadata database.
6. LanceDB local vector index.
7. Demo data mode for email, calendar, and documents.
8. Local document upload and folder indexing.
9. Basic Gmail developer-mode connector.
10. Basic Outlook/Microsoft Graph developer-mode connector.
11. Action card generation.
12. Human approval system.
13. Audit log for every tool call and approval.
14. n8n workflow trigger integration.
15. Basic MCP server/tool layer.
16. Docker Compose setup.
17. README with setup instructions.
18. Seed demo dataset.
19. E2E demo flow.

Out of scope for MVP:

1. Public SaaS multi-tenant launch.
2. Automatic email sending without approval.
3. Mobile app.
4. Browser extension.
5. WhatsApp or SMS integration.
6. Payment integration.
7. Enterprise admin console.
8. Full Google OAuth public verification.
9. Full Outlook tenant-admin support.
10. Full background cloud infrastructure.
11. Automatic subscription cancellation.
12. Unrestricted filesystem access.

---

## 5. Architecture overview

High-level architecture:

```text
User
  -> Next.js frontend with ChatKit
  -> FastAPI backend
  -> Chat runtime adapter
  -> Agent orchestrator
  -> Local LLM gateway using Ollama
  -> MCP tool router
  -> Domain services
       -> Email service
       -> Calendar service
       -> Document service
       -> Action card service
       -> Automation service
       -> Memory service
       -> Audit service
  -> Storage
       -> SQLite metadata DB
       -> LanceDB vector DB
       -> Local file cache
       -> OS keychain for secrets
  -> External/local integrations
       -> Gmail API
       -> Microsoft Graph
       -> Local filesystem
       -> n8n self-hosted workflows
```

Runtime flow:

```text
1. User sends message in ChatKit UI.
2. Frontend calls backend chat endpoint.
3. Backend creates a chat turn record.
4. Orchestrator classifies intent.
5. Orchestrator gathers relevant data using tools.
6. Safety policy checks every requested tool call.
7. Read-only tools execute immediately.
8. Risky tools create approval requests.
9. Local LLM generates grounded response using retrieved context.
10. Backend returns response, sources, and action cards.
11. User approves, edits, or rejects proposed actions.
12. Approved actions execute through MCP tools or n8n.
13. Tool result and audit log are stored.
```

---

## 6. Recommended technology stack

### 6.1 Frontend

Use:

- Next.js with App Router.
- React.
- TypeScript.
- Tailwind CSS.
- ChatKit React package for chat interface.
- shadcn/ui for polished components.
- lucide-react for icons.
- TanStack Query for server state.
- Zustand for lightweight client state.
- Zod for schema validation.
- React Hook Form for forms.
- Playwright for E2E tests.

Frontend package list:

```json
{
  "dependencies": {
    "next": "latest",
    "react": "latest",
    "react-dom": "latest",
    "@openai/chatkit-react": "latest",
    "@tanstack/react-query": "latest",
    "zustand": "latest",
    "zod": "latest",
    "react-hook-form": "latest",
    "lucide-react": "latest",
    "tailwindcss": "latest",
    "class-variance-authority": "latest",
    "clsx": "latest",
    "tailwind-merge": "latest"
  },
  "devDependencies": {
    "typescript": "latest",
    "eslint": "latest",
    "prettier": "latest",
    "playwright": "latest",
    "vitest": "latest"
  }
}
```

ChatKit requirement:

- Use ChatKit in self-hosted mode.
- Do not connect the UI to OpenAI-hosted model inference.
- Build a backend adapter compatible with ChatKit session/message expectations.
- If a ChatKit SDK limitation blocks local inference, keep ChatKit for UI shell and route all model calls through the Hey Broski backend.

### 6.2 Backend

Use:

- Python 3.11 or newer.
- FastAPI.
- Uvicorn.
- Pydantic v2.
- pydantic-settings.
- SQLAlchemy 2.0 or SQLModel.
- Alembic for migrations.
- SQLite with aiosqlite.
- httpx for external API calls.
- APScheduler for local scheduled jobs.
- python-multipart for file upload.
- keyring for OS token storage.
- cryptography for fallback encrypted local token storage.
- structlog or loguru for structured logs.
- pytest for tests.

Backend package list:

```text
fastapi
uvicorn[standard]
pydantic
pydantic-settings
sqlalchemy
sqlmodel
alembic
aiosqlite
httpx
python-multipart
keyring
cryptography
apscheduler
structlog
pytest
pytest-asyncio
respx
freezegun
```

### 6.3 AI and agent packages

Use:

```text
openai
ollama
langchain-core
langgraph
mcp
lancedb
sentence-transformers
numpy
pandas
pydantic
```

Implementation notes:

- Use the `openai` Python client against Ollama's OpenAI-compatible local endpoint when convenient.
- Use direct `httpx` calls to Ollama if more control is needed.
- Start orchestration with custom Python services.
- Introduce LangGraph only after basic flows work.
- Do not make LangGraph a blocker for MVP.

### 6.4 Document processing packages

Use:

```text
pymupdf
pypdf
python-docx
pandas
openpyxl
pillow
pytesseract
watchfiles
```

Optional later:

```text
paddleocr
rapidocr-onnxruntime
unstructured
markitdown
```

Use OCR only when extracted text is missing or too short.

### 6.5 Email and calendar packages

Gmail:

```text
google-api-python-client
google-auth
google-auth-oauthlib
google-auth-httplib2
```

Outlook and Microsoft 365:

```text
msal
httpx
```

Use direct Microsoft Graph REST calls through `httpx` rather than a heavy SDK for the first version.

### 6.6 Storage

Use:

- SQLite for relational metadata.
- LanceDB embedded local path for vectors.
- Local file cache for extracted text and attachments.
- OS keychain for tokens.

Default local data directory:

```text
~/.hey-broski/
  heybroski.db
  lancedb/
  cache/
    documents/
    email_attachments/
    extracted_text/
  logs/
  n8n/
  exports/
```

### 6.7 Automation

Use:

- n8n self-hosted through Docker Compose.
- n8n webhooks for simple workflow triggering.
- n8n MCP Server Trigger support for later workflow-as-tool patterns.

Core rule:

- Hey Broski owns user intent, safety policy, and audit logs.
- n8n executes approved repeatable workflows.
- Do not hide critical business logic only inside n8n.

### 6.8 Local app shell

MVP is a local web app.

Later add Tauri desktop shell for:

- Secure local folder selection.
- Better OS keychain behavior.
- Tray app.
- Background sync.
- Local notifications.

Do not build Tauri before the web MVP works.

---

## 7. Local LLM strategy

### 7.1 Default model

Default local LLM:

```bash
ollama pull qwen3:8b
```

Use Qwen3 8B as the default because it balances quality, local usability, tool-following ability, open-weight availability, and laptop feasibility.

### 7.2 Fallback models

For lower-end machines:

```bash
ollama pull qwen3:4b
ollama pull qwen3:1.7b
```

For stronger machines:

```bash
ollama pull qwen3:14b
ollama pull qwen3:30b
```

Optional high-quality model later:

```bash
ollama pull mistral-small
```

Do not hardcode exact model names except in default config. Let users change them in Settings.

### 7.3 Embedding model

Default embedding model:

```bash
ollama pull nomic-embed-text
```

Optional embedding models:

```bash
ollama pull mxbai-embed-large
```

If Qwen3 embedding models are easily available in the local runtime, support them as an advanced option.

### 7.4 LLM gateway

Create a backend module:

```text
apps/api/app/ai/llm_gateway.py
```

Responsibilities:

- Read model configuration from settings.
- Connect to Ollama.
- Support chat completions.
- Support embeddings.
- Support structured JSON output using schema validation and retries.
- Track latency, model name, tokens if available, and error information.

Interface:

```python
class LLMGateway:
    async def chat(self, messages: list[dict], *, temperature: float = 0.2) -> LLMResponse: ...
    async def structured_chat(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

### 7.5 Model behavior requirements

The model must:

1. Prefer concise, actionable answers.
2. Never claim an action was completed unless a tool result confirms it.
3. Distinguish between found facts and inferred tasks.
4. Include source IDs in intermediate structured outputs.
5. Ask for approval before external actions.
6. Avoid exposing raw OAuth tokens or secrets.
7. Use account labels when data comes from multiple accounts.

---

## 8. Repository structure

Create a monorepo:

```text
hey-broski/
  README.md
  plan.md
  docker-compose.yml
  .env.example
  .gitignore
  package.json
  pnpm-workspace.yaml

  apps/
    web/
      package.json
      next.config.ts
      tsconfig.json
      src/
        app/
          page.tsx
          layout.tsx
          onboarding/
            page.tsx
          dashboard/
            page.tsx
          vault/
            page.tsx
          accounts/
            page.tsx
          automations/
            page.tsx
          audit/
            page.tsx
          settings/
            page.tsx
        components/
          chat/
            HeyBroskiChat.tsx
            ChatMessage.tsx
            SourceCitation.tsx
          action-cards/
            ActionCard.tsx
            ActionCardList.tsx
            ApprovalModal.tsx
          accounts/
            AccountBadge.tsx
            AccountConnectionCard.tsx
          dashboard/
            DailyBriefPanel.tsx
            AttentionSummary.tsx
          documents/
            DocumentUpload.tsx
            DocumentTable.tsx
          layout/
            AppShell.tsx
            Sidebar.tsx
        lib/
          api.ts
          schemas.ts
          query-client.ts
          utils.ts
        stores/
          app-store.ts
        styles/
          globals.css

    api/
      pyproject.toml
      alembic.ini
      app/
        main.py
        config.py
        db/
          session.py
          models.py
          migrations/
        ai/
          llm_gateway.py
          prompts.py
          schemas.py
        agents/
          orchestrator.py
          inbox_agent.py
          document_agent.py
          calendar_agent.py
          automation_agent.py
          safety_agent.py
          memory_agent.py
        services/
          chat_service.py
          action_card_service.py
          approval_service.py
          audit_service.py
          document_service.py
          email_service.py
          calendar_service.py
          automation_service.py
          sync_service.py
          search_service.py
          token_service.py
        connectors/
          gmail/
            oauth.py
            client.py
            sync.py
            mapper.py
          outlook/
            oauth.py
            client.py
            sync.py
            mapper.py
          local_files/
            watcher.py
            extractor.py
            mapper.py
          google_drive/
            client.py
          onedrive/
            client.py
        mcp_tools/
          server.py
          registry.py
          email_tools.py
          calendar_tools.py
          document_tools.py
          action_tools.py
          automation_tools.py
        api_routes/
          chat.py
          actions.py
          approvals.py
          accounts.py
          documents.py
          search.py
          automations.py
          audit.py
          settings.py
          health.py
        jobs/
          scheduler.py
          sync_jobs.py
          action_detection_jobs.py
        tests/
          unit/
          integration/

  packages/
    shared/
      package.json
      src/
        schemas.ts
        types.ts

  mcp-servers/
    heybroski/
      README.md
      server.py

  n8n/
    workflows/
      daily-brief.json
      renewal-watch.json
      followup-watch.json
      invoice-tracker.json
      meeting-prep.json
    README.md

  docs/
    architecture.md
    oauth-setup.md
    demo-script.md
    security.md
    testing.md
```

---

## 9. Environment configuration

Create `.env.example`:

```bash
# App
HEYBROSKI_ENV=development
HEYBROSKI_DATA_DIR=~/.hey-broski
HEYBROSKI_API_BASE_URL=http://localhost:8000
HEYBROSKI_WEB_BASE_URL=http://localhost:3000

# Database
DATABASE_URL=sqlite+aiosqlite:///./heybroski.db
LANCEDB_PATH=./.hey-broski/lancedb

# LLM
OLLAMA_BASE_URL=http://localhost:11434
HEYBROSKI_CHAT_MODEL=qwen3:8b
HEYBROSKI_EMBEDDING_MODEL=nomic-embed-text
HEYBROSKI_LLM_TEMPERATURE=0.2

# Security
HEYBROSKI_TOKEN_STORAGE=keyring
HEYBROSKI_FALLBACK_TOKEN_ENCRYPTION_KEY=change-me-only-for-local-dev

# Gmail developer mode
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/accounts/gmail/callback

# Microsoft developer mode
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT=common
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/accounts/outlook/callback

# n8n
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=
HEYBROSKI_N8N_WEBHOOK_SECRET=local-dev-secret

# Feature flags
FEATURE_GMAIL_CONNECTOR=true
FEATURE_OUTLOOK_CONNECTOR=true
FEATURE_LOCAL_DOCUMENTS=true
FEATURE_N8N=true
FEATURE_MCP=true
FEATURE_TAURI=false
```

Do not commit real `.env`.

---

## 10. Docker Compose

Create `docker-compose.yml` with at least:

```yaml
services:
  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
    depends_on:
      - api

  api:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - heybroski_data:/data/heybroski
      - ./demo-data:/app/demo-data
    depends_on:
      - ollama
      - n8n

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=localhost
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - N8N_DIAGNOSTICS_ENABLED=false
      - N8N_PERSONALIZATION_ENABLED=false
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  heybroski_data:
  ollama_data:
  n8n_data:
```

Add setup script:

```bash
scripts/bootstrap.sh
```

It should:

1. Check Docker.
2. Start Ollama if needed.
3. Pull default models.
4. Run migrations.
5. Seed demo data.
6. Print local URLs.

---

## 11. Database schema

Use SQLite for relational storage. Use migrations through Alembic.

Follow this schema. Add indexes for all foreign keys, external IDs, timestamps, and status fields.

### table_name: users
Description: Stores local user profile records. The MVP is single-user, but this table keeps the architecture ready for multi-profile local usage later.
Columns:
id
 -Description: Unique internal user identifier.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: True
email
 -Description: Optional primary email for display and ownership metadata.
 -Usage: text nullable
 -Values: ["alex@example.com"]
 -Primary Key: False
display_name
 -Description: Human-readable user name.
 -Usage: text nullable
 -Values: ["Alex"]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: connected_accounts
Description: Stores connected external accounts such as Gmail personal, Outlook work, Google Calendar, Microsoft Calendar, Google Drive, and OneDrive. Raw tokens must not be stored here.
Columns:
id
 -Description: Unique internal connected account identifier.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
user_id
 -Description: Owner user ID.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: False
provider
 -Description: Account provider.
 -Usage: text enum
 -Values: ["gmail", "outlook", "google_calendar", "microsoft_calendar", "google_drive", "onedrive", "local_files"]
 -Primary Key: False
account_email
 -Description: Email address or account label shown in UI.
 -Usage: text
 -Values: ["personal@gmail.com", "name@company.com"]
 -Primary Key: False
account_type
 -Description: User-selected account category.
 -Usage: text enum
 -Values: ["personal", "work", "other"]
 -Primary Key: False
display_name
 -Description: Friendly display name.
 -Usage: text nullable
 -Values: ["Personal Gmail", "Work Outlook"]
 -Primary Key: False
scopes_granted
 -Description: JSON list of granted OAuth scopes or local permissions.
 -Usage: json text
 -Values: ["[\"Mail.Read\", \"Mail.ReadWrite\"]"]
 -Primary Key: False
token_ref
 -Description: Reference key used to retrieve token from OS keychain or encrypted fallback store.
 -Usage: text nullable
 -Values: ["keyring:heybroski:gmail:abc123"]
 -Primary Key: False
sync_status
 -Description: Current sync state.
 -Usage: text enum
 -Values: ["not_connected", "connected", "syncing", "error", "disabled"]
 -Primary Key: False
last_synced_at
 -Description: Last successful sync timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
sync_cursor
 -Description: Provider-specific incremental sync cursor such as Gmail historyId or Microsoft deltaLink.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: email_threads
Description: Stores normalized email thread metadata across Gmail, Outlook, and demo inboxes.
Columns:
id
 -Description: Unique internal thread ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
connected_account_id
 -Description: Source connected account.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
provider_thread_id
 -Description: Provider-specific thread or conversation ID.
 -Usage: text
 -Values: []
 -Primary Key: False
subject
 -Description: Thread subject.
 -Usage: text
 -Values: ["Project update request"]
 -Primary Key: False
participants_json
 -Description: JSON array of participants.
 -Usage: json text
 -Values: []
 -Primary Key: False
last_message_at
 -Description: Latest message timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
importance_score
 -Description: Computed importance score from 0 to 1.
 -Usage: float
 -Values: [0.84]
 -Primary Key: False
needs_user_attention
 -Description: Whether the thread likely needs user action.
 -Usage: boolean
 -Values: [true, false]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: emails
Description: Stores normalized email message metadata and extracted plain text. Use this table for search, summaries, and commitment detection.
Columns:
id
 -Description: Unique internal email ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
thread_id
 -Description: Internal email thread ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
connected_account_id
 -Description: Source connected account.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
provider_message_id
 -Description: Gmail message ID, Outlook message ID, or demo ID.
 -Usage: text
 -Values: []
 -Primary Key: False
from_email
 -Description: Sender email address.
 -Usage: text
 -Values: ["person@example.com"]
 -Primary Key: False
to_emails_json
 -Description: JSON list of recipient addresses.
 -Usage: json text
 -Values: []
 -Primary Key: False
cc_emails_json
 -Description: JSON list of cc addresses.
 -Usage: json text
 -Values: []
 -Primary Key: False
subject
 -Description: Email subject.
 -Usage: text
 -Values: []
 -Primary Key: False
body_text
 -Description: Cleaned plain text body used for extraction and retrieval.
 -Usage: text
 -Values: []
 -Primary Key: False
body_snippet
 -Description: Short preview for UI.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
sent_at
 -Description: Message sent timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
received_at
 -Description: Message received timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
is_read
 -Description: Read status when provider supports it.
 -Usage: boolean
 -Values: [true, false]
 -Primary Key: False
labels_json
 -Description: Provider labels or folder names.
 -Usage: json text
 -Values: ["[\"INBOX\"]"]
 -Primary Key: False
has_attachments
 -Description: Whether message has attachments.
 -Usage: boolean
 -Values: [true, false]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: calendar_events
Description: Stores normalized calendar events from Google Calendar, Outlook Calendar, demo data, or locally created reminders.
Columns:
id
 -Description: Unique internal event ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
connected_account_id
 -Description: Source calendar account.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
provider_event_id
 -Description: Provider-specific event ID.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
title
 -Description: Event title.
 -Usage: text
 -Values: ["Project review"]
 -Primary Key: False
description
 -Description: Event description or notes.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
start_at
 -Description: Event start timestamp.
 -Usage: datetime
 -Values: []
 -Primary Key: False
end_at
 -Description: Event end timestamp.
 -Usage: datetime
 -Values: []
 -Primary Key: False
timezone
 -Description: Event timezone.
 -Usage: text nullable
 -Values: ["Asia/Kolkata"]
 -Primary Key: False
attendees_json
 -Description: JSON list of attendees.
 -Usage: json text nullable
 -Values: []
 -Primary Key: False
source_type
 -Description: Origin type.
 -Usage: text enum
 -Values: ["google", "microsoft", "local", "demo"]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: documents
Description: Stores indexed document metadata from local uploads, watched folders, demo files, Google Drive, or OneDrive.
Columns:
id
 -Description: Unique internal document ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
source_type
 -Description: Document origin.
 -Usage: text enum
 -Values: ["upload", "local_folder", "google_drive", "onedrive", "email_attachment", "demo"]
 -Primary Key: False
connected_account_id
 -Description: Optional source account ID.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
source_uri
 -Description: Local path, provider file ID, or internal cache URI.
 -Usage: text
 -Values: []
 -Primary Key: False
file_name
 -Description: Display file name.
 -Usage: text
 -Values: ["invoice_august.pdf"]
 -Primary Key: False
mime_type
 -Description: MIME type.
 -Usage: text nullable
 -Values: ["application/pdf"]
 -Primary Key: False
file_hash
 -Description: Content hash to avoid duplicate indexing.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
document_type
 -Description: Classified document type.
 -Usage: text enum nullable
 -Values: ["invoice", "receipt", "warranty", "contract", "policy", "id", "resume", "bill", "unknown"]
 -Primary Key: False
extracted_text_path
 -Description: Local cache path for extracted text.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
summary
 -Description: Short generated summary.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
indexed_at
 -Description: Timestamp when indexing completed.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: document_chunks
Description: Stores chunk metadata for retrieval. Actual vectors live in LanceDB and refer back to these IDs.
Columns:
id
 -Description: Unique internal chunk ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
document_id
 -Description: Parent document ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
chunk_index
 -Description: Zero-based chunk order.
 -Usage: integer
 -Values: [0, 1, 2]
 -Primary Key: False
text
 -Description: Chunk text.
 -Usage: text
 -Values: []
 -Primary Key: False
page_number
 -Description: Optional PDF page number.
 -Usage: integer nullable
 -Values: [1]
 -Primary Key: False
start_char
 -Description: Start character offset in extracted text.
 -Usage: integer nullable
 -Values: []
 -Primary Key: False
end_char
 -Description: End character offset in extracted text.
 -Usage: integer nullable
 -Values: []
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: document_entities
Description: Stores structured facts extracted from documents, such as due dates, vendors, amounts, expiry dates, policy numbers, invoice numbers, and warranty dates.
Columns:
id
 -Description: Unique internal entity ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
document_id
 -Description: Source document ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
entity_type
 -Description: Type of extracted entity.
 -Usage: text enum
 -Values: ["due_date", "expiry_date", "renewal_date", "amount", "vendor", "policy_number", "invoice_number", "person", "organization", "action_required"]
 -Primary Key: False
entity_value
 -Description: Extracted normalized value.
 -Usage: text
 -Values: ["2026-08-18", "Canva"]
 -Primary Key: False
raw_text
 -Description: Supporting raw text span.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
confidence
 -Description: Extraction confidence from 0 to 1.
 -Usage: float
 -Values: [0.87]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: commitments
Description: Stores commitments, promises, requests, deadlines, and follow-ups extracted from emails, documents, and calendar events.
Columns:
id
 -Description: Unique internal commitment ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
source_type
 -Description: Source type.
 -Usage: text enum
 -Values: ["email", "document", "calendar", "chat", "manual", "demo"]
 -Primary Key: False
source_id
 -Description: Source record ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
connected_account_id
 -Description: Source account if applicable.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
title
 -Description: Short commitment title.
 -Usage: text
 -Values: ["Send updated project report"]
 -Primary Key: False
description
 -Description: Detailed explanation.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
owner_role
 -Description: Whether the user owes action or is waiting on someone else.
 -Usage: text enum
 -Values: ["user_owes", "other_owes", "unclear"]
 -Primary Key: False
counterparty_name
 -Description: Person or organization involved.
 -Usage: text nullable
 -Values: ["Priya"]
 -Primary Key: False
counterparty_email
 -Description: Counterparty email if available.
 -Usage: text nullable
 -Values: ["priya@example.com"]
 -Primary Key: False
due_at
 -Description: Due date/time if known.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
status
 -Description: Commitment status.
 -Usage: text enum
 -Values: ["open", "done", "dismissed", "snoozed", "uncertain"]
 -Primary Key: False
confidence
 -Description: Extraction confidence from 0 to 1.
 -Usage: float
 -Values: [0.78]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: action_cards
Description: Stores actionable UI cards produced by agents. These are the heart of the product.
Columns:
id
 -Description: Unique internal action card ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
user_id
 -Description: Owner user ID.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: False
card_type
 -Description: Type of action card.
 -Usage: text enum
 -Values: ["reply_needed", "follow_up", "deadline", "renewal", "calendar_conflict", "document_expiry", "automation_suggestion", "meeting_prep", "invoice", "custom"]
 -Primary Key: False
title
 -Description: Card title shown in UI.
 -Usage: text
 -Values: ["Credit card bill due soon"]
 -Primary Key: False
description
 -Description: Detailed card explanation.
 -Usage: text
 -Values: []
 -Primary Key: False
priority
 -Description: Priority classification.
 -Usage: text enum
 -Values: ["low", "medium", "high", "urgent"]
 -Primary Key: False
status
 -Description: Card lifecycle status.
 -Usage: text enum
 -Values: ["open", "approved", "completed", "dismissed", "snoozed", "failed"]
 -Primary Key: False
due_at
 -Description: Optional due timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
source_refs_json
 -Description: JSON array of source references.
 -Usage: json text
 -Values: []
 -Primary Key: False
suggested_actions_json
 -Description: JSON array of proposed actions.
 -Usage: json text
 -Values: []
 -Primary Key: False
confidence
 -Description: Confidence from 0 to 1.
 -Usage: float
 -Values: [0.89]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: approval_requests
Description: Stores pending and completed approval flows for any risky or external action.
Columns:
id
 -Description: Unique internal approval request ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
action_card_id
 -Description: Related action card if available.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
tool_name
 -Description: Tool that will execute after approval.
 -Usage: text
 -Values: ["email.create_draft", "calendar.create_reminder", "n8n.trigger_workflow"]
 -Primary Key: False
tool_args_json
 -Description: JSON arguments prepared for the tool.
 -Usage: json text
 -Values: []
 -Primary Key: False
risk_level
 -Description: Risk classification.
 -Usage: text enum
 -Values: ["low", "medium", "high"]
 -Primary Key: False
status
 -Description: Approval status.
 -Usage: text enum
 -Values: ["pending", "approved", "rejected", "expired", "executed", "failed"]
 -Primary Key: False
approved_at
 -Description: Approval timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
executed_at
 -Description: Execution timestamp.
 -Usage: datetime nullable
 -Values: []
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: automation_rules
Description: Stores user-defined automations created through chat or settings. Some rules execute internally, while others trigger n8n workflows.
Columns:
id
 -Description: Unique internal automation rule ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
user_id
 -Description: Owner user ID.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: False
name
 -Description: Automation name.
 -Usage: text
 -Values: ["Trial renewal reminder"]
 -Primary Key: False
description
 -Description: Natural-language explanation.
 -Usage: text
 -Values: []
 -Primary Key: False
trigger_type
 -Description: Trigger type.
 -Usage: text enum
 -Values: ["schedule", "new_email", "new_document", "new_action_card", "manual"]
 -Primary Key: False
conditions_json
 -Description: JSON conditions that must be satisfied.
 -Usage: json text
 -Values: []
 -Primary Key: False
actions_json
 -Description: JSON actions to run after approval/policy checks.
 -Usage: json text
 -Values: []
 -Primary Key: False
n8n_workflow_id
 -Description: Linked n8n workflow ID if applicable.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
is_enabled
 -Description: Whether the rule is active.
 -Usage: boolean
 -Values: [true, false]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: chat_threads
Description: Stores chat conversations.
Columns:
id
 -Description: Unique chat thread ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
user_id
 -Description: Owner user ID.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: False
title
 -Description: Generated or user-defined title.
 -Usage: text nullable
 -Values: ["Daily planning"]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False
updated_at
 -Description: Last update timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: chat_messages
Description: Stores chat messages and response metadata.
Columns:
id
 -Description: Unique chat message ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
thread_id
 -Description: Parent chat thread ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: False
role
 -Description: Message role.
 -Usage: text enum
 -Values: ["user", "assistant", "system", "tool"]
 -Primary Key: False
content
 -Description: Message content.
 -Usage: text
 -Values: []
 -Primary Key: False
sources_json
 -Description: JSON source references attached to assistant answer.
 -Usage: json text nullable
 -Values: []
 -Primary Key: False
model_name
 -Description: Model used for assistant output.
 -Usage: text nullable
 -Values: ["qwen3:8b"]
 -Primary Key: False
latency_ms
 -Description: LLM or full response latency.
 -Usage: integer nullable
 -Values: [1234]
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

### table_name: tool_call_audit_logs
Description: Immutable-style audit log for every tool call attempt, approval decision, external API request summary, and n8n trigger.
Columns:
id
 -Description: Unique audit log ID.
 -Usage: uuid/text
 -Values: []
 -Primary Key: True
user_id
 -Description: Owner user ID.
 -Usage: uuid/text
 -Values: ["local-user"]
 -Primary Key: False
chat_message_id
 -Description: Related chat message if applicable.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
tool_name
 -Description: Tool name.
 -Usage: text
 -Values: ["documents.search", "email.search", "calendar.create_reminder"]
 -Primary Key: False
tool_args_redacted_json
 -Description: Redacted JSON arguments.
 -Usage: json text
 -Values: []
 -Primary Key: False
tool_result_summary
 -Description: Short result summary, never raw secrets.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
risk_level
 -Description: Risk level assigned by policy.
 -Usage: text enum
 -Values: ["read_only", "low", "medium", "high"]
 -Primary Key: False
approval_request_id
 -Description: Approval request if one was required.
 -Usage: uuid/text nullable
 -Values: []
 -Primary Key: False
status
 -Description: Tool call status.
 -Usage: text enum
 -Values: ["allowed", "blocked", "pending_approval", "executed", "failed"]
 -Primary Key: False
error_message
 -Description: Error summary if failed.
 -Usage: text nullable
 -Values: []
 -Primary Key: False
created_at
 -Description: Record creation timestamp in UTC.
 -Usage: datetime
 -Values: []
 -Primary Key: False

---

## 12. LanceDB schema

Create LanceDB tables:

### documents_index

Fields:

```text
chunk_id: string
source_type: string
source_id: string
document_id: string nullable
email_id: string nullable
calendar_event_id: string nullable
connected_account_id: string nullable
account_label: string nullable
text: string
source_title: string
page_number: int nullable
created_at: timestamp
vector: float[]
```

Use cases:

- Semantic search over documents.
- Semantic search over important emails.
- RAG for chat answers.
- Source-grounded citations.

### people_memory_index

Fields:

```text
memory_id: string
person_name: string
person_email: string nullable
relationship_label: string nullable
text: string
last_interaction_at: timestamp nullable
vector: float[]
```

Use cases:

- Search people-related memory.
- Find who is waiting on the user.
- Summarize recent interactions.

---

## 13. Backend API routes

Use `/api` prefix.

### Health

```text
GET /api/health
```

Returns service status, database status, Ollama status, model status, and n8n status.

### Chat

```text
POST /api/chat/sessions
GET /api/chat/sessions
GET /api/chat/sessions/{thread_id}
POST /api/chat/sessions/{thread_id}/messages
```

Message request:

```json
{
  "message": "What needs my attention today?",
  "mode": "daily_admin",
  "account_filter": ["personal", "work"],
  "include_sources": true
}
```

Message response:

```json
{
  "message_id": "uuid",
  "content": "You have 5 items needing attention...",
  "sources": [
    {
      "source_type": "email",
      "source_id": "uuid",
      "title": "Credit card bill",
      "account_label": "Gmail / Personal"
    }
  ],
  "action_cards": [
    {
      "id": "uuid",
      "card_type": "renewal",
      "title": "Canva trial renewal likely soon",
      "priority": "medium"
    }
  ]
}
```

If ChatKit requires a specific session protocol, implement adapters that map ChatKit messages to this internal API contract.

### Action cards

```text
GET /api/actions
GET /api/actions/{id}
POST /api/actions/{id}/dismiss
POST /api/actions/{id}/snooze
POST /api/actions/{id}/approve
POST /api/actions/{id}/complete
```

### Approvals

```text
GET /api/approvals/pending
POST /api/approvals/{id}/approve
POST /api/approvals/{id}/reject
POST /api/approvals/{id}/edit
```

### Accounts

```text
GET /api/accounts
POST /api/accounts/demo/enable
POST /api/accounts/gmail/start
GET /api/accounts/gmail/callback
POST /api/accounts/outlook/start
GET /api/accounts/outlook/callback
POST /api/accounts/{id}/sync
DELETE /api/accounts/{id}
```

### Documents

```text
POST /api/documents/upload
GET /api/documents
GET /api/documents/{id}
POST /api/documents/{id}/reindex
DELETE /api/documents/{id}
POST /api/documents/local-folder
```

### Search

```text
POST /api/search
```

Request:

```json
{
  "query": "warranty expiring soon",
  "source_types": ["documents", "emails"],
  "account_filter": ["personal", "work"],
  "top_k": 10
}
```

### Automations

```text
GET /api/automations
POST /api/automations
POST /api/automations/{id}/enable
POST /api/automations/{id}/disable
POST /api/automations/{id}/run-now
DELETE /api/automations/{id}
```

### Audit

```text
GET /api/audit
GET /api/audit/{id}
```

### Settings

```text
GET /api/settings
PATCH /api/settings
```

---

## 14. Frontend pages and UX

### 14.1 Home / Chat page

Route:

```text
/
```

Main layout:

- Left sidebar with navigation.
- Center chat panel.
- Right action inbox panel.
- Account filter at top.
- Model/status indicator.

Required chat examples shown as prompt chips:

```text
What needs my attention today?
Who is waiting on me?
Find upcoming renewals.
Summarize important unread emails.
Find documents expiring this year.
Create a reminder for all due dates.
```

### 14.2 Dashboard

Route:

```text
/dashboard
```

Sections:

- Today's attention summary.
- Open action cards.
- Upcoming deadlines.
- Follow-ups.
- Renewals.
- Calendar conflicts.
- Sync status.

### 14.3 Action Inbox

Can be included in dashboard or own route later.

Action card UI must show:

- Type.
- Priority.
- Account label.
- Due date.
- Confidence.
- Source chips.
- Suggested actions.
- Approve/edit/dismiss/snooze buttons.

### 14.4 Vault

Route:

```text
/vault
```

Features:

- Upload document.
- View indexed docs.
- Filter by type.
- Search documents.
- View extracted entities.
- Re-index document.

### 14.5 Accounts

Route:

```text
/accounts
```

Features:

- Enable demo data.
- Connect Gmail.
- Connect Outlook.
- Add local folder.
- Show sync status.
- Manual sync button.
- Disconnect account.

For each account card show:

```text
Provider: Gmail
Label: Personal Gmail
Email: personal@gmail.com
Scopes: readonly, compose
Last sync: 2026-08-13 22:15
Status: connected
```

### 14.6 Automations

Route:

```text
/automations
```

Features:

- List rules.
- Create from natural language.
- Enable/disable.
- Run now.
- Show linked n8n workflow.
- Show last run result.

### 14.7 Audit

Route:

```text
/audit
```

Show:

- Tool calls.
- Approval decisions.
- Sync events.
- External API calls summary.
- Errors.

### 14.8 Settings

Route:

```text
/settings
```

Show:

- Local model configuration.
- Embedding model.
- Data directory.
- Privacy settings.
- Token storage status.
- Export/delete local data.

---

## 15. Account connection design

### 15.1 Multiple accounts

The app must support multiple accounts from the beginning.

Example:

```text
Gmail / Personal / personal@gmail.com
Outlook / Work / name@company.com
Google Calendar / Personal / personal@gmail.com
Outlook Calendar / Work / name@company.com
Local Folder / Documents / ~/Documents
```

Every indexed object must keep:

```text
connected_account_id
provider
account_type
account_email/account_label
```

UI must always display the source account for emails, calendar events, and cloud documents.

### 15.2 Gmail connector

Modes:

1. Demo mode.
2. Developer OAuth mode.
3. Production OAuth verification later.

Required MVP Gmail capabilities:

- OAuth sign-in.
- List messages from inbox and important folders.
- Fetch message bodies.
- Normalize plain text.
- Store messages and threads.
- Incremental sync using Gmail history ID when available.
- Create draft after approval.

Do not implement send email in MVP unless it is behind explicit approval and disabled by default.

Minimum scopes for MVP:

```text
gmail.readonly
gmail.compose
```

If label/archive support is added later:

```text
gmail.modify
```

Gmail sync approach:

1. First sync fetches recent messages from last 30 days or configurable limit.
2. Store latest history ID.
3. Next sync uses incremental history listing.
4. If history ID is invalid, perform a limited resync.
5. Never scan entire mailbox by default.

### 15.3 Outlook connector

Modes:

1. Demo mode.
2. Developer OAuth mode with Microsoft app registration.
3. Production/admin-consent support later.

Required MVP Outlook capabilities:

- OAuth sign-in using MSAL.
- Fetch messages from Inbox and Sent Items.
- Normalize threads and messages.
- Incremental sync using Microsoft Graph delta query where possible.
- Create draft after approval.

Recommended delegated permissions:

```text
Mail.Read
Mail.ReadWrite
offline_access
User.Read
```

For calendar:

```text
Calendars.Read
Calendars.ReadWrite
```

Work account reality:

- Some Microsoft 365 tenants require admin consent.
- Show a clear UI error if consent is blocked.
- Provide demo mode and file import fallback.

### 15.4 Calendar connectors

Google Calendar:

- Read upcoming events.
- Detect conflicts.
- Create reminder/event only after approval.

Microsoft Calendar:

- Read upcoming events through Graph.
- Detect conflicts.
- Create reminder/event only after approval.

MVP default:

- Read next 30 days.
- Store events locally.
- Sync manually and on schedule.

### 15.5 Documents

MVP document sources:

1. Upload through browser.
2. Local folder path configured by user.
3. Demo documents.

Phase 2:

1. Google Drive selected files using least-privilege file picker approach.
2. OneDrive selected files.

Document indexing flow:

```text
file selected/uploaded
  -> compute file hash
  -> skip if duplicate
  -> extract text
  -> OCR if needed
  -> classify document type
  -> extract structured entities
  -> chunk text
  -> create embeddings
  -> store metadata in SQLite
  -> store vectors in LanceDB
  -> create action cards if due dates/renewals/expiries found
```

Supported file types in MVP:

```text
.pdf
.txt
.md
.docx
.csv
.xlsx
.png
.jpg
.jpeg
```

---

## 16. MCP design

MCP is the tool protocol layer between agents and services.

Create a Hey Broski MCP server with tool definitions and safe execution policies.

### 16.1 MCP tool registry

Backend location:

```text
apps/api/app/mcp_tools/registry.py
```

Every tool must have:

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    risk_level: Literal["read_only", "low", "medium", "high"]
    requires_approval: bool
    handler: Callable
```

### 16.2 Read-only tools

Read-only tools can execute without approval but must be audited.

Tools:

```text
email.search_messages
email.get_thread
email.list_recent_important
calendar.list_events
documents.search
documents.get_summary
documents.get_entities
actions.list
commitments.search
memory.search_people
automations.list
```

### 16.3 Approval-required tools

These must create approval requests before execution:

```text
email.create_draft
email.send_message
email.archive_message
calendar.create_event
calendar.update_event
documents.move_file
documents.delete_file
automations.create_rule
n8n.trigger_workflow
n8n.create_workflow
```

For MVP, implement:

```text
email.create_draft
calendar.create_reminder
automations.create_rule
n8n.trigger_workflow
```

Disable email sending until a later feature flag is explicitly enabled.

### 16.4 Tool response format

All tools return:

```json
{
  "ok": true,
  "data": {},
  "sources": [],
  "audit_id": "uuid",
  "requires_followup": false,
  "message": "optional human-readable summary"
}
```

On failure:

```json
{
  "ok": false,
  "error_code": "PROVIDER_AUTH_EXPIRED",
  "message": "Gmail authorization expired. Reconnect account.",
  "audit_id": "uuid"
}
```

---

## 17. Agent design

Start with a deterministic orchestrator and add more agent behavior gradually.

### 17.1 Orchestrator Agent

Responsibilities:

- Classify user intent.
- Select tools.
- Coordinate sub-agents.
- Build grounded final response.
- Create action cards.
- Avoid direct risky execution.

Inputs:

```text
user message
chat history summary
account filters
open action cards
retrieved sources
tool results
```

Outputs:

```json
{
  "intent": "daily_attention_summary",
  "tool_plan": [],
  "final_response": "...",
  "source_refs": [],
  "action_cards": []
}
```

### 17.2 Inbox Agent

Responsibilities:

- Find important emails.
- Detect unanswered requests.
- Detect commitments.
- Detect people waiting on user.
- Draft replies.

Signals:

- Direct question asked of the user.
- Phrases like "please send", "can you share", "waiting for", "by Friday".
- Thread ended with someone else and no user reply afterward.
- Important sender or recent urgency.

### 17.3 Document Agent

Responsibilities:

- Classify document types.
- Extract due dates, expiry dates, vendors, amounts, policy numbers, invoice numbers.
- Create document-based action cards.
- Answer document questions with page/source references.

### 17.4 Calendar Agent

Responsibilities:

- Detect meeting conflicts.
- Find upcoming meetings.
- Prepare meeting briefs from related docs/emails.
- Create reminders after approval.

### 17.5 Automation Agent

Responsibilities:

- Convert natural-language automation requests into structured automation rules.
- Decide whether the rule can be internal or should use n8n.
- Create approval request before enabling workflow.

Example input:

```text
Whenever you detect a trial renewal, remind me 3 days before it renews.
```

Expected output:

```json
{
  "name": "Trial renewal reminder",
  "trigger_type": "new_action_card",
  "conditions": {
    "card_type": "renewal",
    "due_at_exists": true
  },
  "actions": [
    {
      "type": "create_reminder",
      "offset_days": -3
    }
  ],
  "requires_approval": true
}
```

### 17.6 Safety Agent

Responsibilities:

- Classify tool risk.
- Block unsafe or overly broad actions.
- Redact secrets in logs.
- Require approval for external effects.
- Explain risk in approval cards.

Policy examples:

```text
Read local indexed metadata: allowed, audited.
Search email: allowed, audited.
Create draft: approval required.
Send email: high risk, disabled by default.
Delete file: blocked in MVP.
Move file: blocked in MVP.
Trigger n8n workflow: approval required.
```

### 17.7 Memory Agent

Responsibilities:

- Maintain local person and commitment memory.
- Store recurring patterns only when useful.
- Avoid storing sensitive details unnecessarily.
- Link people to emails, documents, and commitments.

---

## 18. Prompt and structured-output requirements

Use structured JSON for extraction and agent planning.

### 18.1 Commitment extraction schema

```python
class CommitmentExtraction(BaseModel):
    commitments: list[CommitmentItem]

class CommitmentItem(BaseModel):
    title: str
    description: str | None
    owner_role: Literal["user_owes", "other_owes", "unclear"]
    counterparty_name: str | None
    counterparty_email: str | None
    due_at: str | None
    confidence: float
    evidence_quote: str
```

### 18.2 Document entity extraction schema

```python
class DocumentEntityExtraction(BaseModel):
    document_type: str
    summary: str
    entities: list[DocumentEntity]
    possible_actions: list[PossibleAction]

class DocumentEntity(BaseModel):
    entity_type: str
    entity_value: str
    raw_text: str | None
    confidence: float

class PossibleAction(BaseModel):
    action_type: str
    title: str
    due_at: str | None
    confidence: float
    source_reason: str
```

### 18.3 Action card generation schema

```python
class ActionCardDraft(BaseModel):
    card_type: str
    title: str
    description: str
    priority: Literal["low", "medium", "high", "urgent"]
    due_at: str | None
    source_refs: list[SourceRef]
    suggested_actions: list[SuggestedAction]
    confidence: float
```

### 18.4 Final response rules

Assistant responses must:

1. Be direct and useful.
2. Separate confirmed facts from uncertain inferences.
3. Include account labels.
4. Include action cards when relevant.
5. Include source references.
6. Never say an action is completed unless tool execution succeeded.

---

## 19. Action card types

Implement these card types:

```text
reply_needed
follow_up
deadline
renewal
calendar_conflict
document_expiry
invoice
meeting_prep
automation_suggestion
custom
```

Suggested action types:

```text
create_reminder
draft_email
open_source
mark_done
snooze
dismiss
create_automation
trigger_n8n_workflow
```

Card priority rules:

```text
urgent: due within 24 hours or high-impact conflict
high: due within 3 days, important sender, money/legal/work obligation
medium: due within 14 days or likely useful follow-up
low: informational or low confidence
```

---

## 20. n8n integration

### 20.1 Role of n8n

n8n handles repeatable workflows and scheduled/background automations. Hey Broski owns core logic, action cards, safety, and auditing.

### 20.2 n8n workflows to ship

Create JSON exports under:

```text
n8n/workflows/
```

#### daily-brief.json

Trigger:

```text
Cron every morning, configurable.
```

Action:

```text
Call Hey Broski /api/automations/daily-brief/run endpoint.
```

Output:

```text
Create daily action cards and summary.
```

#### renewal-watch.json

Trigger:

```text
Webhook from Hey Broski when new renewal card is created.
```

Action:

```text
Create reminder card or calendar reminder after approval.
```

#### followup-watch.json

Trigger:

```text
Daily cron.
```

Action:

```text
Ask Hey Broski to detect stale follow-ups.
```

#### invoice-tracker.json

Trigger:

```text
Webhook when invoice document is indexed.
```

Action:

```text
Create invoice action card.
```

#### meeting-prep.json

Trigger:

```text
Cron every 30 minutes.
```

Action:

```text
Find upcoming meetings and prepare brief cards.
```

### 20.3 n8n trigger API

Hey Broski endpoint:

```text
POST /api/automations/n8n/webhook/{workflow_key}
```

Verify shared secret:

```text
X-HeyBroski-Webhook-Secret
```

---

## 21. Sync and indexing jobs

Use APScheduler for internal scheduled jobs.

Jobs:

```text
sync_connected_accounts_every_15_minutes
detect_action_cards_every_30_minutes
refresh_daily_brief_every_morning
reindex_failed_documents_every_hour
cleanup_old_cache_weekly
```

MVP should also provide manual sync buttons in UI.

Sync rules:

1. Do not full-sync every run.
2. Use provider cursors where available.
3. Limit first sync to recent messages unless user expands range.
4. Store sync errors visibly.
5. Keep per-account sync state isolated.

---

## 22. Source references

Every answer and action card must include source references.

Source reference shape:

```json
{
  "source_type": "email",
  "source_id": "uuid",
  "connected_account_id": "uuid",
  "account_label": "Outlook / Work",
  "title": "Project update request",
  "snippet": "Can you send the report by Friday?",
  "timestamp": "2026-08-13T10:30:00Z"
}
```

Document source reference:

```json
{
  "source_type": "document",
  "source_id": "uuid",
  "title": "sony_headphones_invoice.pdf",
  "page_number": 1,
  "snippet": "Warranty valid until 2027-01-15"
}
```

Calendar source reference:

```json
{
  "source_type": "calendar_event",
  "source_id": "uuid",
  "account_label": "Google Calendar / Personal",
  "title": "Bank appointment",
  "timestamp": "2026-08-16T11:00:00+05:30"
}
```

---

## 23. Security and privacy requirements

### 23.1 Data location

Default data stays local.

Do not send user emails, documents, calendar data, or embeddings to a third-party AI API.

### 23.2 OAuth tokens

Token storage order:

1. OS keychain through `keyring`.
2. Encrypted local fallback using `cryptography` if keychain is unavailable.
3. Never plaintext SQLite.

### 23.3 Permissions

Use minimum scopes.

Gmail:

- Start with read-only and compose.
- Add modify only when needed.
- Sending disabled by default.

Microsoft:

- Start with `Mail.Read` and `offline_access`.
- Add `Mail.ReadWrite` only for drafts.
- Add `Calendars.ReadWrite` only for calendar creation.

Filesystem:

- Access only user-selected folders.
- Store allowlist.
- Never recursively index entire home directory by default.

### 23.4 Audit logs

Log every tool call with redacted arguments.

Never log:

- OAuth access tokens.
- Refresh tokens.
- Full email bodies in audit logs.
- Raw confidential document text in audit logs.

### 23.5 Approval matrix

```text
Read indexed data: no approval
Search email: no approval, audited
Fetch full email body: no approval, audited
Create email draft: approval required
Send email: disabled by default, high-risk approval if enabled later
Create calendar reminder: approval required
Create automation rule: approval required
Trigger n8n workflow: approval required
Delete email/file: blocked in MVP
Share document: blocked in MVP
```

---

## 24. Demo data

Create a demo dataset so reviewers can test the product instantly.

Directory:

```text
demo-data/
  emails/
    gmail_personal.json
    outlook_work.json
  calendar/
    personal_calendar.json
    work_calendar.json
  documents/
    electricity_bill.pdf
    headphones_warranty.pdf
    insurance_policy.pdf
    rent_agreement.pdf
    resume_request_email_attachment.pdf
  expected_outputs/
    daily_attention_summary.json
```

Demo scenarios:

1. Credit card bill due in 5 days.
2. Canva trial renewal soon.
3. Recruiter waiting for updated resume.
4. Manager waiting for project report.
5. Bank appointment on calendar with related document.
6. Headphones warranty expiring soon.
7. Insurance renewal date in document.
8. Calendar conflict between two work meetings.
9. Invoice payment due.
10. Stale follow-up from freelancer client.

The demo must work without Gmail/Outlook OAuth.

---

## 25. Implementation phases

### Phase 0 - Repository setup

Deliverables:

- Monorepo structure.
- Docker Compose.
- Frontend app booting.
- Backend app booting.
- Health endpoint.
- SQLite connection.
- Alembic migration setup.
- Ollama health check.
- n8n container.
- `.env.example`.

Acceptance criteria:

```text
docker compose up starts web, api, ollama, and n8n.
http://localhost:3000 loads UI.
http://localhost:8000/api/health returns healthy or actionable model-missing status.
```

### Phase 1 - ChatKit local chat with Ollama

Deliverables:

- ChatKit UI integrated.
- Backend chat endpoint.
- Ollama LLM gateway.
- Basic chat messages persisted.
- Settings show active model.

Acceptance criteria:

```text
User can chat with local Qwen3 model.
No cloud LLM key is required.
Messages are stored in SQLite.
```

### Phase 2 - Action cards and approval system

Deliverables:

- action_cards table.
- approval_requests table.
- Action Inbox UI.
- Create/dismiss/snooze/approve card flows.
- Audit log for approvals.

Acceptance criteria:

```text
Backend can create action cards.
UI displays cards.
User can approve/reject actions.
Risky actions are not executed without approval.
```

### Phase 3 - Demo data ingestion

Deliverables:

- Demo email loader.
- Demo calendar loader.
- Demo document loader.
- Seed command.
- Daily attention summary working from demo data.

Acceptance criteria:

```text
User can enable demo mode and ask: "What needs my attention this week?"
System returns at least 5 grounded action cards with sources.
```

### Phase 4 - Document vault

Deliverables:

- Document upload.
- Text extraction.
- Chunking.
- Embeddings.
- LanceDB search.
- Entity extraction.
- Document action cards.
- Vault UI.

Acceptance criteria:

```text
User uploads a PDF invoice or warranty.
System extracts key dates/entities.
System creates an action card if a due date or expiry exists.
User can ask questions about the document with source references.
```

### Phase 5 - Gmail connector

Deliverables:

- OAuth start/callback.
- Token storage.
- Message sync.
- Thread normalization.
- Incremental sync cursor.
- Gmail source labels.
- Draft creation after approval.

Acceptance criteria:

```text
Developer-mode Gmail account can connect.
Recent Gmail messages sync locally.
Messages appear with Gmail / Personal label.
System can identify reply-needed emails.
System can create a Gmail draft only after approval.
```

### Phase 6 - Outlook connector

Deliverables:

- Microsoft OAuth start/callback using MSAL.
- Token storage.
- Message sync through Graph.
- Delta sync where possible.
- Outlook source labels.
- Draft creation after approval.

Acceptance criteria:

```text
Developer-mode Outlook account can connect.
Recent Outlook messages sync locally.
Messages appear with Outlook / Work label.
System can identify reply-needed emails.
System can create an Outlook draft only after approval.
```

### Phase 7 - Calendar support

Deliverables:

- Demo calendar support.
- Google Calendar read support.
- Microsoft Calendar read support.
- Conflict detection.
- Reminder/event creation after approval.

Acceptance criteria:

```text
System detects upcoming meetings and conflicts.
System creates reminder proposal.
Reminder is created only after approval.
```

### Phase 8 - MCP tool layer

Deliverables:

- Hey Broski MCP server.
- Tool registry.
- Read-only tools.
- Approval-required tools.
- Audit integration.
- Orchestrator uses MCP tools internally.

Acceptance criteria:

```text
At least email.search_messages, documents.search, calendar.list_events, actions.create_card, and n8n.trigger_workflow exist as MCP-style tools.
Tool calls are audited.
Risky tool calls create approval requests.
```

### Phase 9 - n8n integration

Deliverables:

- n8n Docker service.
- Hey Broski webhook endpoints.
- Workflow exports.
- Automation UI.
- Natural-language automation draft.

Acceptance criteria:

```text
User can create a renewal reminder automation from chat.
System creates a pending automation rule.
After approval, n8n workflow can be triggered or linked.
```

### Phase 10 - Polish, tests, and documentation

Deliverables:

- README.
- Demo script.
- Architecture docs.
- OAuth setup docs.
- Security docs.
- Unit tests.
- Integration tests.
- Playwright E2E tests.
- Screenshots/GIF-ready demo flow.

Acceptance criteria:

```text
Fresh clone can run demo with documented commands.
Core flows pass tests.
GitHub repo looks polished and portfolio-ready.
```

---

## 26. Testing plan

### 26.1 Unit tests

Test:

- LLM gateway schema validation.
- Source reference generation.
- Action card priority logic.
- Commitment extraction parser.
- Document extraction parser.
- Safety policy matrix.
- Token service redaction.

### 26.2 Integration tests

Test:

- Demo data ingestion.
- SQLite migrations.
- LanceDB indexing/search.
- Gmail mapper using fixture API responses.
- Outlook mapper using fixture API responses.
- Approval execution flow.
- n8n webhook flow with mocked n8n.

### 26.3 E2E tests

Use Playwright.

Flows:

1. Enable demo data.
2. Ask daily attention question.
3. See action cards.
4. Open source citation.
5. Approve reminder creation.
6. Dismiss action card.
7. Upload document and ask question.

### 26.4 LLM regression tests

Use fixed demo data and expected structured outputs.

Tests:

```text
Daily summary contains at least 5 relevant action cards.
Credit card due date is detected.
Manager follow-up is detected.
Warranty expiry is detected.
Calendar conflict is detected.
No unsupported source is fabricated.
No action is marked completed without execution result.
```

---

## 27. Observability

Create backend structured logs.

Log fields:

```text
event_name
request_id
user_id
tool_name
account_provider
latency_ms
status
error_code
model_name
```

UI status indicators:

- Ollama reachable/unreachable.
- Active model pulled/missing.
- Last sync status per account.
- n8n reachable/unreachable.
- Background jobs status.

---

## 28. Error handling

Common errors and UX messages:

### Missing Ollama model

```text
Qwen3 model is not installed locally. Run: ollama pull qwen3:8b
```

### Gmail auth expired

```text
Gmail connection expired. Reconnect Personal Gmail from Accounts.
```

### Outlook admin consent blocked

```text
Your Microsoft 365 tenant requires admin approval for this app. You can use demo mode or connect a personal Outlook account.
```

### Document OCR unavailable

```text
This appears to be a scanned document, but OCR is not configured. Install Tesseract or upload a text-based PDF.
```

### n8n unavailable

```text
n8n is not reachable. The automation was saved but not triggered.
```

---

## 29. UX copy principles

Use simple wording:

- Say "Needs your attention" instead of "high-salience task".
- Say "Source" instead of "retrieval artifact".
- Say "Approve" instead of "execute tool call".
- Say "Work Outlook" and "Personal Gmail" clearly.

Every generated answer should be practical and actionable.

---

## 30. README requirements

README must include:

1. Product screenshot or placeholder.
2. What Hey Broski does.
3. Why local-first.
4. Features.
5. Architecture diagram.
6. Quickstart.
7. Model setup.
8. Demo mode instructions.
9. Gmail developer OAuth setup.
10. Outlook developer OAuth setup.
11. n8n workflow import instructions.
12. Security principles.
13. Roadmap.
14. Contribution guide.

Quickstart target:

```bash
git clone <repo>
cd hey-broski
cp .env.example .env
docker compose up
```

Model setup:

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Demo:

```text
Open http://localhost:3000
Click Enable Demo Mode
Ask: What needs my attention this week?
```

---

## 31. Final MVP acceptance criteria

The project is considered complete for MVP when all of the following are true:

1. A fresh user can run the app locally.
2. The app starts without paid API keys.
3. Chat UI works with local Ollama model.
4. Demo mode works without external account connections.
5. User can upload documents and ask questions about them.
6. The system creates action cards from demo emails, calendar events, and documents.
7. Source references are shown for answers and cards.
8. Gmail developer-mode connection works.
9. Outlook developer-mode connection works.
10. Multiple accounts are labeled and filterable.
11. Risky actions require approval.
12. Audit logs show tool calls and approval decisions.
13. At least one n8n workflow can be triggered after approval.
14. The README explains how to run the project.
15. Tests cover core flows.
16. The UI looks like a real product, not a notebook demo.

---

## 32. Suggested first coding sequence

Follow this exact sequence to avoid getting stuck:

1. Create monorepo and basic Docker Compose.
2. Build FastAPI health endpoint.
3. Build Next.js shell with sidebar and blank chat page.
4. Connect ChatKit UI to backend.
5. Add Ollama LLM gateway.
6. Persist chat threads/messages.
7. Create SQLite models and migrations.
8. Build action card service and UI.
9. Add demo data loader.
10. Implement daily attention summary from demo data.
11. Add document upload and extraction.
12. Add LanceDB indexing/search.
13. Add source references.
14. Add approval requests.
15. Add Gmail connector.
16. Add Outlook connector.
17. Add calendar connector.
18. Add MCP tool registry.
19. Add n8n webhook integration.
20. Polish UI and docs.

---

## 33. Future roadmap after MVP

Post-MVP features:

1. Tauri desktop app.
2. Local notifications.
3. Google Drive file picker.
4. OneDrive file picker.
5. Browser extension for saving pages/emails.
6. Better semantic person memory graph.
7. Meeting prep packs.
8. Invoice tracker dashboard.
9. Subscription tracker dashboard.
10. More robust workflow builder for n8n.
11. Export/import personal vault.
12. Encrypted backup.
13. Mobile companion app.
14. Plugin marketplace for Hey Broski tools.
15. Advanced RAG evaluation dashboard.

---

## 34. Quality bar

The app should feel like a product users can return to regularly.

Must-have UX qualities:

- Fast enough for daily use.
- Clear account labels.
- Clear sources.
- Clear approvals.
- No scary hidden actions.
- Helpful empty states.
- Demo data that tells a story.
- Error messages that explain how to fix the issue.

Portfolio qualities:

- Clean architecture.
- Good README.
- Dockerized setup.
- Demo video possible.
- Real integrations.
- Local LLM support.
- MCP and n8n usage is meaningful, not decorative.
- Tests prove reliability.

---

## 35. One-sentence positioning

Hey Broski is a local-first personal admin copilot powered by ChatKit, Ollama, MCP tools, n8n workflows, and multi-agent orchestration that turns emails, calendars, and documents into a safe, source-grounded daily action inbox.

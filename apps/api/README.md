# Hey Broski Backend API - Python Project

## Project Overview

A local FastAPI backend for Hey Broski with LLM gateway, MCP tools, and domain services.

## Python Version Requirements

Python 3.11 or newer. This project is designed to work with modern Python features and async/await patterns.

## Installation

### From Scratch
```bash
# Clone the repository
cd into your project directory and run:

git clone <repo>
cd heybroski

# Set up environment configuration
cp .env.example .env

# Navigate to backend directory
cd apps/api

# Install the package in development mode
pip install -e .

# Or install dependencies from requirements.txt (generated)
pip install -r requirements.txt
```

### Docker Installation
```bash
# Build and run the backend service
docker build -t heybroski/api .
docker run -p 8000:8000 heybroski/api
```

## Development

### Running the Application
```bash
# Start the FastAPI application with auto-reload for development
cd apps/api
uvicorn main:app --reload
```

### Database Migrations
```bash
# Create a new migration
alembic revision --autogenerate "description_of_changes"

# Apply all migrations
 alembic upgrade head

# Check migration history
 alembic history

# Show current migration status
 alembic current
```

### Database Operations
```bash
# Seed demo data for testing and development
python -m manage seed_demo
```

### Environment Setup
```bash
# Copy environment example to .env
cd apps/api
cp .env.example .env

# Edit .env with your configuration
# Key variables:
# - DATABASE_URL: SQLite database connection
# - OLLAMA_BASE_URL: Ollama server URL
# - HEYBROSKI_CHAT_MODEL: Default chat model
# - GOOGLE_CLIENT_ID/SECRET: Gmail OAuth credentials
```

## Project Structure

### Core Components
```
apps/api/
├── alembic.ini              # Alembic configuration
├── app/                     # Main application code
│   ├── __init__.py
│   ├── config.py            # Application configuration
│   ├── main.py              # FastAPI application entry point
│   ├── db/                  # Database layer
│   │   ├── __init__.py
│   │   ├── session.py       # Database session management
│   │   ├── models.py        # SQLAlchemy models
│   │   └── migrations/      # Alembic migration scripts
│   ├── ai/                 # AI and LLM components
│   │   ├── llm_gateway.py   # Interface to Ollama
│   │   ├── prompts.py      # Prompt templates
│   │   └── schemas.py      # Pydantic validation schemas
│   ├── agents/             # Agent implementations
│   │   ├── orchestrator.py # Main agent orchestrator
│   │   ├── inbox_agent.py  # Email processing agent
│   │   ├── document_agent.py # Document processing agent
│   │   ├── calendar_agent.py # Calendar processing agent
│   │   ├── automation_agent.py # Automation agent
│   │   └── safety_agent.py # Safety and policy agent
│   │   └── memory_agent.py # Memory and learning agent
│   ├── services/           # Domain services
│   │   ├── chat_service.py
│   │   ├── action_card_service.py
│   │   ├── approval_service.py
│   │   ├── audit_service.py
│   │   ├── document_service.py
│   │   ├── email_service.py
│   │   ├── calendar_service.py
│   │   ├── automation_service.py
│   │   ├── sync_service.py
│   │   └── search_service.py
│   │   └── token_service.py
│   ├── connectors/         # External API connectors
│   │   ├── gmail/           # Gmail API connector
│   │   │   ├── oauth.py     # Gmail OAuth implementation
│   │   │   ├── client.py   # Gmail API client
│   │   │   ├── sync.py     # Gmail sync logic
│   │   │   └── mapper.py  # Data mapping utilities
│   │   ├── outlook/         # Outlook API connector
│   │   │   ├── oauth.py     # Outlook OAuth implementation
│   │   │   ├── client.py   # Outlook API client
│   │   │   ├── sync.py     # Outlook sync logic
│   │   │   └── mapper.py  # Data mapping utilities
│   │   └── local_files/     # Local file system connector
│   │       ├── watcher.py  # File system monitoring
│   │       └── extractor.py # File content extraction
│   │       └── mapper.py  # Data mapping utilities
│   │   └── google_drive/   # Google Drive connector
│   │       └── client.py   # Google Drive API client
│   │   └── onedrive/        # OneDrive connector
│   │       └── client.py   # OneDrive API client
│   ├── mcp_tools/          # Model Context Protocol tools
│   │   ├── server.py       # MCP server implementation
│   │   ├── registry.py     # Tool registry
│   │   ├── email_tools.py  # Email-related MCP tools
│   │   ├── calendar_tools.py # Calendar-related MCP tools
│   │   ├── document_tools.py # Document-related MCP tools
│   │   ├── action_tools.py  # Action card MCP tools
│   │   └── automation_tools.py # Automation MCP tools
│   └── api_routes/         # FastAPI API endpoints
│       ├── chat.py         # Chat-related endpoints
│       ├── actions.py      # Action card endpoints
│       ├── approvals.py    # Approval endpoints
│       ├── accounts.py     # Account management endpoints
│       ├── documents.py    # Document endpoints
│       ├── search.py       # Search endpoints
│       ├── automations.py  # Automation endpoints
│       ├── audit.py        # Audit logging endpoints
│       ├── settings.py     # Settings endpoints
│       └── health.py       # Health check endpoints
│   └── jobs/               # Scheduled background jobs
│       ├── scheduler.py      # Job scheduler
│       ├── sync_jobs.py      # Sync-related jobs
│       └── action_detection_jobs.py # Action detection jobs
│   └── tests/             # Test suite
│       ├── unit/           # Unit tests
│       └── integration/    # Integration tests
├── pyproject.toml          # Python project configuration
├── alembic.ini             # Alembic configuration
├── Dockerfile              # Docker image configuration
└── requirements.txt        # Dependencies (automatically generated)
```

### Dependencies

#### Core Backend Dependencies
```python
# Web framework
fastapi                    # FastAPI web framework
uvicorn[standard]          # ASGI server with standard features
pydantic                   # Data validation and settings management
pydantic-settings          # Settings management

# Database
SQLAlchemy                # SQL toolkit and ORM
SQLModel                   # Simplified SQLAlchemy interface
Alembic                    # Database migration tool
aiosqlite                 # Async SQLite driver

# HTTP and API
httpx                       # HTTP client for external APIs
python-multipart          # Multipart form data handling

# Scheduling
APScheduler                # Advanced Python Scheduler

# Security and Authentication
keyring                    # OS keychain integration
cryptography              # Cryptographic utilities for token storage

# Logging and Monitoring
structlog                 # Structured logging

# Testing
pytest                      # Testing framework
pytest-asyncio            # Async test support
respx                      # HTTP mocking
freezegun                  # Time travel testing
```

#### AI and LLM Dependencies
```python
# Local LLM integration
openai                    # OpenAI-compatible client for Ollama
ollama                    # Ollama Python client
langchain-core           # LangChain core components
langgraph                 # LangGraph for agent orchestration
mcp                        # Model Context Protocol
lancedb                   # Vector database

# Model utilities
sentence-transformers    # Text embedding models
numpy                      # Numerical operations
pandas                     # Data manipulation
```

#### Document Processing Dependencies
```python
# Document parsing and extraction
PyMuPDF                   # Fast PDF processing
pypdf                     # PDF utilities
python-docx                # DOCX file processing
pillow                     # Image processing
pytesseract               # OCR

# Optional advanced OCR (later phases)
paddleocr                 # OCR with PaddlePaddle
rapidocr-onnxruntime      # OCR with ONNX
unstructured              # Document unstructured parsing
markitdown                # Document format conversion
```

#### Email and Calendar Dependencies
```python
# Gmail API
google-api-python-client  # Google API client
google-auth               # Google authentication
google-auth-oauthlib      # OAuth2 utilities
google-auth-httplib2      # HTTP library

# Microsoft Graph API
msal                      # Microsoft Authentication Library
```

## Key Features

### 1. LLM Gateway
- **Unified interface** to local Ollama inference
- **Model configuration** from environment variables
- **Structured outputs** using Pydantic validation
- **Latency tracking** and model metrics
- **Fallback support** for multiple models

### 2. Agent Orchestration
- **Deterministic intent classification** using LLMs
- **Tool selection** based on user intent
- **Safety policy enforcement** before tool execution
- **Grounded response generation** with source citations
- **Action card creation** from agent analysis

### 3. Domain Services
- **Email Service**: Gmail/Outlook connector, sync, and processing
- **Calendar Service**: Event management and conflict detection
- **Document Service**: Upload, extraction, and semantic search
- **Action Card Service**: Card lifecycle management and approval
- **Automation Service**: n8n workflow integration
- **Memory Service**: Person and commitment tracking
- **Audit Service**: Immutable tool call logs

### 4. MCP Tool Layer
- **Tool registry** with risk classification
- **Read-only tools** requiring no approval
- **Approval-required tools** with audit logging
- **Safe execution policies** preventing unauthorized actions
- **Integration with agents** for tool coordination

### 5. Storage Layer
- **SQLite**: Relational metadata storage for users, accounts, and entities
- **LanceDB**: Vector search and document indexing
- **Local file cache**: Extracted text and attachments
- **OS keychain**: Secure OAuth token storage

## Database Schema

The database uses SQLite with the following core tables:

### Users
- Local user profile management (single-user MVP, extensible for multiple profiles)

### Connected Accounts
- External account connections (Gmail, Outlook, Calendar, Drive, local folders)
- OAuth token references (stored in OS keychain, not in database)
- Sync state tracking

### Email Threads and Messages
- Normalized email metadata across providers
- Importance scoring and attention detection
- Thread organization and message indexing

### Calendar Events
- Event storage from Google Calendar, Outlook Calendar, and local reminders
- Conflict detection and preparation support

### Documents
- Indexed document metadata from uploads, local folders, and cloud storage
- Document type classification and entity extraction
- Semantic search via LanceDB vector index

### Action Cards
- User-facing actionable cards created from agent analysis
- Multi-stage lifecycle (open → approved → completed → dismissed)
- Source references and suggested actions

### Approval Requests
- Human approval flow for risky external actions
- Audit trail for approval decisions
- Link to related action cards

### Chat Threads and Messages
- Conversation history and context
- Source references and action cards from responses
- Performance metrics (latency, model usage)

### Tool Call Audit Logs
- Immutable log of every tool call and approval
- Redacted arguments for security
- Audit trail for compliance

### Automation Rules
- User-defined automation workflows
- Support for n8n integration
- Approval before execution

## API Endpoints

### Health and Status
```
GET /api/health
    Returns service health, database status, Ollama status, and n8n status.
```

### Chat
```
POST /api/chat/sessions
    Create a new chat session.

GET /api/chat/sessions
    List all chat sessions for the user.

GET /api/chat/sessions/{thread_id}
    Get a specific chat session.

POST /api/chat/sessions/{thread_id}/messages
    Send a message to a chat session.
```

### Action Cards
```
GET /api/actions
    List all action cards for the user.

GET /api/actions/{id}
    Get a specific action card.

POST /api/actions/{id}/dismiss
    Dismiss an action card.

POST /api/actions/{id}/snooze
    Snooze an action card.

POST /api/actions/{id}/approve
    Approve an action card.

POST /api/actions/{id}/complete
    Mark an action card as completed.
```

### Approvals
```
GET /api/approvals/pending
    List pending approval requests.

POST /api/approvals/{id}/approve
    Approve an approval request.

POST /api/approvals/{id}/reject
    Reject an approval request.

POST /api/approvals/{id}/edit
    Edit an approval request before execution.
```

### Account Management
```
GET /api/accounts
    List all connected accounts.

POST /api/accounts/demo/enable
    Enable demo mode for testing.

POST /api/accounts/gmail/start
    Start Gmail OAuth flow.

GET /api/accounts/gmail/callback
    Gmail OAuth callback handler.

POST /api/accounts/outlook/start
    Start Outlook OAuth flow.

GET /api/accounts/outlook/callback
    Outlook OAuth callback handler.

POST /api/accounts/{id}/sync
    Manually sync a connected account.

DELETE /api/accounts/{id}
    Disconnect a connected account.
```

### Document Management
```
POST /api/documents/upload
    Upload a new document.

GET /api/documents
    List all documents.

GET /api/documents/{id}
    Get document details.

POST /api/documents/{id}/reindex
    Reindex a document.

DELETE /api/documents/{id}
    Delete a document.

POST /api/documents/local-folder
    Scan a local folder for documents.
```

### Search
```
POST /api/search
    Semantic search across documents, emails, and other content.
```

### Automations
```
GET /api/automations
    List all automation rules.

POST /api/automations
    Create a new automation rule.

POST /api/automations/{id}/enable
    Enable an automation rule.

POST /api/automations/{id}/disable
    Disable an automation rule.

POST /api/automations/{id}/run-now
    Run an automation rule immediately.

DELETE /api/automations/{id}
    Delete an automation rule.
```

### Audit
```
GET /api/audit
    List all audit logs.

GET /api/audit/{id}
    Get a specific audit log entry.
```

### Settings
```
GET /api/settings
    Get user settings.

PATCH /api/settings
    Update user settings.
```

## Testing

### Unit Tests
```bash
# Run unit tests
cd apps/api
pytest tests/unit/ -v

# Run specific test module
cd apps/api
pytest tests/unit/test_llm_gateway.py -v
```

### Integration Tests
```bash
# Run integration tests
cd apps/api
pytest tests/integration/ -v

# Run specific integration test
cd apps/api
pytest tests/integration/test_demo_data.py -v
```

### E2E Tests
```bash
# Frontend E2E tests
cd apps/web
pnpm run test:e2e

# Or run with Playwright
cd apps/web
npx playwright test
```

## Configuration

### Environment Variables
See `.env.example` in the project root for all configuration options.

### Key Configuration Variables
```bash
# App configuration
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

# Gmail OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/accounts/gmail/callback

# Microsoft OAuth
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

### Model Configuration
- Default chat model: `qwen3:8b`
- Default embedding model: `nomic-embed-text`
- Model temperature: `0.2`
- All models can be overridden via `.env`

### Storage Configuration
- Default data directory: `~/.hey-broski`
- SQLite database: `heybroski.db`
- LanceDB vector store: `lancedb/`
- Local file cache: `cache/` directory

## Performance Optimizations

### For Limited Hardware
- Use smaller models: `qwen3:4b` or `qwen3:1.7b`
- Disable CPU-intensive features like OCR
- Reduce demo data scope
- Use SQLite with WAL mode
- Consider single-threaded processing

### For Production
- Use PostgreSQL instead of SQLite
- Implement reverse proxy (nginx)
- Set up monitoring and alerting
- Regular backups of data volumes

## Troubleshooting

### Common Issues and Solutions

#### Ollama Not Running
```bash
# Start Ollama service
docker compose up -d ollama

# Or run manually
ollama serve
```

#### Model Not Found
```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

#### Database Connection Issues
```bash
# Check file permissions
chmod 700 ~/.hey-broski

# Recreate database if needed
docker compose exec api rm -f heybroski.db
```

#### Gmail OAuth Setup
```bash
# Set up Google Cloud project with OAuth consent screen
# Configure redirect URI: http://localhost:8000/api/accounts/gmail/callback
# Get client ID and secret
```

#### Outlook OAuth Setup
```bash
# Set up Microsoft Azure app registration
# Configure web platform: http://localhost:8000
# Get client ID and secret
```

## Development Workflow

### Phase 0: Repository Setup
1. Create monorepo structure ✓
2. Set up Docker Compose ✓
3. Create README and documentation ✓
4. Set up environment configuration ✓

### Phase 1: ChatKit + Ollama Gateway
1. Implement ChatKit adapter in backend ✓
2. Add Ollama LLM gateway with model configuration ✓
3. Set up basic chat message persistence ✓
4. Create settings page showing active model ✓

### Phase 2: Action Cards and Approval System
1. Create action_cards table in database
2. Create approval_requests table
3. Implement action card service and API endpoints
4. Build action inbox UI with approve/reject/snooze/dismiss flows
5. Implement audit logging for approvals

### Phase 3: Demo Data Ingestion
1. Create demo data loader
2. Set up demo emails, calendar events, documents
3. Seed database with demo data
4. Test daily attention summary from demo data

## Migration Guide

### From Previous Version
1. Run migrations: `alembic upgrade head`
2. Seed demo data: `python -m manage seed_demo`
3. Update .env configuration if needed
4. Restart services

## Future Improvements

### Phase 1-5 (Post-MVP)
1. Tauri desktop app
2. Local notifications
3. Google Drive/OneDrive integration
4. Browser extension
5. Advanced semantic person memory graph
6. Meeting prep packs
7. Invoice tracker dashboard
8. Subscription tracker dashboard
9. More robust workflow builder for n8n

## Version Information

- **Version**: 0.1.0 (MVP Phase 0)
- **Status**: In Development
- **Target**: Production-ready MVP with demo mode
- **License**: Proprietary

---

Built with zero paid APIs, local LLMs, and complete data ownership.

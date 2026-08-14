# Hey Broski

Local-first personal admin copilot with ChatKit, Ollama, MCP tools, and n8n workflows.

## Quickstart

```bash
git clone <repo>
cd hey-broski
cp .env.example .env
docker compose up
```

Open http://localhost:3000

## What does Hey Broski do?

Hey Broski turns emails, calendars, and documents into a safe, source-grounded daily action inbox.

- Read connected emails, calendars, and documents
- Detect commitments, deadlines, renewals, and follow-ups
- Answer questions through chat
- Create action cards
- Trigger approved automations

## Why local-first?

- Zero paid API dependencies
- Complete data ownership
- Works offline
- GDPR compliant by default

## Features

- Chat UI using ChatKit
- Local FastAPI backend
- Local LLM through Ollama (Qwen3 8B)
- SQLite metadata database
- LanceDB vector index
- Demo mode for instant evaluation
- Local document upload and indexing
- Gmail/Outlook developer OAuth
- Action card generation
- Human approval system
- Audit logging
- n8n workflow integration
- MCP tool layer

## Architecture

```
User -> Next.js + ChatKit
         ↓
FastAPI Backend
         ↓
- Chat runtime adapter
- Agent orchestrator
- Local LLM gateway (Ollama)
- MCP tool router
- Domain services
  - Email, Calendar, Document
  - Action cards
  - Automations
  - Memory
  - Audit
         ↓
Storage
  - SQLite metadata
  - LanceDB vectors
  - Local file cache
  - OS keychain
         ↓
External
  - Gmail API
  - Microsoft Graph
  - Local filesystem
  - n8n workflows
```

## Model Setup

```bashnollama pull qwen3:8b
ollama pull nomic-embed-text
```

## Demo Mode

```bash
Open http://localhost:3000
Click "Enable Demo Mode"
Ask: What needs my attention this week?
```

## Gmail Developer OAuth

Configure in Google Cloud Console:
- OAuth consent screen
- Authorized JavaScript origins: http://localhost:8000
- Redirect URIs: http://localhost:8000/api/accounts/gmail/callback

## Outlook Developer OAuth

Configure in Microsoft Azure:
- Web platform: http://localhost:8000
- Redirect URIs: http://localhost:8000/api/accounts/outlook/callback

## n8n Workflow Import

Import the provided JSON workflows into n8n.

## Security Principles

- Local-first data storage
- OAuth tokens in OS keychain
- No raw tokens in SQLite
- Source-grounded responses
- Approval required for external actions

## Roadmap

Post-MVP:
- Tauri desktop app
- Google Drive/OneDrive integration
- Local notifications
- Advanced semantic person memory
- Export/import personal vault
- Encrypted backup
- Mobile companion app

## Contribution Guide

1. Clone and run `docker compose up`
2. Focus on MVP core flows
3. Follow the implementation sequence in plan.md
4. Each commit must include tests

## Live Demo

The project includes a demo script for quick evaluation without configuration.

---

This repository is under active development. The architecture supports local LLMs, MCP tools, and n8n workflows while maintaining complete privacy and zero-cost operation.

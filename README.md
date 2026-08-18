# Hey Broski

Local-first personal admin copilot with ChatKit, Ollama, MCP tools, and n8n workflows.

## Quickstart (GitHub Codespaces - Recommended)

The easiest way to run Hey Broski is using **GitHub Codespaces** - no local Docker setup required.

### 1. Open in Codespaces
- Go to the repository on GitHub
- Click **Code** → **Codespaces** → **Create codespace on main**
- Wait for the environment to load (2-3 minutes)

### 2. Start all services
```bash
docker compose up -d
```

### 3. Wait for models to download (first run only)
```bash
docker compose logs -f ollama
# Wait for "success" messages for qwen3:8b and nomic-embed-text (~2-5 min)
```

### 4. Access the application
- **Frontend (Chat UI)**: Click the forwarded port **3000** in the Ports tab (globe icon)
- **Backend API**: Port **8000** → `/api/health`
- **n8n**: Port **5678** → `/setup`
- **Ollama**: Port **11434** → `/api/tags`

---

## Local Development (Docker Desktop / Rancher Desktop / Podman)

### Prerequisites
- Docker Engine + Docker Compose v2
- Or Podman with `podman compose`
- 8GB+ RAM recommended

### Start Services
```bash
# Clone and configure
git clone <repo>
cd hey-broski
cp .env.example .env

# Start all services in background
docker compose up -d

# Or with Podman
podman compose up -d
```

### Stop Services
```bash
# Stop and remove containers (keeps volumes/data)
docker compose down

# Stop only (keeps containers for restart)
docker compose stop

# Start previously stopped containers
docker compose start
```

### Rebuild After Code Changes
```bash
# Rebuild specific service (e.g., after API changes)
docker compose up -d --build --force-recreate api

# Rebuild all services
docker compose up -d --build

# Rebuild without cache
docker compose up -d --build --pull always
```

### View Logs
```bash
# All services
docker compose logs -f

# Specific service (last 50 lines)
docker compose logs web --tail 50
docker compose logs api --tail 50
docker compose logs ollama --tail 50
docker compose logs n8n --tail 50

# Follow live logs
docker compose logs -f web
docker compose logs -f api
```

### Check Status
```bash
# List running containers
docker ps

# Detailed status with health checks
docker compose ps

# Resource usage
docker stats
```

### Access Services Locally
| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Chat UI |
| API Health | http://localhost:8000/api/health | Backend health |
| n8n | http://localhost:5678 | Workflow editor |
| Ollama | http://localhost:11434/api/tags | Model management |

---

## First Run - Model Download

On first startup, Ollama downloads models automatically:
- **qwen3:8b** (~5.2 GB) - Main chat model
- **nomic-embed-text** (~274 MB) - Embedding model

```bash
# Monitor progress
docker compose logs -f ollama

# Verify models loaded
docker compose exec api python -c "
import ollama
client = ollama.Client(host='http://ollama:11434')
print([m['name'] for m in client.list()['models']])
"
```

Expected output:
```
['nomic-embed-text:latest', 'qwen3:8b']
```

---

## Health Checks

```bash
# Backend health (includes Ollama status)
curl http://localhost:8000/api/health

# Expected healthy response:
{
  "status": "healthy",
  "services": {
    "database": "connected",
    "ollama": "available",
    "n8n": "available"
  },
  "model": "qwen3:8b"
}
```

---

## Testing the Chat

1. Open http://localhost:3000 (or forwarded port 3000 in Codespaces)
2. Wait for green "connected" status indicator
3. Try these queries:
   - "What needs my attention today?"
   - "Who is waiting on me?"
   - "Find upcoming renewals and deadlines"
   - "Summarize important unread emails"

The chat will respond with:
- LLM-generated response
- Source citations (demo data)
- Action cards with approve/edit/dismiss buttons

---

## Troubleshooting

### Ollama shows "unavailable"
```bash
# Check Ollama logs
docker compose logs ollama --tail 100

# Test connectivity from API container
docker compose exec api python -c "
import ollama
client = ollama.Client(host='http://ollama:11434')
print(client.list())
"

# Restart Ollama if stuck
docker compose restart ollama
```

### Frontend shows 404 / blank page
```bash
# Check web logs
docker compose logs web --tail 50

# Rebuild web
docker compose up -d --build --force-recreate web
```

### API returns 404 for /api/*
```bash
# Check API logs
docker compose logs api --tail 50

# Verify proxy config
cat apps/web/next.config.js
# Should have: destination: 'http://api:8000/api/:path*'
```

### Port conflicts
```bash
# Check what's using ports
docker compose ps
netstat -tulpn | grep -E '3000|8000|5678|11434'

# Stop conflicting services
docker compose down
```

---

## Environment Configuration

```bash
# Copy and edit
cp .env.example .env
# Edit .env with your values
```

Key variables:
| Variable | Description | Default |
|----------|-------------|---------|
| `HEYBROSKI_CHAT_MODEL` | LLM model | `qwen3:8b` |
| `HEYBROSKI_EMBEDDING_MODEL` | Embedding model | `nomic-embed-text` |
| `OLLAMA_BASE_URL` | Ollama URL (Docker) | `http://ollama:11434` |
| `GOOGLE_CLIENT_ID` | Gmail OAuth | (empty) |
| `MICROSOFT_CLIENT_ID` | Outlook OAuth | (empty) |

---

## Data Persistence

Data is stored in Docker volumes:
- `heybroski_data` - SQLite database, file cache
- `ollama_data` - Downloaded models
- `n8n_data` - Workflows, credentials

```bash
# Backup volumes
docker run --rm -v hey-broski_heybroski_data:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz /data

# Restore
docker run --rm -v hey-broski_heybroski_data:/data -v $(pwd):/backup alpine tar xzf /backup/backup.tar.gz -C /
```

---

## Development Workflow

```bash
# 1. Make code changes
# 2. Rebuild affected service
docker compose up -d --build --force-recreate api

# 3. Check logs
docker compose logs -f api

# 4. Test changes
curl http://localhost:8000/api/health
```

---

## Commands Quick Reference

| Task | Command |
|------|---------|
| Start all | `docker compose up -d` |
| Stop all | `docker compose down` |
| Restart all | `docker compose restart` |
| Rebuild API | `docker compose up -d --build --force-recreate api` |
| Rebuild Web | `docker compose up -d --build --force-recreate web` |
| View all logs | `docker compose logs -f` |
| View API logs | `docker compose logs api --tail 50` |
| View Web logs | `docker compose logs web --tail 50` |
| View Ollama logs | `docker compose logs ollama --tail 50` |
| Check status | `docker compose ps` |
| List containers | `docker ps` |
| Shell into API | `docker compose exec api bash` |
| Shell into Web | `docker compose exec web sh` |
| Test Ollama | `docker compose exec api python -c "import ollama; print(ollama.Client(host='http://ollama:11434').list())"` |

---

## Codespaces-Specific Notes

- **Port forwarding**: Codespaces auto-forwards ports 3000, 8000, 5678, 11434
- **Access URLs**: Use the "Ports" tab → globe icon for public URLs
- **Terminal**: Use the built-in terminal (Terminal → New Terminal)
- **Docker socket**: Works out of the box in Codespaces
- **Persistence**: Volumes persist across Codespace restarts

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│  Next.js    │────▶│  FastAPI    │
│  (Port 3000)│     │  (Web)      │     │  (Port 8000)│
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
                    ┌─────────────┐     ┌───────┴───────┐
                    │   Ollama    │     │     n8n       │
                    │  (Port 11434)│     │  (Port 5678)  │
                    └─────────────┘     └───────────────┘
                           │
                    ┌──────┴──────┐
                    │  Volumes    │
                    │  (Data)     │
                    └─────────────┘
```

---

## Next Steps

1. **Enable Demo Mode** in the UI for instant testing
2. **Configure OAuth** for Gmail/Outlook (optional)
3. **Add documents** via the Vault page
4. **Create n8n workflows** for automations
4. **Explore the codebase** - see `plan.md` for implementation roadmap

---

Built with zero paid APIs, local LLMs, and complete data ownership.
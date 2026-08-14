# Hey Broski - Project Setup Script

This script automates the initial setup for Hey Broski development.

## Usage

```bash
./scripts/bootstrap.sh
```

## Requirements

- Docker with Compose v2+
- Git
- Linux/macOS (Windows WSL2)

## Setup Steps

1. **Check Docker**
2. **Start Ollama** (if not running)
3. **Pull default models**
4. **Run database migrations**
5. **Seed demo data**
6. **Print local URLs**

## Commands

```bash
# Pull models if not present
ollama pull qwen3:8b
ollama pull nomic-embed-text

# Run migrations
python apps/api/manage.py migrate

# Seed demo data
python apps/api/manage.py seed_demo

# Manual Ollama setup
ollama serve &
sleep 2
ollama pull qwen3:8b
sleep 30
ollama pull nomic-embed-text
```

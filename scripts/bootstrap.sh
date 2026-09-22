#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker and run this script again." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

docker compose up -d --build
printf '%s\n' \
  "Hey Broski is starting:" \
  "  App:  http://localhost:3000" \
  "  API:  http://localhost:8000/docs" \
  "  n8n:  http://localhost:5678" \
  "Demo mode works immediately. To enable local AI, run: docker compose exec ollama ollama pull qwen3:8b"

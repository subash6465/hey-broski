$ErrorActionPreference = 'Stop'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is required. Install Docker Desktop and run this script again.'
}

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env from .env.example'
}

docker compose up -d --build
Write-Host 'Hey Broski is starting:'
Write-Host '  App:  http://localhost:3000'
Write-Host '  API:  http://localhost:8000/docs'
Write-Host '  n8n:  http://localhost:5678'
Write-Host 'The ollama-model service pulls qwen3:4b automatically. Follow progress with: docker compose logs -f ollama-model'

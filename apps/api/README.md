# Hey Broski API

FastAPI backend for the local MVP. It uses a deliberately small layered structure:

- `main.py`: HTTP boundary and validation
- `assistant.py`: retrieval, action proposals, and local Ollama generation with a grounded fallback
- `repository.py`: SQLite persistence and audit records
- `schemas.py`: API contracts
- `config.py`: environment configuration

From the repository root:

```bash
pip install -r apps/api/requirements-dev.txt
uvicorn apps.api.app.main:app --reload
pytest apps/api/tests
```

Local inference is enabled by default; when running the API outside Docker, start Ollama and pull `qwen3:4b` first. The API still returns grounded fallback answers if the model is unavailable. OpenAPI documentation is served at http://localhost:8000/docs.

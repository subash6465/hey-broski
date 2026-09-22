# Hey Broski API

FastAPI backend for the local MVP. It uses a deliberately small layered structure:

- `main.py`: HTTP boundary and validation
- `assistant.py`: retrieval, action proposals, and optional Ollama generation
- `repository.py`: SQLite persistence and audit records
- `schemas.py`: API contracts
- `config.py`: environment configuration

From the repository root:

```bash
pip install -r apps/api/requirements-dev.txt
uvicorn apps.api.app.main:app --reload
pytest apps/api/tests
```

The API works in demo mode without Ollama. OpenAPI documentation is served at http://localhost:8000/docs.

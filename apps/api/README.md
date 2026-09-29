# Hey Broski API

FastAPI backend for the local MVP. It uses a deliberately small layered structure:

- `main.py`: HTTP boundary and validation
- `assistant.py`: chunk retrieval, action proposals, and streamed local Ollama generation
- `repository.py`: SQLite conversations, message turns, document excerpts, and internal safety records
- `schemas.py`: API contracts
- `config.py`: environment configuration

From the repository root:

```bash
pip install -r apps/api/requirements-dev.txt
uvicorn apps.api.app.main:app --reload
pytest apps/api/tests
```

Local inference is required for chat; when running the API outside Docker, start Ollama and pull `qwen3:4b-instruct` first. If upgrading an existing `.env`, set `HEYBROSKI_CHAT_MODEL=qwen3:4b-instruct` and `OLLAMA_NUM_PREDICT=768`, then restart the API. If the model is unavailable, chat returns an error without saving a partial turn. OpenAPI documentation is served at http://localhost:8000/docs.

The UI uses `POST /api/chat/sessions/{id}/messages/stream`, which emits newline-delimited JSON events (`status`, `content`, `complete`, or `error`). Raw model reasoning is never sent to the UI. Only a completed answer is saved. `GET /api/chat/sessions` and `GET /api/chat/sessions/{id}/messages` restore past conversations. Uploaded document text is chunked in SQLite and retrieved by keyword for each question; older uploads are indexed at startup.

`DELETE /api/chat/sessions/{id}` removes a conversation, its messages, related actions/reminders, and linked audit entries. `DELETE /api/documents/{id}` removes only the uploaded document and its search chunks; existing chat messages, saved source snapshots, actions, and reminders remain unchanged. Both return 204 on success or 404 if the ID does not exist.

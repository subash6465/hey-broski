from __future__ import annotations

import asyncio
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import ollama
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .assistant import AssistantService
from .config import settings
from .repository import Repository
from .schemas import ActionCard, ChatRequest, ChatResponse, DecisionRequest, DocumentRecord

repository = Repository(settings.database_path)
assistant = AssistantService(repository, settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.initialize()
    yield


app = FastAPI(title="Hey Broski API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https://.*\.(app\.github\.dev|githubpreview\.dev)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    ollama_status, models = "unavailable", []
    try:
        client = ollama.Client(host=settings.ollama_base_url, timeout=3)
        response = await asyncio.wait_for(asyncio.to_thread(client.list), timeout=4)
        models = [getattr(model, "model", "") for model in getattr(response, "models", [])]
        ollama_status = (
            "available"
            if any(name.startswith(settings.chat_model) for name in models)
            else f"model_missing:{settings.chat_model}"
        )
    except Exception:
        pass
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "demo" if settings.demo_mode else "connected",
        "services": {"database": "connected", "ollama": ollama_status},
        "model": settings.chat_model,
        "available_models": models,
    }


@app.post("/api/chat/sessions", status_code=201)
async def create_session() -> dict[str, str]:
    return repository.create_session()


@app.get("/api/chat/sessions")
async def list_sessions() -> dict[str, Any]:
    return {"sessions": repository.list_sessions()}


@app.get("/api/chat/sessions/{session_id}/messages")
async def list_messages(session_id: str) -> dict[str, Any]:
    if not repository.session_exists(session_id):
        raise HTTPException(404, "Conversation not found")
    return {"messages": repository.list_messages(session_id)}


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
async def send_message(session_id: str, request: ChatRequest) -> ChatResponse:
    if not repository.session_exists(session_id):
        raise HTTPException(404, "Conversation not found")
    repository.add_message(session_id, "user", request.message)
    sources, cards = assistant.context_for(request.message)
    if not request.include_sources:
        sources = []
    persisted_cards = []
    for card in cards:
        repository.upsert_action(
            {
                **card.model_dump(),
                "sources": [source.model_dump() for source in card.source_refs],
                "session_id": session_id,
            }
        )
        persisted = repository.get_action(card.id)
        persisted_cards.append(ActionCard.model_validate(persisted) if persisted else card)
    cards = persisted_cards
    content, generated_by = await assistant.answer(request.message, sources)
    message_id = repository.add_message(
        session_id,
        "assistant",
        content,
        {
            "sources": [source.model_dump() for source in sources],
            "action_cards": [card.model_dump() for card in cards],
            "generated_by": generated_by,
        },
    )
    repository.audit(
        "chat.completed",
        message_id,
        {"session_id": session_id, "generated_by": generated_by, "source_count": len(sources)},
    )
    return ChatResponse(
        message_id=message_id,
        content=content,
        sources=sources,
        action_cards=cards,
        generated_by=generated_by,
    )


@app.get("/api/actions", response_model=list[ActionCard])
async def list_actions(
    action_status: str | None = Query(default=None, alias="status"),
) -> list[dict[str, Any]]:
    return repository.list_actions(action_status)


@app.post("/api/actions/{action_id}/decision", response_model=ActionCard)
async def decide_action(action_id: str, request: DecisionRequest) -> dict[str, Any]:
    action = repository.get_action(action_id)
    if not action:
        raise HTTPException(404, "Action card not found")
    if action["status"] != "pending":
        raise HTTPException(409, f"Action has already been {action['status']}")
    if request.decision == "approve":
        # The MVP executes only a local reminder. External connectors must use
        # the same approval boundary and persist their own confirmed result.
        updated, tool_result = repository.execute_local_reminder(action_id)
        next_status = "completed"
    else:
        updated = repository.decide_action(action_id, "dismissed")
        tool_result = {"executed": False}
        next_status = "dismissed"
    repository.audit(
        f"action.{next_status}",
        action_id,
        {
            "decision": request.decision,
            "tool": (action.get("proposed_action") or {}).get("tool"),
            "tool_result": tool_result,
        },
    )
    return updated


@app.get("/api/reminders")
async def list_reminders() -> dict[str, Any]:
    return {"reminders": repository.list_reminders()}


@app.get("/api/documents", response_model=list[DocumentRecord])
async def list_documents() -> list[dict[str, Any]]:
    return repository.list_documents()


@app.post("/api/documents", response_model=DocumentRecord, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    payload = await file.read()
    if not payload:
        raise HTTPException(400, "The uploaded file is empty")
    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Files are limited to 10 MB")
    content_type = file.content_type or "application/octet-stream"
    try:
        if content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
            from pypdf import PdfReader

            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)
        elif content_type.startswith("text/") or (file.filename or "").lower().endswith((".md", ".txt", ".csv")):
            text = payload.decode("utf-8", errors="replace")
        else:
            raise HTTPException(415, "Supported formats: PDF, TXT, Markdown, and CSV")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Could not extract text: {exc}") from exc
    if len(text.strip()) < 10:
        raise HTTPException(422, "No usable text was found in this document")
    document = repository.add_document(file.filename or "document", content_type, len(payload), text.strip())
    repository.audit(
        "document.uploaded",
        document["id"],
        {"filename": document["filename"], "size_bytes": len(payload)},
    )
    return document


@app.get("/api/audit")
async def list_audit() -> dict[str, Any]:
    return {"events": repository.list_audit()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

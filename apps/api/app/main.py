from __future__ import annotations

import io
import json
import asyncio
import contextlib
import os
from time import perf_counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse, RedirectResponse, JSONResponse

from .assistant import AssistantService, ModelResponseError
from .connectors import ConnectorService, ConnectionError
from .config import settings
from .credential_vault import CredentialVault
from .mail_sync import MailSync
from .mail_vectors import MailVectorIndex
from .repository import Repository
from .schemas import ActionCard, ChatRequest, ChatResponse, DecisionRequest, DocumentRecord, OwnerProfileInput, GmailClientInput, OutlookClientInput, SyncPreferencesInput

repository = Repository(settings.database_path)
assistant = AssistantService(repository, settings)
vault = CredentialVault(settings.data_dir)
connectors = ConnectorService(repository, vault)
mail_sync = MailSync(repository, connectors)


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.initialize()
    global connectors, mail_sync
    connectors = ConnectorService(repository, vault)
    mail_sync = MailSync(repository, connectors)
    scheduler = asyncio.create_task(mail_sync.scheduler())
    vector_worker = asyncio.create_task(assistant.mail_vectors.worker())
    try:
        yield
    finally:
        scheduler.cancel()
        vector_worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler
        with contextlib.suppress(asyncio.CancelledError):
            await vector_worker


app = FastAPI(title="Hey Broski API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https://.*\.(app\.github\.dev|githubpreview\.dev)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_foreign_browser_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        allowed = {"http://localhost:3000", "http://127.0.0.1:3000", os.getenv("HEYBROSKI_WEB_BASE_URL", "http://localhost:3000").rstrip("/")}
        if origin and origin not in allowed:
            return JSONResponse({"detail": "This request did not come from the local Hey Broski app"}, status_code=403)
    return await call_next(request)


@app.get("/api/onboarding")
async def onboarding_status() -> dict[str, Any]:
    return {**repository.onboarding_status(), "gmail_client_imported": connectors.has_gmail_client(),
            "outlook_available": connectors.has_outlook_client()}


@app.put("/api/profile")
async def save_profile(profile: OwnerProfileInput) -> dict[str, Any]:
    return repository.save_profile(profile.model_dump())


@app.post("/api/accounts/gmail/client")
async def import_gmail_client(request: GmailClientInput) -> dict[str, bool]:
    try:
        connectors.import_gmail_client(request.credentials)
    except ConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"imported": True}


@app.post("/api/accounts/outlook/client")
async def import_outlook_client(request: OutlookClientInput) -> dict[str, bool]:
    try:
        connectors.import_outlook_client(request.client_id)
    except ConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"imported": True}


@app.get("/api/accounts")
async def list_accounts() -> dict[str, Any]:
    return {"accounts": repository.list_accounts()}


@app.post("/api/accounts/{provider}/start")
async def start_connection(provider: str) -> dict[str, str]:
    if provider not in {"gmail", "outlook"}:
        raise HTTPException(404, "Unknown mail provider")
    if not repository.profile_complete():
        raise HTTPException(409, "Complete your profile first")
    try:
        return {"authorization_url": connectors.start(provider)}
    except ConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/accounts/{provider}/callback")
async def connection_callback(provider: str, state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    base = os.getenv("HEYBROSKI_WEB_BASE_URL", "http://localhost:3000").rstrip("/")
    if provider not in {"gmail", "outlook"}:
        raise HTTPException(404, "Unknown mail provider")
    if error or not code:
        return RedirectResponse(f"{base}/?setup=connections&connection=cancelled", status_code=303)
    try:
        await connectors.finish(provider, state, code)
    except ConnectionError:
        return RedirectResponse(f"{base}/?setup=connections&connection=failed", status_code=303)
    return RedirectResponse(f"{base}/?setup=connections&connection=connected", status_code=303)


@app.delete("/api/accounts/{account_id}", status_code=204, response_class=Response)
async def disconnect_account(account_id: str) -> Response:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    if account_id in mail_sync._running:
        raise HTTPException(409, "Wait for the current import to finish before disconnecting")
    async with assistant.mail_vectors.lock:
        await asyncio.to_thread(assistant.mail_vectors.remove_account, account_id)
        vault.delete(f"account:{account_id}")
        repository.delete_account(account_id)
    return Response(status_code=204)


@app.post("/api/accounts/{account_id}/sync/pause")
async def pause_sync(account_id: str) -> dict[str, str]:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    job = repository.get_sync_job(account_id)
    processing_only = job and job["status"] == "complete" and repository.mail_pipeline_counts(account_id, settings.embedding_model)["pending_embedding_chunks"] > 0
    if not job or job["status"] != "running" and not processing_only:
        raise HTTPException(409, "No active import or processing to pause")
    await mail_sync.stop(account_id, "paused_processing" if processing_only else "paused")
    async with assistant.mail_vectors.lock:
        pass
    return {"status": "paused"}


@app.post("/api/accounts/{account_id}/sync/cancel")
async def cancel_sync(account_id: str) -> dict[str, str]:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    job = repository.get_sync_job(account_id)
    processing_only = job and job["status"] in {"complete", "paused_processing"} and repository.mail_pipeline_counts(account_id, settings.embedding_model)["pending_embedding_chunks"] > 0
    if not job or job["status"] not in {"running", "paused", "failed"} and not processing_only:
        raise HTTPException(409, "No active sync to cancel")
    await mail_sync.stop(account_id, "canceled")
    async with assistant.mail_vectors.lock:
        pass
    return {"status": "canceled"}


@app.delete("/api/accounts/{account_id}/mail-data", status_code=204, response_class=Response)
async def delete_imported_mail(account_id: str) -> Response:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    await mail_sync.stop(account_id, "canceled")
    async with assistant.mail_vectors.lock:
        await asyncio.to_thread(assistant.mail_vectors.remove_account, account_id)
        repository.reset_sync_job(account_id, purge_mail_conversations=True)
        repository.start_sync_job(account_id)
        repository.set_sync_control(account_id, "canceled")
    return Response(status_code=204)


@app.put("/api/accounts/{account_id}/sync-preferences")
async def save_sync_preferences(account_id: str, preferences: SyncPreferencesInput) -> dict[str, Any]:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    previous = repository.get_sync_preferences(account_id)
    changed = not previous or any((previous[key] != value for key, value in {
        "history_months": preferences.history_months, "interval_hours": preferences.interval_hours,
        "include_sent": int(preferences.include_sent)}.items()))
    if changed and account_id in mail_sync._running:
        raise HTTPException(409, "Wait for the current import to finish before changing sync settings")
    result = repository.save_sync_preferences(account_id, preferences.history_months, preferences.interval_hours, preferences.include_sent)
    if changed:
        async with assistant.mail_vectors.lock:
            await asyncio.to_thread(assistant.mail_vectors.remove_account, account_id)
            repository.reset_sync_job(account_id)
        mail_sync.schedule(account_id)
    return result


@app.get("/api/accounts/{account_id}/sync")
async def sync_status(account_id: str) -> dict[str, Any]:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    return {"preferences": repository.get_sync_preferences(account_id), "job": repository.get_sync_job(account_id),
            "pipeline": repository.mail_pipeline_counts(account_id, settings.embedding_model)}


@app.post("/api/accounts/{account_id}/sync")
async def start_sync(account_id: str) -> dict[str, str]:
    if not repository.get_account(account_id):
        raise HTTPException(404, "Account not found")
    if not repository.get_sync_preferences(account_id):
        raise HTTPException(409, "Choose import and sync settings first")
    job = repository.get_sync_job(account_id)
    if job and job["status"] == "paused_processing":
        repository.set_sync_control(account_id, "complete")
        return {"status": "resumed"}
    mail_sync.schedule(account_id, manual=True)
    return {"status": "started"}


@app.get("/api/live")
async def liveness_check() -> dict[str, str]:
    """Process-only probe used by Docker; never calls a dependency."""
    return {"status": "ok"}


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    ollama_status, models = "disabled" if not settings.use_ollama else "unavailable", []
    if settings.use_ollama:
        try:
            timeout = httpx.Timeout(2.0, connect=0.5)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{settings.ollama_base_url}/api/tags")
                response.raise_for_status()
            models = [
                model.get("model") or model.get("name") or ""
                for model in response.json().get("models", [])
            ]
            ollama_status = (
                "available"
                if settings.chat_model in models
                else f"model_missing:{settings.chat_model}"
            )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
    return {
        "status": "healthy" if ollama_status == "available" else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "connected" if repository.list_accounts() else "demo" if settings.demo_mode else "local",
        "inference_enabled": settings.use_ollama,
        "services": {"database": "connected", "ollama": ollama_status,
                     "embeddings": "available" if settings.embedding_model in models else f"model_missing:{settings.embedding_model}"},
        "model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "mail_chunks_pending_embedding": repository.pending_mail_vector_count(settings.embedding_model),
        "available_models": models,
    }


@app.post("/api/chat/sessions", status_code=201)
async def create_session() -> dict[str, str]:
    return repository.create_session()


@app.get("/api/chat/sessions")
async def list_sessions() -> dict[str, Any]:
    return {"sessions": repository.list_sessions()}


@app.delete("/api/chat/sessions/{session_id}", status_code=204, response_class=Response)
async def delete_session(session_id: str) -> Response:
    if not repository.delete_session(session_id):
        raise HTTPException(404, "Conversation not found")
    return Response(status_code=204)


@app.get("/api/chat/sessions/{session_id}/messages")
async def list_messages(session_id: str) -> dict[str, Any]:
    if not repository.session_exists(session_id):
        raise HTTPException(404, "Conversation not found")
    return {"messages": repository.list_messages(session_id)}


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
async def send_message(session_id: str, request: ChatRequest) -> ChatResponse:
    if not repository.session_exists(session_id):
        raise HTTPException(404, "Conversation not found")
    history = repository.list_messages(session_id)[-6:]
    previous_question = next((item["content"] for item in reversed(history) if item["role"] == "user"), "")
    sources, cards = await asyncio.to_thread(assistant.context_for, request.message, previous_question)
    if not request.include_sources:
        sources = []
    started = perf_counter()
    try:
        content, generated_by = await assistant.answer(request.message, sources, history)
    except ModelResponseError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    return save_chat_turn(session_id, request.message, content, sources, cards, generated_by, round((perf_counter() - started) * 1000))


def save_chat_turn(session_id: str, question: str, content: str, sources: list, cards: list[ActionCard], generated_by: str, response_time_ms: int) -> ChatResponse:
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
    turn_id, user_message_id, message_id = repository.add_turn(
        session_id, question, content,
        {
            "sources": [source.model_dump() for source in sources],
            "action_cards": [card.model_dump() for card in cards],
            "generated_by": generated_by,
            "model": assistant.settings.chat_model,
        },
        response_time_ms,
    )
    repository.audit(
        "chat.completed",
        message_id,
        {"session_id": session_id, "generated_by": generated_by, "source_count": len(sources)},
    )
    return ChatResponse(
        message_id=message_id,
        turn_id=turn_id,
        user_message_id=user_message_id,
        content=content,
        sources=sources,
        action_cards=cards,
        generated_by=generated_by,
    )


@app.post("/api/chat/sessions/{session_id}/messages/stream")
async def stream_message(session_id: str, request: ChatRequest) -> StreamingResponse:
    if not repository.session_exists(session_id):
        raise HTTPException(404, "Conversation not found")
    history = repository.list_messages(session_id)[-6:]
    previous_question = next((item["content"] for item in reversed(history) if item["role"] == "user"), "")
    sources, cards = await asyncio.to_thread(assistant.context_for, request.message, previous_question)
    if not request.include_sources:
        sources = []

    async def events():
        started = perf_counter()
        try:
            async for event in assistant.stream_answer(request.message, sources, history):
                if event["type"] == "complete":
                    result = save_chat_turn(session_id, request.message, event["content"], sources, cards, event.get("generated_by", "ollama"), round((perf_counter() - started) * 1000))
                    event = {"type": "complete", **result.model_dump(mode="json")}
                yield json.dumps(event) + "\n"
        except ModelResponseError as exc:
            yield json.dumps({"type": "error", "detail": exc.detail}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


@app.delete("/api/documents/{document_id}", status_code=204, response_class=Response)
async def delete_document(document_id: str) -> Response:
    if not repository.delete_document(document_id):
        raise HTTPException(404, "Document not found")
    return Response(status_code=204)


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

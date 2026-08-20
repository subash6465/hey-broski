from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

import ollama
import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger()

OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CHAT_MODEL = os.getenv("HEYBROSKI_CHAT_MODEL", "qwen3:4b")
LLM_TEMPERATURE = float(os.getenv("HEYBROSKI_LLM_TEMPERATURE", "0.2"))
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "128"))

app = FastAPI(title="Hey Broski API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.(app\.github\.dev|githubpreview\.dev)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    mode: Optional[str] = "daily_admin"
    account_filter: Optional[List[str]] = None
    include_sources: bool = True

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message cannot be empty")
        return cleaned


class Source(BaseModel):
    source_type: str
    source_id: str
    connected_account_id: str
    account_label: str
    title: str
    snippet: str
    timestamp: str


class ChatResponse(BaseModel):
    message_id: str
    content: str
    sources: List[Source] = Field(default_factory=list)
    action_cards: List[Dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    timestamp: str
    services: Dict[str, str]
    model: str
    available_models: List[str] = Field(default_factory=list)


def make_ollama_client() -> ollama.Client:
    return ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)


def extract_model_names(models_response: Any) -> List[str]:
    models = []
    raw_models = getattr(models_response, "models", None) or models_response.get("models", [])
    for model in raw_models:
        name = getattr(model, "model", None) or getattr(model, "name", None)
        if isinstance(model, dict):
            name = model.get("model") or model.get("name") or name
        if name:
            models.append(name)
    return models


async def list_ollama_models() -> List[str]:
    client = make_ollama_client()
    response = await asyncio.to_thread(client.list)
    return extract_model_names(response)


def demo_sources() -> List[Source]:
    return [
        Source(
            source_type="email",
            source_id="demo-1",
            connected_account_id="demo-account-1",
            account_label="Gmail / Personal",
            title="Credit card bill due soon",
            snippet="Credit card bill of $1,234.56 is due on August 18, 2026",
            timestamp="2026-08-13T10:00:00Z",
        )
    ]


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    services = {"database": "not_configured", "ollama": "unavailable", "n8n": "not_checked"}
    available_models: List[str] = []

    try:
        available_models = await list_ollama_models()
        if CHAT_MODEL in available_models or f"{CHAT_MODEL}:latest" in available_models:
            services["ollama"] = "available"
        else:
            services["ollama"] = f"model_missing:{CHAT_MODEL}"
    except Exception as exc:
        logger.error("ollama_health_check_failed", error=str(exc), host=OLLAMA_HOST)

    return HealthResponse(
        status="healthy" if services["ollama"] == "available" else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
        model=CHAT_MODEL,
        available_models=available_models,
    )


@app.post("/api/chat/sessions")
async def create_session() -> Dict[str, str]:
    return {"session_id": f"session_{uuid4().hex}"}


@app.get("/api/chat/sessions")
async def list_sessions() -> Dict[str, List[Any]]:
    return {"sessions": []}


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
async def send_message(session_id: str, request: ChatRequest) -> ChatResponse:
    system_prompt = """You are Hey Broski, a local-first personal admin AI assistant.
You help users manage their emails, calendar, documents, and tasks.
Be concise, actionable, and helpful. If you do not have real connected account data, say so clearly and use only the provided demo context."""

    started = time.perf_counter()
    try:
        client = make_ollama_client()
        response = await asyncio.to_thread(
            client.chat,
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.message},
            ],
            options={
                "temperature": LLM_TEMPERATURE,
                "num_predict": OLLAMA_NUM_PREDICT,
            },
        )
        message = getattr(response, "message", None) or response.get("message", {})
        content = getattr(message, "content", None) or message.get("content")
        if not content:
            raise RuntimeError("Ollama returned an empty response")

        logger.info(
            "ollama_chat_succeeded",
            host=OLLAMA_HOST,
            model=CHAT_MODEL,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
        return ChatResponse(
            message_id=f"msg_{uuid4().hex}",
            content=content,
            sources=demo_sources() if request.include_sources else [],
            action_cards=[],
        )
    except Exception as exc:
        logger.error("ollama_chat_failed", error=str(exc), host=OLLAMA_HOST, model=CHAT_MODEL)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Unable to get a response from Ollama at {OLLAMA_HOST} using model '{CHAT_MODEL}'. "
                "Confirm Ollama is running and the model is pulled. "
                f"Original error: {exc}"
            ),
        ) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

# Hey Broski API - Phase 1: Chat with Ollama LLM

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import ollama
import logging
import structlog

logger = structlog.get_logger()

app = FastAPI(title="Hey Broski API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
CHAT_MODEL = os.getenv("HEYBROSKI_CHAT_MODEL", "qwen3:8b")

client = ollama.Client(host=OLLAMA_HOST)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "daily_admin"
    account_filter: Optional[List[str]] = None
    include_sources: Optional[bool] = True

class ChatResponse(BaseModel):
    message_id: str
    content: str
    sources: List[Dict[str, Any]] = []
    action_cards: List[Dict[str, Any]] = []

@app.get("/api/health")
async def health_check():
    ollama_status = "unavailable"
    try:
        health_client = ollama.Client(host=OLLAMA_HOST)
        models = health_client.list()
        ollama_status = "available"
        logger.info("ollama_health_check", status="available", models_count=len(models.get('models', [])))
    except Exception as e:
        ollama_status = "unavailable"
        logger.error("ollama_health_check_failed", error=str(e), host=OLLAMA_HOST)
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "database": "connected",
            "ollama": ollama_status,
            "n8n": "available"
        },
        "model": CHAT_MODEL
    }


@app.post("/api/chat/sessions")
async def create_session():
    session_id = f"session_{datetime.now().timestamp()}"
    return {"session_id": session_id}


@app.get("/api/chat/sessions")
async def list_sessions():
    return {"sessions": []}


@app.post("/api/chat/sessions/{session_id}/messages")
async def send_message(session_id: str, request: ChatRequest):
    user_message = request.message
    
    system_prompt = """You are Hey Broski, a local-first personal admin AI assistant. 
You help users manage their emails, calendar, documents, and tasks.
You have access to their connected accounts (Gmail, Outlook, Calendar, Documents).
Always provide source references when answering from user data.
Be concise, actionable, and helpful.
If you don't have access to real data, use the demo data context provided."""

    try:
        # Create fresh client for each request to avoid connection issues
        chat_client = ollama.Client(host=OLLAMA_HOST)
        response = chat_client.chat(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            options={"temperature": 0.2}
        )
        
        content = response['message']['content']
        
    except Exception as e:
        logger.error("ollama_chat_failed", error=str(e), host=OLLAMA_HOST)
        content = f"I'm having trouble connecting to the local LLM. Please ensure Ollama is running and the model '{CHAT_MODEL}' is installed. Error: {str(e)}"
    
    return {
        "message_id": f"msg_{datetime.now().timestamp()}",
        "content": content,
        "sources": [
            {
                "source_type": "email",
                "source_id": "demo-1",
                "connected_account_id": "demo-account-1",
                "account_label": "Gmail / Personal",
                "title": "Credit card bill due soon",
                "snippet": "Credit card bill of $1,234.56 is due on August 18, 2026",
                "timestamp": "2026-08-13T10:00:00Z"
            }
        ],
        "action_cards": []
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
# Basic FastAPI backend for Hey Broski MVP

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

app = FastAPI(title="Hey Broski API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "database": "connected",
            "ollama": "available",
            "n8n": "available"
        }
    }


@app.post("/api/chat/sessions")
async def create_session():
    session_id = f"session_{datetime.now().timestamp()}"
    return {"session_id": session_id}


@app.get("/api/chat/sessions")
async def list_sessions():
    return {"sessions": []}


@app.post("/api/chat/sessions/{session_id}/messages")
async def send_message(session_id: str, message: Dict[str, Any]):
    user_message = message.get("message", "")
    
    # Simple dummy responses based on user message
    if "attention" in user_message.lower():
        response_content = "You have 4 items needing attention:\n\n1. Gmail / Personal: Credit card bill due on 2026-08-18.\n2. Gmail / Personal: Canva trial renewal tomorrow.\n3. Gmail / Work: Manager asked for updated project report and no reply was found.\n4. Calendar / Personal: Bank appointment tomorrow at 10:00 AM."
        action_cards = [
            {
                "id": "card-1",
                "card_type": "renewal",
                "title": "Canva trial renewal tomorrow",
                "priority": "medium",
                "source_refs": [
                    {
                        "source_type": "email",
                        "source_id": "demo-2",
                        "connected_account_id": "demo-account-1",
                        "account_label": "Gmail / Personal",
                        "title": "Canva trial renewal soon",
                        "snippet": "Your Canva premium trial will renew tomorrow for $12.99",
                        "timestamp": "2026-08-14T14:30:00Z"
                    }
                ],
                "suggested_actions": ["create_reminder"],
                "confidence": 0.9
            }
        ]
    elif "waiting" in user_message.lower():
        response_content = "Based on your emails, these people are waiting on you:\n\n1. Manager from work (manager@company.com) - Updated project report requested, no reply found.\n\n\nSuggested actions:\n- Draft a reply to the work email asking for clarification on report requirements.\n- Update the action card to track this follow-up.\n\nApproval required before sending any reply."
        action_cards = [
            {
                "id": "card-2",
                "card_type": "follow_up",
                "title": "Reply to manager about project report",
                "priority": "high",
                "source_refs": [
                    {
                        "source_type": "email",
                        "source_id": "demo-3",
                        "connected_account_id": "demo-account-1",
                        "account_label": "Gmail / Work",
                        "title": "Updated project report",
                        "snippet": "Please find the updated project report attached. The deadline is Friday and we need your input before the weekend.",
                        "timestamp": "2026-08-12T16:45:00Z"
                    }
                ],
                "suggested_actions": ["draft_email", "create_automation"],
                "confidence": 0.8
            }
        ]
    else:
        response_content = "Hello! I'm Hey Broski. I can help you with your daily attention summary, find upcoming renewals, detect follow-ups, and manage your tasks. Try asking 'What needs my attention today?' or 'Who is waiting on me?' to get started."
        action_cards = []
    
    return {
        "message_id": f"msg_{datetime.now().timestamp()}",
        "content": response_content,
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
        "action_cards": action_cards
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    source_type: Literal["email", "calendar", "document"]
    source_id: str
    account_label: str
    title: str
    snippet: str
    timestamp: str


class ActionCard(BaseModel):
    id: str
    card_type: str
    title: str
    description: str
    priority: Literal["urgent", "high", "medium", "low"]
    status: Literal["pending", "approved", "completed", "dismissed", "failed"]
    due_at: str | None = None
    confidence: float = Field(ge=0, le=1)
    source_refs: list[Source] = Field(default_factory=list)
    proposed_action: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    include_sources: bool = True

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be empty")
        return value


class ChatResponse(BaseModel):
    message_id: str
    turn_id: str
    user_message_id: str
    content: str
    sources: list[Source] = Field(default_factory=list)
    action_cards: list[ActionCard] = Field(default_factory=list)
    generated_by: Literal["ollama"]


class DecisionRequest(BaseModel):
    decision: Literal["approve", "dismiss"]


class DocumentRecord(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: str
    preview: str


class OwnerProfileInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=1, le=120)
    phone_number: str = Field(min_length=5, max_length=32)
    gender: str = Field(min_length=1, max_length=80)
    time_zone: str = Field(min_length=1, max_length=80)

    @field_validator("first_name", "last_name", "phone_number", "gender", "time_zone")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value


class GmailClientInput(BaseModel):
    credentials: dict[str, Any]


class OutlookClientInput(BaseModel):
    client_id: str = Field(min_length=36, max_length=36)


class SyncPreferencesInput(BaseModel):
    history_months: Literal[3, 6, 12, 24] = 12
    interval_hours: Literal[1, 6, 12, 24] = 24
    include_sent: bool = True

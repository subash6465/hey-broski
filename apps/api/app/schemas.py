from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class Source(BaseModel):
    source_type: Literal["email", "calendar", "document"]
    source_id: str
    account_label: str
    title: str
    snippet: str
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    generated_by: Literal["ollama", "metadata", "coverage"]


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
    date_of_birth: date
    country_code: str = Field(min_length=2, max_length=5)
    phone_number: str = Field(min_length=4, max_length=15)
    gender: str = Field(min_length=1, max_length=80)
    time_zone: str = Field(min_length=1, max_length=80)

    @field_validator("first_name", "last_name", "country_code", "phone_number", "gender", "time_zone")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value

    @model_validator(mode="after")
    def validate_profile(self) -> "OwnerProfileInput":
        if not re.fullmatch(r"\+[1-9][0-9]{0,3}", self.country_code):
            raise ValueError("Enter a country calling code such as +91")
        if not self.phone_number.isascii() or not self.phone_number.isdigit():
            raise ValueError("Enter the phone number using digits only")
        if len(self.country_code) - 1 + len(self.phone_number) > 15:
            raise ValueError("The complete phone number must have at most 15 digits")
        try:
            today = datetime.now(ZoneInfo(self.time_zone)).date()
        except ZoneInfoNotFoundError:
            # Windows may have no IANA zone database until tzdata is installed.
            # The local app runs on the same computer as the browser.
            today = datetime.now().date()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        if age < 0 or age > 120:
            raise ValueError("Enter a valid date of birth")
        return self


class GmailClientInput(BaseModel):
    credentials: dict[str, Any]


class OutlookClientInput(BaseModel):
    client_id: str = Field(min_length=36, max_length=36)


class SyncPreferencesInput(BaseModel):
    history_months: Literal[3, 6, 12, 24] = 12
    interval_hours: Literal[1, 6, 12, 24] = 24
    include_sent: bool = True

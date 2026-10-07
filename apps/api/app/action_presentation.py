"""Consistent titles and conservative priority overrides for action cards."""

from __future__ import annotations

import re
from datetime import datetime, timezone


GERUNDS = {
    "sharing": "Share", "filing": "File", "paying": "Pay", "renewing": "Renew",
    "submitting": "Submit", "reviewing": "Review", "booking": "Book", "completing": "Complete",
    "responding": "Respond", "updating": "Update", "scheduling": "Schedule",
}


def action_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title).strip().rstrip(".")
    first, _, rest = cleaned.partition(" ")
    if first.lower() in GERUNDS and rest:
        return f"{GERUNDS[first.lower()]} {rest}"[:160]
    return cleaned[:160]


def action_priority(title: str, description: str, due_at: str | None, suggested: str = "medium") -> str:
    text = f"{title} {description}".lower()
    # Optional feedback and social invitations should not crowd out obligations.
    optional = bool(re.search(r"\b(dining experience|restaurant review|share (?:your )?feedback|survey|rate your|review your visit|eazypoints|loyalty points|refer friends|refer family|referral reward)\b", text))
    required = bool(re.search(r"\b(itr|income tax|tax return|tax filing|file taxes|tax deadline|insurance premium|bill payment|credit card bill|invoice due|legal notice|compliance|kyc)\b", text))
    if optional:
        return "low"
    if required:
        return "high"
    if due_at:
        try:
            days = (datetime.fromisoformat(due_at.replace("Z", "+00:00")).astimezone(timezone.utc).date()
                    - datetime.now(timezone.utc).date()).days
            if 0 <= days <= 2 and suggested in {"high", "urgent"}:
                return "urgent"
            if 0 <= days <= 7 and suggested in {"medium", "high", "urgent"}:
                return "high"
            if days < 0 and suggested == "urgent":
                return "high"
        except ValueError:
            pass
    return suggested if suggested in {"urgent", "high", "medium", "low"} else "medium"

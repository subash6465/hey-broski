from __future__ import annotations

import asyncio
import re

import ollama
import httpx
import structlog

from .config import Settings
from .demo_data import DEMO_SOURCES
from .repository import Repository
from .schemas import ActionCard, Source

logger = structlog.get_logger()


class AssistantService:
    def __init__(self, repository: Repository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def context_for(self, message: str) -> tuple[list[Source], list[ActionCard]]:
        query = message.lower()
        if not self.settings.demo_mode:
            selected = []
        elif any(word in query for word in ("wait", "reply", "follow")):
            selected = [DEMO_SOURCES[1]]
        elif any(word in query for word in ("renew", "deadline", "due", "expir", "warranty")):
            selected = [DEMO_SOURCES[i] for i in (0, 2, 5)]
        elif any(word in query for word in ("calendar", "meeting", "conflict")):
            selected = [DEMO_SOURCES[i] for i in (3, 4)]
        elif any(word in query for word in ("email", "unread", "inbox")):
            selected = [DEMO_SOURCES[i] for i in (0, 1, 5)]
        else:
            selected = list(DEMO_SOURCES)
        terms = [term for term in re.findall(r"[a-z0-9]{3,}", query) if term not in {"what", "when", "that", "this", "with", "from", "about", "find", "show"}]
        for document in self.repository.search_documents(terms):
            selected.append(Source(source_type="document", source_id=document["id"], account_label="Document vault", title=document["filename"], snippet=document["extracted_text"][:220], timestamp=document["created_at"]))
        actionable = {"email-card-bill", "email-manager-report", "doc-headphones-warranty", "event-design-review", "email-canva-renewal"}
        return selected, [self._card_for(source) for source in selected if source.source_id in actionable]

    def _card_for(self, source: Source) -> ActionCard:
        definitions = {
            "email-card-bill": ("Pay credit card bill", "₹12,450 is due soon.", "high", "2026-09-25T23:59:00Z"),
            "email-manager-report": ("Reply with the Q3 project update", "Your manager requested the revised update.", "high", "2026-09-23T17:00:00Z"),
            "doc-headphones-warranty": ("Review headphones warranty", "The warranty expires this month.", "medium", "2026-09-30T23:59:00Z"),
            "event-design-review": ("Resolve calendar conflict", "Design review overlaps the client check-in.", "high", "2026-09-23T10:00:00Z"),
            "email-canva-renewal": ("Review Canva renewal", "The trial will convert to a paid subscription.", "medium", "2026-09-27T00:00:00Z"),
        }
        title, description, priority, due_at = definitions[source.source_id]
        return ActionCard(id=f"action_{source.source_id}", card_type="reminder" if source.source_type != "calendar" else "calendar_conflict", title=title, description=description, priority=priority, status="pending", due_at=due_at, confidence=0.94, source_refs=[source], proposed_action={"tool": "reminders.create", "requires_approval": True, "input": {"title": title, "due_at": due_at}})

    @staticmethod
    def deterministic_answer(sources: list[Source]) -> str:
        if not sources:
            return "I couldn't find a matching item in your local data. Upload a document or try a broader question."
        lines = [f"I found {len(sources)} item{'s' if len(sources) != 1 else ''} needing your attention:", ""]
        lines.extend(f"{index}. {source.account_label}: {source.snippet} [Source {index}]" for index, source in enumerate(sources, 1))
        lines += ["", "Suggested actions are shown below. Nothing will be executed without your approval."]
        return "\n".join(lines)

    async def answer(self, message: str, sources: list[Source]) -> tuple[str, str]:
        fallback = self.deterministic_answer(sources)
        context = "\n".join(f"[Source {i}] {s.account_label} — {s.title}: {s.snippet}" for i, s in enumerate(sources, 1))
        prompt = f"Answer using only these sources. Cite every fact as [Source N]. Never claim an action occurred. End by saying approval is required for suggested actions.\n\nQuestion: {message}\n\n{context}"
        try:
            # Do a short availability/model check first. A missing Ollama model
            # must never hold the otherwise complete demo response for minutes.
            timeout = httpx.Timeout(2.0, connect=0.5)
            async with httpx.AsyncClient(timeout=timeout) as client:
                model_response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                model_response.raise_for_status()
            model_names = [
                model.get("model") or model.get("name") or ""
                for model in model_response.json().get("models", [])
            ]
            if not any(name == self.settings.chat_model or name.startswith(f"{self.settings.chat_model}:") for name in model_names):
                logger.info("ollama_model_missing_using_demo_answer", model=self.settings.chat_model)
                return fallback, "demo"

            client = ollama.Client(
                host=self.settings.ollama_base_url,
                timeout=self.settings.ollama_timeout_seconds,
            )
            response = await asyncio.to_thread(client.chat, model=self.settings.chat_model, messages=[{"role": "system", "content": "You are Hey Broski, a concise local-first personal admin assistant."}, {"role": "user", "content": prompt}], options={"temperature": self.settings.llm_temperature, "num_predict": 400})
            content = getattr(getattr(response, "message", None), "content", None)
            if content:
                return content.strip(), "ollama"
        except Exception as exc:
            logger.warning("ollama_unavailable_using_demo_answer", error=str(exc))
        return fallback, "demo"

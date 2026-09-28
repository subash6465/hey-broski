from __future__ import annotations

import re

import httpx
import structlog

from .config import Settings
from .demo_data import DEMO_SOURCES
from .repository import Repository
from .schemas import ActionCard, Source

logger = structlog.get_logger()


class ModelResponseError(Exception):
    def __init__(self, detail: str, status_code: int = 503) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


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

    async def answer(self, message: str, sources: list[Source]) -> tuple[str, str]:
        if not self.settings.use_ollama:
            raise ModelResponseError("Local model inference is disabled. Set HEYBROSKI_USE_OLLAMA=true and restart the API.")

        context = "\n".join(f"[Source {i}] {s.account_label} — {s.title}: {s.snippet}" for i, s in enumerate(sources, 1))
        prompt = (
            "Answer using only the provided sources. Cite every source-based fact as [Source N]. "
            "If no sources are provided, say you could not find supporting information; do not invent facts. "
            "Never claim an action occurred. End by saying approval is required for suggested actions."
            f"\n\nQuestion: {message}\n\nSources:\n{context or '(none)'}"
        )
        try:
            timeout = httpx.Timeout(self.settings.ollama_timeout_seconds, connect=2.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/chat",
                    json={
                        "model": self.settings.chat_model,
                        "messages": [
                            {"role": "system", "content": "You are Hey Broski, a concise local-first personal admin assistant."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "think": False,
                        "keep_alive": "5m",
                        "options": {
                            "temperature": self.settings.llm_temperature,
                            "num_ctx": 4096,
                            "num_predict": self.settings.ollama_num_predict,
                        },
                    },
                )
                response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            if content:
                return content, "ollama"
            logger.warning("ollama_empty_answer", model=self.settings.chat_model)
            raise ModelResponseError("The local model returned an empty answer. Please retry.", 502)
        except httpx.TimeoutException as exc:
            logger.warning("ollama_timeout", model=self.settings.chat_model, error=str(exc))
            raise ModelResponseError("The local model timed out. Please retry or use a smaller model.", 504) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("ollama_http_error", model=self.settings.chat_model, status=exc.response.status_code)
            if exc.response.status_code == 404:
                raise ModelResponseError(f"Local model {self.settings.chat_model} is not installed. Check the ollama-model pull job.") from exc
            raise ModelResponseError("The local model could not generate an answer. Check the Ollama logs.", 502) from exc
        except (httpx.RequestError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("ollama_unavailable", model=self.settings.chat_model, error=str(exc))
            raise ModelResponseError("Cannot reach the local model or read its response. Check that Ollama is running.") from exc

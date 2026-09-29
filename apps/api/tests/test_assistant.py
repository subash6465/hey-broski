from datetime import date
from pathlib import Path

from app.assistant import AssistantService
from app.config import Settings
from app.demo_data import DEMO_SOURCES
from app.repository import Repository


def service(tmp_path: Path) -> AssistantService:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    settings = Settings(tmp_path, tmp_path / "test.db", "http://127.0.0.1:1", "qwen3:4b-instruct", 0.2, 0.01, True)
    return AssistantService(repository, settings)


def test_renewal_query_is_grounded_and_actionable(tmp_path: Path) -> None:
    sources, actions = service(tmp_path).context_for("Show renewals and deadlines")

    assert {source.source_id for source in sources} == {
        "email-card-bill", "doc-headphones-warranty", "email-canva-renewal"
    }
    assert all(action.status == "pending" for action in actions)
    assert all(action.proposed_action["requires_approval"] for action in actions if action.proposed_action)


def test_follow_up_reuses_document_from_previous_question(tmp_path: Path) -> None:
    assistant = service(tmp_path)
    assistant.repository.add_document("smoke.txt", "text/plain", 55, "The meeting code is ORCHID-42. The project owner is Ada.")

    sources, _ = assistant.context_for("Who is the project owner?", "What is the code in smoke.txt?")

    assert sources
    assert all(source.source_type == "document" for source in sources)
    assert "Ada" in sources[0].snippet


def test_upcoming_demo_filter_excludes_expired_and_stale_items() -> None:
    today = date(2026, 9, 29)
    week_start = date(2026, 9, 28)

    assert not AssistantService._is_current_demo_source(DEMO_SOURCES[0], today, week_start)
    assert not AssistantService._is_current_demo_source(DEMO_SOURCES[1], today, week_start)
    assert AssistantService._is_current_demo_source(DEMO_SOURCES[2], today, week_start)

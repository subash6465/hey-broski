from pathlib import Path

from app.assistant import AssistantService
from app.config import Settings
from app.repository import Repository


def service(tmp_path: Path) -> AssistantService:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    settings = Settings(tmp_path, tmp_path / "test.db", "http://127.0.0.1:1", "qwen3:8b", 0.2, 0.01, True)
    return AssistantService(repository, settings)


def test_renewal_query_is_grounded_and_actionable(tmp_path: Path) -> None:
    sources, actions = service(tmp_path).context_for("Show renewals and deadlines")

    assert {source.source_id for source in sources} == {
        "email-card-bill", "doc-headphones-warranty", "email-canva-renewal"
    }
    assert all(action.status == "pending" for action in actions)
    assert all(action.proposed_action["requires_approval"] for action in actions if action.proposed_action)


def test_fallback_answer_cites_each_source(tmp_path: Path) -> None:
    assistant = service(tmp_path)
    sources, _ = assistant.context_for("Who is waiting on me?")
    answer = assistant.deterministic_answer(sources)

    assert "[Source 1]" in answer
    assert "Nothing will be executed without your approval" in answer

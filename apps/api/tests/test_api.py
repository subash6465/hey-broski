from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService
from app.repository import Repository


def test_demo_chat_approval_and_audit(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    async def fallback(message, sources):
        return main.assistant.deterministic_answer(sources), "demo"

    monkeypatch.setattr(main.assistant, "answer", fallback)

    with TestClient(main.app) as client:
        assert client.get("/api/live").json() == {"status": "ok"}
        session = client.post("/api/chat/sessions").json()
        response = client.post(
            f"/api/chat/sessions/{session['session_id']}/messages",
            json={"message": "Who is waiting on me?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sources"][0]["source_id"] == "email-manager-report"
        action = body["action_cards"][0]

        decision = client.post(
            f"/api/actions/{action['id']}/decision",
            json={"decision": "approve"},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "completed"
        assert client.get("/api/reminders").json()["reminders"][0]["action_id"] == action["id"]
        assert client.get("/api/audit").json()["events"][0]["event_type"] == "action.completed"


def test_text_document_upload(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("renewal.txt", b"Insurance renewal is due on 15 October 2026.", "text/plain")},
        )

        assert response.status_code == 201
        assert client.get("/api/documents").json()[0]["filename"] == "renewal.txt"

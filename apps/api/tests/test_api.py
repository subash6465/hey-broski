import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService
from app.repository import Repository


@pytest.mark.parametrize("generated_by", ["metadata", "coverage"])
def test_direct_chat_response_and_stream_accept_answer_origin(tmp_path: Path, monkeypatch, generated_by: str) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    async def direct_answer(message, sources, history=None):
        return "Answer from indexed mail.", generated_by

    async def streamed_answer(message, sources, history=None):
        yield {"type": "complete", "content": "Answer from indexed mail.", "generated_by": generated_by}

    monkeypatch.setattr(main.assistant, "answer", direct_answer)
    monkeypatch.setattr(main.assistant, "stream_answer", streamed_answer)
    with TestClient(main.app) as client:
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        direct = client.post(f"/api/chat/sessions/{session_id}/messages", json={"message": "Latest mail?"})
        stream = client.post(f"/api/chat/sessions/{session_id}/messages/stream", json={"message": "Latest mail?"})
        stored = client.get(f"/api/chat/sessions/{session_id}/messages").json()["messages"]

    assert direct.status_code == 200
    assert direct.json()["generated_by"] == generated_by
    assert json.loads(stream.text.splitlines()[-1])["generated_by"] == generated_by
    assert [item["metadata"].get("generated_by") for item in stored if item["role"] == "assistant"] == [generated_by, generated_by]


def test_model_chat_approval_and_audit(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    async def model_answer(message, sources, history=None):
        return "Your manager needs a reply. [Source 1] Approval is required before acting.", "ollama"

    monkeypatch.setattr(main.assistant, "answer", model_answer)

    with TestClient(main.app) as client:
        assert client.get("/api/live").json() == {"status": "ok"}
        session = client.post("/api/chat/sessions").json()
        response = client.post(
            f"/api/chat/sessions/{session['session_id']}/messages",
            json={"message": "Who is waiting on me?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["generated_by"] == "ollama"
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


def test_streamed_chat_is_saved_and_reopened_as_history(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    async def streamed_answer(message, sources, history=None):
        yield {"type": "status", "text": "Checking sources..."}
        yield {"type": "content", "text": "The uploaded policy renews in October. [Source 1]"}
        yield {"type": "complete", "content": "The uploaded policy renews in October. [Source 1]"}

    monkeypatch.setattr(main.assistant, "stream_answer", streamed_answer)
    with TestClient(main.app) as client:
        document = client.post("/api/documents", files={"file": ("policy.txt", b"The uploaded policy renews in October 2026.", "text/plain")}).json()
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        response = client.post(f"/api/chat/sessions/{session_id}/messages/stream", json={"message": "When does policy.txt renew?"})
        events = [json.loads(line) for line in response.text.splitlines()]
        stored = client.get(f"/api/chat/sessions/{session_id}/messages").json()["messages"]
        sessions = client.get("/api/chat/sessions").json()["sessions"]

    assert [event["type"] for event in events] == ["status", "content", "complete"]
    assert events[-1]["sources"][0]["source_id"].startswith(document["id"])
    assert len(stored) == 2
    assert stored[0]["turn_id"] == stored[1]["turn_id"] == events[-1]["turn_id"]
    assert stored[1]["content"] == events[-1]["content"]
    assert stored[1]["response_time_ms"] >= 0
    assert sessions[0]["session_id"] == session_id


def test_failed_stream_does_not_save_partial_turn(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    async def failed_answer(message, sources, history=None):
        yield {"type": "status", "text": "Checking..."}
        raise main.ModelResponseError("The model stopped responding.", 504)

    monkeypatch.setattr(main.assistant, "stream_answer", failed_answer)
    with TestClient(main.app) as client:
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        response = client.post(f"/api/chat/sessions/{session_id}/messages/stream", json={"message": "What is due?"})
        events = [json.loads(line) for line in response.text.splitlines()]
        stored = client.get(f"/api/chat/sessions/{session_id}/messages").json()["messages"]

    assert [event["type"] for event in events] == ["status", "error"]
    assert stored == []


def test_delete_conversation_and_document_endpoints(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.assistant = AssistantService(repository, main.settings)

    with TestClient(main.app) as client:
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        repository.add_turn(session_id, "Question", "Answer", {}, 1)
        document = client.post("/api/documents", files={"file": ("secret.txt", b"The project code is ORCHID-42.", "text/plain")}).json()
        kept_session = client.post("/api/chat/sessions").json()["session_id"]
        repository.add_turn(kept_session, "What is the code?", "It is ORCHID-42.", {
            "sources": [{"source_id": f'{document["id"]}#part-1', "snippet": "The project code is ORCHID-42."}],
        }, 1)

        assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 204
        assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 404
        assert client.get(f"/api/chat/sessions/{session_id}/messages").status_code == 404
        assert client.delete(f'/api/documents/{document["id"]}').status_code == 204
        assert client.delete(f'/api/documents/{document["id"]}').status_code == 404
        assert client.get("/api/documents").json() == []
        saved = client.get(f"/api/chat/sessions/{kept_session}/messages").json()["messages"]
        assert [message["content"] for message in saved] == ["What is the code?", "It is ORCHID-42."]
        assert saved[1]["metadata"]["sources"][0]["source_id"].startswith(document["id"])
        future_sources, _ = main.assistant.context_for("What is in secret.txt?")
        assert all(not source.source_id.startswith(document["id"]) for source in future_sources)

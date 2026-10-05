import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService, ModelResponseError, final_answer
from app.config import Settings
from app.repository import Repository


def assistant(tmp_path: Path) -> AssistantService:
    repository = Repository(tmp_path / "ollama.db")
    repository.initialize()
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "ollama.db",
        ollama_base_url="http://ollama.test:11434",
        chat_model="qwen3:4b-instruct",
        llm_temperature=0.2,
        ollama_timeout_seconds=10,
        demo_mode=True,
        use_ollama=True,
        ollama_num_predict=160,
    )
    return AssistantService(repository, settings)


def test_local_model_is_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("HEYBROSKI_USE_OLLAMA", raising=False)
    monkeypatch.delenv("HEYBROSKI_CHAT_MODEL", raising=False)
    settings = Settings.from_env()

    assert settings.use_ollama is True
    assert settings.chat_model == "qwen3:4b-instruct"


def test_old_output_limit_is_raised_to_avoid_truncated_answers(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "128")
    assert Settings.from_env().ollama_num_predict == 512


def test_final_answer_removes_model_analysis_preamble() -> None:
    assert final_answer("Analysis: I should inspect the source.\n\nFinal answer: ORCHID-42 [Source 1]") == "ORCHID-42 [Source 1]"
    assert final_answer("<think>private reasoning</think>Final answer: The date is 15 October.") == "The date is 15 October."
    assert final_answer("I cannot verify that here. [Source N] is missing.") == "I cannot verify that here."
    assert final_answer("I cannot verify that here. [Source missing]") == "I cannot verify that here."
    with pytest.raises(ModelResponseError, match="reasoning"):
        final_answer("Analysis: I have not answered yet.")


def mock_ollama(monkeypatch, handler) -> None:
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )


def test_local_model_requests_direct_answer(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    sources, _ = service.context_for("Who is waiting on me?")

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["model"] == "qwen3:4b-instruct"
        assert body["stream"] is False
        assert body["think"] is False
        assert body["options"]["num_predict"] == 160
        assert "[Source 1]" in body["messages"][1]["content"]
        return httpx.Response(200, json={"message": {"content": "Your manager is waiting for a reply. [Source 1] Approval is required for actions."}})

    mock_ollama(monkeypatch, respond)
    content, generated_by = asyncio.run(service.answer("Who is waiting on me?", sources))

    assert generated_by == "ollama"
    assert "manager is waiting" in content


def test_stream_hides_model_thinking_and_returns_completed_answer(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    service.settings = replace(service.settings, ollama_num_predict=768)

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["think"] is False
        assert body["options"]["num_predict"] == 768
        chunks = [
            {"message": {"thinking": "Checking the source...", "content": ""}, "done": False},
            {"message": {"thinking": "", "content": "The renewal is due on 15 October. [Source 1]"}, "done": False},
            {"message": {"thinking": "", "content": ""}, "done": True, "done_reason": "stop"},
        ]
        return httpx.Response(200, content="\n".join(json.dumps(chunk) for chunk in chunks) + "\n")

    mock_ollama(monkeypatch, respond)

    async def collect():
        return [event async for event in service.stream_answer("When is the renewal?", [])]

    events = asyncio.run(collect())
    assert [event["type"] for event in events] == ["status", "content", "complete"]
    assert "Checking the source" not in str(events)
    assert events[-1]["content"] == "The renewal is due on 15 October. [Source 1]"
    assert "Checking" not in events[-1]["content"]


def test_stream_rejects_truncated_answer(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    mock_ollama(monkeypatch, lambda request: httpx.Response(200, content=json.dumps({
        "message": {"content": "The renewal is"}, "done": True, "done_reason": "length",
    }) + "\n"))

    async def collect():
        return [event async for event in service.stream_answer("When?", [])]

    with pytest.raises(ModelResponseError, match="answer limit"):
        asyncio.run(collect())


def test_unavailable_model_raises_clear_error(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    sources, _ = service.context_for("Who is waiting on me?")
    mock_ollama(monkeypatch, lambda request: httpx.Response(404, json={"error": "model not found"}))

    with pytest.raises(ModelResponseError, match="not installed") as error:
        asyncio.run(service.answer("Who is waiting on me?", sources))
    assert error.value.status_code == 503


def test_uncited_model_text_still_returns_with_source_metadata(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    sources, _ = service.context_for("Who is waiting on me?")
    mock_ollama(monkeypatch, lambda request: httpx.Response(200, json={"message": {"content": "Someone may need a reply."}}))

    content, generated_by = asyncio.run(service.answer("Who is waiting on me?", sources))
    assert generated_by == "ollama"
    assert content == "Someone may need a reply."


def test_empty_model_answer_is_rejected(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    sources, _ = service.context_for("Who is waiting on me?")
    mock_ollama(monkeypatch, lambda request: httpx.Response(200, json={"message": {"content": ""}}))

    with pytest.raises(ModelResponseError, match="empty") as error:
        asyncio.run(service.answer("Who is waiting on me?", sources))
    assert error.value.status_code == 502


def test_question_without_sources_still_uses_model(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "Sources:\n(none)" in body["messages"][1]["content"]
        return httpx.Response(200, json={"message": {"content": "I could not find supporting information in your vault."}})

    mock_ollama(monkeypatch, respond)
    content, generated_by = asyncio.run(service.answer("What is in my vault?", []))

    assert generated_by == "ollama"
    assert "could not find" in content


def test_disabled_model_fails_instead_of_answering(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    service.settings = replace(service.settings, use_ollama=False)
    sources, _ = service.context_for("Who is waiting on me?")
    mock_ollama(monkeypatch, lambda request: (_ for _ in ()).throw(AssertionError("Ollama should not be called")))

    with pytest.raises(ModelResponseError, match="disabled"):
        asyncio.run(service.answer("Who is waiting on me?", sources))


def test_legacy_thinking_model_has_actionable_error(tmp_path: Path) -> None:
    service = assistant(tmp_path)
    service.settings = replace(service.settings, chat_model="qwen3:4b")

    with pytest.raises(ModelResponseError, match="qwen3:4b-instruct"):
        asyncio.run(service.answer("What is due?", []))


def test_model_timeout_is_reported(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    sources, _ = service.context_for("Who is waiting on me?")

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    mock_ollama(monkeypatch, timeout)
    with pytest.raises(ModelResponseError, match="timed out") as error:
        asyncio.run(service.answer("Who is waiting on me?", sources))
    assert error.value.status_code == 504


def test_chat_endpoint_reports_actual_local_generation(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    monkeypatch.setattr(main, "settings", service.settings)
    monkeypatch.setattr(main, "repository", service.repository)
    monkeypatch.setattr(main, "assistant", service)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b-instruct"}]})
        return httpx.Response(200, json={"message": {"content": "A reply is due. [Source 1] Approval is required before acting."}})

    mock_ollama(monkeypatch, respond)
    with TestClient(main.app) as client:
        health = client.get("/api/health").json()
        assert health["inference_enabled"] is True
        assert health["services"]["ollama"] == "available"
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        reply = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"message": "Who is waiting on me?"},
        )

    assert reply.status_code == 200
    assert reply.json()["generated_by"] == "ollama"
    assert "[Source 1]" in reply.json()["content"]


def test_failed_generation_does_not_save_partial_turn(tmp_path: Path, monkeypatch) -> None:
    service = assistant(tmp_path)
    monkeypatch.setattr(main, "settings", service.settings)
    monkeypatch.setattr(main, "repository", service.repository)
    monkeypatch.setattr(main, "assistant", service)
    mock_ollama(monkeypatch, lambda request: httpx.Response(404, json={"error": "model not found"}))

    with TestClient(main.app) as client:
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        reply = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"message": "Who is waiting on me?"},
        )
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()["messages"]
        actions = client.get("/api/actions").json()

    assert reply.status_code == 503
    assert "not installed" in reply.json()["detail"]
    assert messages == []
    assert actions == []

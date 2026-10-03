"""Evidence-oriented regression cases for the local read-only agent."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService
from app.agent_tools import AgentTools
from app.config import Settings
from app.mail_index import normalize_gmail_message
from app.repository import Repository


def setup_mail(tmp_path: Path) -> tuple[AssistantService, str]:
    repository = Repository(tmp_path / "agent.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    settings = Settings(tmp_path, tmp_path / "agent.db", "http://ollama.test:11434", "qwen3:4b-instruct", 0.0, 10, False)
    return AssistantService(repository, settings), account["id"]


def add_mail(service: AssistantService, account_id: str, message_id: str, subject: str, body: str,
             sender: str, timestamp: int, thread: str | None = None, labels: list[str] | None = None) -> None:
    payload = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    raw = {"id": message_id, "threadId": thread or message_id, "internalDate": str(timestamp),
           "labelIds": labels or ["INBOX"], "payload": {"mimeType": "text/plain", "body": {"data": payload},
           "headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]}}
    service.repository.upsert_mail_message(normalize_gmail_message(raw, account_id, "owner@example.com"))


def test_latest_topical_mail_uses_text_and_date(tmp_path: Path) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "refund", "Refund approved", "Your refund is approved", "Support <help@example.com>", 1780000000000)
    add_mail(service, account_id, "unrelated", "Weekly newsletter", "A new article", "News <news@example.com>", 1780002000000)
    sources, _ = service.context_for("What is my latest email about refund?")
    assert [source.metadata["message_id"] for source in sources] == ["refund"]
    answer, generated_by = asyncio.run(service.answer("What is my latest email about refund?", sources))
    assert generated_by == "metadata"
    assert "Refund approved" in answer


def test_find_in_long_message_reaches_beyond_preview(tmp_path: Path) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "long", "Contract", "intro " * 2000 + "The agreement code is PINE-731.",
             "Alice <alice@example.com>", 1780000000000)
    sources, _ = service.context_for("agreement code")
    tool = AgentTools(service.repository, sources, question="What is the agreement code?")
    result = tool.execute("find_in_message", {"source_number": 1, "query": "PINE-731"})
    assert result["found"] is True
    assert "PINE-731" in result["passages"][0]


def test_exact_metadata_count_does_not_call_model(tmp_path: Path) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "one", "Ticket", "Ticket details", "BookMyShow <tickets@bookmyshow.com>", 1780000000000)
    add_mail(service, account_id, "two", "Ticket", "Ticket details", "BookMyShow <tickets@bookmyshow.com>", 1780001000000)
    add_mail(service, account_id, "three", "Other", "Other details", "Other <other@example.com>", 1780002000000)
    answer, origin = asyncio.run(service.answer("How many emails from book my show?", []))
    assert origin == "metadata"
    assert "2 matching indexed messages" in answer


def test_agent_filters_recipient_attachment_and_account(tmp_path: Path) -> None:
    service, account_id = setup_mail(tmp_path)
    raw = {"id": "invoice", "threadId": "invoice", "internalDate": "1780000000000", "labelIds": ["INBOX"],
           "payload": {"mimeType": "multipart/mixed", "headers": [
               {"name": "From", "value": "Billing <billing@example.com>"},
               {"name": "To", "value": "Owner <owner@example.com>"},
               {"name": "Subject", "value": "May invoice"}], "parts": [
               {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(b"Invoice total is 42").decode()}},
               {"mimeType": "application/pdf", "filename": "may-invoice.pdf", "body": {"attachmentId": "a1", "size": 42}}]}}
    service.repository.upsert_mail_message(normalize_gmail_message(raw, account_id, "owner@example.com"))
    tool = AgentTools(service.repository, [], question="Find may-invoice.pdf sent to owner@example.com")
    args = {"query": "", "recipient": "owner@example.com", "attachment_name": "invoice.pdf",
            "account_email": "owner@example.com"}
    assert tool.execute("search_mail", args)["matches"][0]["subject"] == "May invoice"
    assert service.repository.count_mail_messages(recipient="owner@example.com", attachment_name="invoice.pdf",
                                                  account_email="owner@example.com") == 1
    assert service.repository.search_mail_messages("", recipient="other@example.com", attachment_name="invoice.pdf") == []
    sources, _ = service.context_for("What is the latest mail to owner@example.com?")
    assert [source.metadata["message_id"] for source in sources] == ["invoice"]


def test_agent_opens_thread_and_cites_returned_message(tmp_path: Path, monkeypatch) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "first", "Project Cedar", "Please send the draft", "Alice <alice@example.com>", 1780000000000, "thread-a")
    add_mail(service, account_id, "second", "Re: Project Cedar", "The final deadline is Friday", "Bob <bob@example.com>", 1780001000000, "thread-a")
    sources, _ = service.context_for("What is the deadline in the Project Cedar thread?")
    assert sources
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        body = json.loads(request.content)
        assert body["tools"]
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"message": {"content": "", "tool_calls": [{"type": "function",
                "function": {"name": "open_thread", "arguments": {"source_number": 1}}}]}})
        tool_response = json.loads(body["messages"][-1]["content"])
        assert tool_response["thread_count_indexed"] == 2
        assert any("Friday" in item["body"] for item in tool_response["messages"])
        number = next(item["source"] for item in tool_response["messages"] if "Friday" in item["body"])
        return httpx.Response(200, json={"message": {"content": f"The deadline is Friday. [Source {number}]"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    answer, origin = asyncio.run(service.answer("What is the deadline in the Project Cedar thread?", sources))
    assert origin == "agent"
    assert "Friday" in answer
    assert calls == 2
    assert len(sources) == 2


def test_agent_rejects_invalid_citation(tmp_path: Path, monkeypatch) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "one", "Code", "The code is CEDAR-42", "Alice <alice@example.com>", 1780000000000)
    sources, _ = service.context_for("What is the code?")
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"message": {"content": "", "tool_calls": [{"type": "function",
                "function": {"name": "open_message", "arguments": {"source_number": 1}}}]}})
        return httpx.Response(200, json={"message": {"content": "The code is CEDAR-42. [Source 999]"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    answer, origin = asyncio.run(service.answer("What is the code?", sources))
    assert origin == "agent"
    assert "could not verify" in answer


@pytest.mark.parametrize("stream", [False, True])
def test_chat_api_persists_sources_opened_by_agent(tmp_path: Path, monkeypatch, stream: bool) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "first", "Project Cedar", "Please send the draft", "Alice <alice@example.com>", 1780000000000, "thread-a")
    add_mail(service, account_id, "second", "Re: Project Cedar", "Final deadline is Friday", "Bob <bob@example.com>", 1780001000000, "thread-a")
    assert len(service.context_for("Summarize the draft thread")[0]) == 1
    async def idle_worker():
        await asyncio.Event().wait()
    monkeypatch.setattr(service.mail_vectors, "worker", idle_worker)
    monkeypatch.setattr(main, "repository", service.repository)
    monkeypatch.setattr(main, "assistant", service)
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"message": {"tool_calls": [{"type": "function",
                "function": {"name": "open_thread", "arguments": {"source_number": 1}}}]}})
        return httpx.Response(200, json={"message": {"content": "The deadline is Friday. [Source 2]"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    with TestClient(main.app) as client:
        session_id = client.post("/api/chat/sessions").json()["session_id"]
        response = client.post(f"/api/chat/sessions/{session_id}/messages{'/stream' if stream else ''}",
            json={"message": "Summarize the draft thread"})
        stored = client.get(f"/api/chat/sessions/{session_id}/messages").json()["messages"]
    assert response.status_code == 200
    payload = json.loads(response.text.splitlines()[-1]) if stream else response.json()
    assert payload["generated_by"] == "agent"
    assert len(payload["sources"]) == 2
    assert len(stored[-1]["metadata"]["sources"]) == 2


def test_model_without_tool_support_uses_grounded_fallback(tmp_path: Path, monkeypatch) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "one", "Code", "The code is CEDAR-42", "Alice <alice@example.com>", 1780000000000)
    sources, _ = service.context_for("What is the code?")

    def respond(request: httpx.Request) -> httpx.Response:
        if "tools" in json.loads(request.content):
            return httpx.Response(400, json={"error": "model does not support tools"})
        return httpx.Response(200, json={"message": {"content": "The code is CEDAR-42. [Source 1]"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    answer, origin = asyncio.run(service.answer("What is the code?", sources))
    assert origin == "ollama"
    assert "CEDAR-42" in answer
    assert service._tools_supported is False


@pytest.mark.parametrize(("question", "expected"), [
    ("Which is the latest mail I received?", "friend"),
    ("What is my latest email about refund?", "refund"),
    ("Show details of mails from book my show", "ticket"),
    ("Find the message with CEDAR-42", "code"),
    ("Show my sent mail", "sent"),
    ("Find emails about nonexistent-phrase-xyz", None),
])
def test_retrieval_cases(tmp_path: Path, question: str, expected: str | None) -> None:
    service, account_id = setup_mail(tmp_path)
    add_mail(service, account_id, "ticket", "Movie ticket", "Your seat is B12", "BookMyShow <tickets@bookmyshow.com>", 1780000000000)
    add_mail(service, account_id, "refund", "Refund approved", "Your refund is approved", "Support <help@example.com>", 1780001000000)
    add_mail(service, account_id, "friend", "Weekend", "Coffee on Saturday", "Friend <friend@example.com>", 1780002000000)
    add_mail(service, account_id, "code", "Access code", "The code is CEDAR-42", "Admin <admin@example.com>", 1780000500000)
    add_mail(service, account_id, "sent", "Status report", "I sent the report", "Owner <owner@example.com>", 1780001500000, labels=["SENT"])
    sources, _ = service.context_for(question)
    assert (sources[0].metadata["message_id"] if sources else None) == expected

"""Local, rebuildable semantic index for mail chunks."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

from .repository import Repository

logger = logging.getLogger(__name__)


class MailVectorIndex:
    def __init__(self, repository: Repository, path: Path, ollama_url: str, model: str) -> None:
        self.repository = repository
        self.path = path
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.table_name = "mail_" + hashlib.sha256(model.encode()).hexdigest()[:12]
        self.lock = asyncio.Lock()

    def _database(self):
        import lancedb
        self.path.mkdir(parents=True, exist_ok=True)
        return lancedb.connect(str(self.path))

    async def index_batch(self, limit: int = 16) -> int:
        async with self.lock:
            return await self._index_batch(limit)

    async def _index_batch(self, limit: int) -> int:
        chunks = self.repository.pending_mail_vectors(self.model, limit)
        if not chunks:
            return 0
        inputs = [f"Subject: {c['subject']}\nFrom: {c['sender']}\n{c['content']}" for c in chunks]
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.ollama_url}/api/embed", json={"model": self.model, "input": inputs})
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        if len(vectors) != len(chunks):
            raise ValueError("Embedding model returned the wrong number of vectors")
        rows = [{"chunk_id": chunk["id"], "account_id": chunk["account_id"],
                 "message_id": chunk["message_id"], "vector": vector} for chunk, vector in zip(chunks, vectors)]
        await asyncio.to_thread(self._upsert_rows, rows)
        self.repository.mark_mail_vectors([chunk["id"] for chunk in chunks], self.model)
        return len(chunks)

    def _upsert_rows(self, rows: list[dict]) -> None:
        database = self._database()
        if self.table_name in database.list_tables().tables:
            table = database.open_table(self.table_name)
            table.merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
        else:
            database.create_table(self.table_name, data=rows)

    def search(self, query: str, limit: int = 20) -> list[int]:
        database = self._database()
        if self.table_name not in database.list_tables().tables:
            return []
        with httpx.Client(timeout=15) as client:
            response = client.post(f"{self.ollama_url}/api/embed", json={"model": self.model, "input": query})
            response.raise_for_status()
            vector = response.json()["embeddings"][0]
        table = database.open_table(self.table_name)
        return [int(row["chunk_id"]) for row in table.search(vector).limit(limit).to_list()
                if row.get("_distance", 0.0) <= 1.1]

    def remove_account(self, account_id: str) -> None:
        database = self._database()
        for name in database.list_tables().tables:
            if name.startswith("mail_"):
                database.open_table(name).delete(f"account_id = '{account_id}'")

    async def worker(self) -> None:
        while True:
            try:
                count = await self.index_batch()
                await asyncio.sleep(3 if count else 30)
            except Exception as exc:
                # Exact and FTS retrieval remain available while Ollama is offline.
                logger.warning("Mail embeddings paused: %s", exc)
                await asyncio.sleep(60)

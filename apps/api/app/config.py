from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Native runs use the repository-root .env; Compose supplies the same values
# through env_file and explicit container overrides. Never override real env vars.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    ollama_base_url: str
    chat_model: str
    llm_temperature: float
    ollama_timeout_seconds: float
    demo_mode: bool
    use_ollama: bool = True
    ollama_num_predict: int = 768
    embedding_model: str = "qwen3-embedding:0.6b"
    ollama_num_ctx: int = 8192

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("HEYBROSKI_DATA_DIR", ".hey-broski")).expanduser().resolve()
        database_path = Path(os.getenv("HEYBROSKI_DATABASE_PATH", str(data_dir / "heybroski.db"))).expanduser().resolve()
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
            chat_model=os.getenv("HEYBROSKI_CHAT_MODEL", "qwen3:4b-instruct"),
            llm_temperature=float(os.getenv("HEYBROSKI_LLM_TEMPERATURE", "0.2")),
            # Streaming chat uses this as an idle read timeout, not a total
            # browser deadline. The first model load can take longer.
            ollama_timeout_seconds=max(15.0, min(float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")), 300.0)),
            demo_mode=_bool("HEYBROSKI_DEMO_MODE", True),
            use_ollama=_bool("HEYBROSKI_USE_OLLAMA", True),
            # Older local .env files used 128, which cut answers mid-sentence.
            ollama_num_predict=max(512, min(int(os.getenv("OLLAMA_NUM_PREDICT", "768")), 2048)),
            embedding_model=os.getenv("HEYBROSKI_EMBEDDING_MODEL", "qwen3-embedding:0.6b"),
            ollama_num_ctx=max(4096, min(int(os.getenv("OLLAMA_NUM_CTX", "8192")), 32768)),
        )


settings = Settings.from_env()

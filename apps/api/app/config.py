from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    use_ollama: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("HEYBROSKI_DATA_DIR", ".hey-broski")).expanduser().resolve()
        database_path = Path(os.getenv("HEYBROSKI_DATABASE_PATH", str(data_dir / "heybroski.db"))).expanduser().resolve()
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
            chat_model=os.getenv("HEYBROSKI_CHAT_MODEL", "qwen3:8b"),
            llm_temperature=float(os.getenv("HEYBROSKI_LLM_TEMPERATURE", "0.2")),
            # Keep the end-to-end request below the browser's 60-second limit,
            # including when an older .env still contains the former 300 value.
            ollama_timeout_seconds=min(float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")), 45.0),
            demo_mode=_bool("HEYBROSKI_DEMO_MODE", True),
            use_ollama=_bool("HEYBROSKI_USE_OLLAMA", False),
        )


settings = Settings.from_env()

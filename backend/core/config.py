from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

CORE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CORE_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"

TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_ALLOWED_CORS_ORIGINS = "http://127.0.0.1:5000,http://localhost:5000"


def load_backend_env() -> None:
    load_dotenv(ENV_FILE)


load_backend_env()


def env_bool(name: str, default: str | bool = "false") -> bool:
    return str(os.getenv(name, str(default))).strip().lower() in TRUE_VALUES


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


def env_csv(name: str, default: str = "") -> tuple[str, ...]:
    value = env_str(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


def env_int(name: str, default: str | int, minimum: int | None = None, strict: bool = True) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        if strict:
            raise
        value = int(default)
    return max(minimum, value) if minimum is not None else value


def env_float(name: str, default: str | float, strict: bool = True) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        if strict:
            raise
        return float(default)


def resolve_repo_path(path_value: str) -> str:
    configured_path = str(path_value or "").strip()
    if not configured_path:
        return ""

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path)


@dataclass(frozen=True)
class AppSettings:
    max_question_chars: int = 1200
    live_verify_enabled: bool = True
    live_verify_limit: int = 2
    response_cache_ttl: int = 300
    chat_cache_version: str = "2026-06-01-rag-v3"
    max_feedback_text_chars: int = 4000
    max_feedback_sources: int = 6
    startup_rebuild_index: bool = False
    startup_rebuild_full_site: bool = True
    startup_use_sitemaps: bool = True
    startup_skip_vector_index: bool = False
    startup_max_urls_per_faculty: int = 0
    startup_max_depth: int = 5
    startup_max_links_per_page: int = 150
    startup_fetch_workers: int = 12
    startup_terminal_progress: bool = True
    allowed_cors_origins: tuple[str, ...] = ("http://127.0.0.1:5000", "http://localhost:5000")

    @property
    def rebuild_index(self) -> bool:
        return self.startup_rebuild_index

    @property
    def rebuild_full_site(self) -> bool:
        return self.startup_rebuild_full_site

    @property
    def use_sitemaps(self) -> bool:
        return self.startup_use_sitemaps

    @property
    def skip_vector_index(self) -> bool:
        return self.startup_skip_vector_index

    @property
    def max_urls_per_faculty(self) -> int:
        return self.startup_max_urls_per_faculty

    @property
    def max_depth(self) -> int:
        return self.startup_max_depth

    @property
    def max_links_per_page(self) -> int:
        return self.startup_max_links_per_page

    @property
    def fetch_workers(self) -> int:
        return self.startup_fetch_workers

    @property
    def terminal_progress(self) -> bool:
        return self.startup_terminal_progress


Settings = AppSettings


def get_app_settings() -> AppSettings:
    return AppSettings(
        max_question_chars=env_int("MAX_QUESTION_CHARS", "1200", minimum=120),
        live_verify_enabled=env_bool("LIVE_VERIFY_ENABLED", "true"),
        live_verify_limit=env_int("LIVE_VERIFY_LIMIT", "2", minimum=0),
        response_cache_ttl=env_int("CHAT_RESPONSE_CACHE_TTL", "300", minimum=60),
        chat_cache_version=env_str("CHAT_CACHE_VERSION", "2026-06-01-rag-v3"),
        max_feedback_text_chars=env_int("MAX_FEEDBACK_TEXT_CHARS", "4000", minimum=200),
        max_feedback_sources=env_int("MAX_FEEDBACK_SOURCES", "6", minimum=1),
        startup_rebuild_index=env_bool("STARTUP_REBUILD_INDEX", "false"),
        startup_rebuild_full_site=env_bool("STARTUP_REBUILD_FULL_SITE", "true"),
        startup_use_sitemaps=env_bool("STARTUP_USE_SITEMAPS", "true"),
        startup_skip_vector_index=env_bool("STARTUP_SKIP_VECTOR_INDEX", "false"),
        startup_max_urls_per_faculty=env_int("STARTUP_MAX_URLS_PER_FACULTY", "0", minimum=0),
        startup_max_depth=env_int("STARTUP_MAX_DEPTH", "5", minimum=0),
        startup_max_links_per_page=env_int("STARTUP_MAX_LINKS_PER_PAGE", "150", minimum=10),
        startup_fetch_workers=env_int("STARTUP_FETCH_WORKERS", "12", minimum=1),
        startup_terminal_progress=env_bool("STARTUP_TERMINAL_PROGRESS", "true"),
        allowed_cors_origins=env_csv("ALLOWED_CORS_ORIGINS", DEFAULT_ALLOWED_CORS_ORIGINS),
    )


def get_chat_runtime_settings() -> AppSettings:
    return get_app_settings()


def get_startup_indexing_settings() -> AppSettings:
    return get_app_settings()


APP_SETTINGS = get_app_settings()

MAX_QUESTION_CHARS = APP_SETTINGS.max_question_chars
LIVE_VERIFY_ENABLED = APP_SETTINGS.live_verify_enabled
LIVE_VERIFY_LIMIT = APP_SETTINGS.live_verify_limit
RESPONSE_CACHE_TTL = APP_SETTINGS.response_cache_ttl
CHAT_CACHE_VERSION = APP_SETTINGS.chat_cache_version
MAX_FEEDBACK_TEXT_CHARS = APP_SETTINGS.max_feedback_text_chars
MAX_FEEDBACK_SOURCES = APP_SETTINGS.max_feedback_sources
STARTUP_REBUILD_INDEX = APP_SETTINGS.startup_rebuild_index
STARTUP_REBUILD_FULL_SITE = APP_SETTINGS.startup_rebuild_full_site
STARTUP_USE_SITEMAPS = APP_SETTINGS.startup_use_sitemaps
STARTUP_SKIP_VECTOR_INDEX = APP_SETTINGS.startup_skip_vector_index
STARTUP_MAX_URLS_PER_FACULTY = APP_SETTINGS.startup_max_urls_per_faculty
STARTUP_MAX_DEPTH = APP_SETTINGS.startup_max_depth
STARTUP_MAX_LINKS_PER_PAGE = APP_SETTINGS.startup_max_links_per_page
STARTUP_FETCH_WORKERS = APP_SETTINGS.startup_fetch_workers
STARTUP_TERMINAL_PROGRESS = APP_SETTINGS.startup_terminal_progress
ALLOWED_CORS_ORIGINS = APP_SETTINGS.allowed_cors_origins


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str
    generation_model: str
    embedding_model: str


def get_ollama_settings() -> OllamaSettings:
    return OllamaSettings(
        base_url=env_str("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") or "http://127.0.0.1:11434",
        generation_model=env_str("OLLAMA_GENERATION_MODEL", "qwen3:4b"),
        embedding_model=env_str("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
    )


@dataclass(frozen=True)
class VectorStoreSettings:
    url: str
    path: str
    collection_name: str
    timeout: int


def get_vector_settings() -> VectorStoreSettings:
    return VectorStoreSettings(
        url=env_str("QDRANT_URL", "http://127.0.0.1:6333"),
        path=resolve_repo_path(os.getenv("QDRANT_PATH", "")),
        collection_name=env_str("QDRANT_COLLECTION", "uvt_asist_chunks"),
        timeout=env_int("QDRANT_TIMEOUT_SECONDS", "30"),
    )

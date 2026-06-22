from __future__ import annotations

import copy
import os
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

from core.config import (
    STARTUP_FETCH_WORKERS,
    STARTUP_MAX_DEPTH,
    STARTUP_MAX_LINKS_PER_PAGE,
    STARTUP_MAX_URLS_PER_FACULTY,
    STARTUP_REBUILD_FULL_SITE,
    STARTUP_REBUILD_INDEX,
    STARTUP_SKIP_VECTOR_INDEX,
    STARTUP_TERMINAL_PROGRESS,
    STARTUP_USE_SITEMAPS,
    env_bool,
)
from faculties import FACULTIES

INDEXING_STATE_LOCK = threading.Lock()
INDEXING_STATE: dict = {
    "enabled": STARTUP_REBUILD_INDEX,
    "running": False,
    "ready": True,
    "phase": "idle",
    "message": "Indexarea de startup nu ruleaza.",
    "progress": 0,
    "started_at": None,
    "finished_at": None,
    "error": "",
    "current_faculty": "",
    "processed_faculties": 0,
    "total_faculties": len(FACULTIES),
    "discovered_urls": 0,
    "fetched_pages": 0,
    "page_count": 0,
    "chunk_count": 0,
    "embedded_chunks": 0,
    "total_chunks": 0,
    "error_count": 0,
}
TERMINAL_PROGRESS_LOCK = threading.Lock()
TERMINAL_PROGRESS_STATE = {
    "last_rendered_at": 0.0,
    "last_progress": -1,
    "last_phase": "",
    "line_length": 0,
}
TERMINAL_PROGRESS_WIDTH = 20
TERMINAL_PROGRESS_MIN_INTERVAL = 0.35


def compact_text(value, max_chars: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_chars]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def set_indexing_state(**updates) -> dict:
    with INDEXING_STATE_LOCK:
        INDEXING_STATE.update(updates)
        return copy.deepcopy(INDEXING_STATE)


def get_indexing_state() -> dict:
    with INDEXING_STATE_LOCK:
        return copy.deepcopy(INDEXING_STATE)


def indexing_blocks_chat() -> bool:
    return bool(get_indexing_state().get("running"))



def flask_debug_enabled() -> bool:
    return env_bool("FLASK_DEBUG", "false")


def should_run_startup_index_rebuild(debug: bool) -> bool:
    if not STARTUP_REBUILD_INDEX:
        return False
    if debug and os.getenv("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def describe_indexing_progress(update: dict) -> str:
    phase = update.get("phase") or "indexing"
    faculty_name = update.get("current_faculty") or ""

    if phase == "discovering":
        message = "Descopar paginile oficiale UVT."
    elif phase == "fetching":
        message = "Descarc si extrag continutul din paginile oficiale."
    elif phase == "chunking":
        message = "Transform paginile in fragmente pentru cautare."
    elif phase == "embedding":
        done = int(update.get("embedded_chunks") or 0)
        total = int(update.get("total_chunks") or update.get("chunk_count") or 0)
        message = f"Generez embeddings local cu Ollama ({done}/{total} fragmente)."
    elif phase == "saving":
        message = "Salvez indexul JSON si vectorii in Qdrant."
    elif phase == "ready":
        message = "Indexarea s-a finalizat."
    else:
        message = "Indexarea este in curs."

    if faculty_name and phase in {"discovering", "fetching"}:
        message = f"{message} Sectiune curenta: {faculty_name}."
    return message


def terminal_progress_enabled() -> bool:
    return bool(STARTUP_TERMINAL_PROGRESS)


def terminal_text(value, max_chars: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars - 3]}..."


def compact_exception(exc: Exception, max_chars: int) -> str:
    message = compact_text(exc, max_chars)
    exception_type = type(exc).__name__
    if not message:
        return exception_type
    return compact_text(f"{exception_type}: {message}", max_chars)


def build_terminal_progress_suffix(state: dict) -> str:
    phase = state.get("phase")
    if phase in {"discovering", "fetching"}:
        parts = [
            f"facultati {int(state.get('processed_faculties') or 0)}/{int(state.get('total_faculties') or len(FACULTIES))}",
            f"url-uri {int(state.get('discovered_urls') or 0)}",
            f"pagini {int(state.get('fetched_pages') or 0)}",
        ]
        errors = int(state.get("error_count") or 0)
        if errors:
            parts.append(f"erori {errors}")
        return ", ".join(parts)

    if phase == "embedding":
        done = int(state.get("embedded_chunks") or 0)
        total = int(state.get("total_chunks") or state.get("chunk_count") or 0)
        return f"embeddings {done}/{total}"

    if phase in {"chunking", "saving", "ready"}:
        pages = int(state.get("page_count") or 0)
        chunks = int(state.get("chunk_count") or 0)
        errors = int(state.get("error_count") or 0)
        suffix = f"pagini {pages}, fragmente {chunks}"
        return f"{suffix}, erori {errors}" if errors else suffix

    return ""


def render_terminal_indexing_progress(state: dict, force: bool = False, final: bool = False) -> None:
    if not terminal_progress_enabled():
        return

    progress = max(0, min(100, int(state.get("progress", 0) or 0)))
    phase = terminal_text(state.get("phase") or "indexing", 14)
    message = terminal_text(state.get("message") or "Indexarea este in curs.", 48)
    suffix = terminal_text(build_terminal_progress_suffix(state), 38)
    now = time.time()

    with TERMINAL_PROGRESS_LOCK:
        should_render = (
            force
            or final
            or progress != TERMINAL_PROGRESS_STATE["last_progress"]
            or phase != TERMINAL_PROGRESS_STATE["last_phase"]
            or now - TERMINAL_PROGRESS_STATE["last_rendered_at"] >= TERMINAL_PROGRESS_MIN_INTERVAL
        )
        if not should_render:
            return

        filled = int(TERMINAL_PROGRESS_WIDTH * progress / 100)
        bar = "#" * filled + "-" * (TERMINAL_PROGRESS_WIDTH - filled)
        line = f"Indexare UVT [{bar}] {progress:3d}% {phase} | {message}"
        if suffix:
            line = f"{line} | {suffix}"
        terminal_width = shutil.get_terminal_size(fallback=(100, 20)).columns
        line = terminal_text(line, max(72, terminal_width - 1))

        previous_length = int(TERMINAL_PROGRESS_STATE["line_length"] or 0)
        padding = " " * max(0, previous_length - len(line))
        dynamic_terminal = bool(getattr(sys.stdout, "isatty", lambda: False)())
        prefix = "\r" if dynamic_terminal else ""
        end = "\n" if final or not dynamic_terminal else ""
        print(f"{prefix}{line}{padding}", end=end, flush=True)

        TERMINAL_PROGRESS_STATE.update({
            "last_rendered_at": now,
            "last_progress": progress,
            "last_phase": phase,
            "line_length": 0 if final or not dynamic_terminal else len(line),
        })


def update_startup_index_progress(update: dict) -> None:
    state_update = {
        "phase": update.get("phase", "indexing"),
        "message": describe_indexing_progress(update),
        "progress": max(0, min(100, int(update.get("progress", 0) or 0))),
        "current_faculty": update.get("current_faculty", ""),
    }

    for key in (
        "processed_faculties",
        "total_faculties",
        "discovered_urls",
        "fetched_pages",
        "page_count",
        "chunk_count",
        "embedded_chunks",
        "total_chunks",
        "error_count",
    ):
        if key in update:
            state_update[key] = update[key]

    state = set_indexing_state(**state_update)
    render_terminal_indexing_progress(state)


def run_startup_index_rebuild() -> None:
    from build_index import build_index

    initial_state = set_indexing_state(
        enabled=True,
        running=True,
        ready=False,
        phase="starting",
        message="Pornesc indexarea completa a surselor oficiale UVT.",
        progress=1,
        started_at=utc_now_iso(),
        finished_at=None,
        error="",
        current_faculty="",
        processed_faculties=0,
        total_faculties=len(FACULTIES),
        discovered_urls=0,
        fetched_pages=0,
        page_count=0,
        chunk_count=0,
        embedded_chunks=0,
        total_chunks=0,
        error_count=0,
    )

    max_urls_per_faculty = STARTUP_MAX_URLS_PER_FACULTY
    max_depth = STARTUP_MAX_DEPTH
    max_links_per_page = STARTUP_MAX_LINKS_PER_PAGE
    fetch_workers = STARTUP_FETCH_WORKERS

    if STARTUP_REBUILD_FULL_SITE:
        if max_urls_per_faculty > 0:
            max_urls_per_faculty = max(max_urls_per_faculty, 800)
        max_depth = max(max_depth, 5)
        max_links_per_page = max(max_links_per_page, 150)
        fetch_workers = max(fetch_workers, 12)

    print(
        "Startup index rebuild enabled. "
        f"full_site={STARTUP_REBUILD_FULL_SITE}, sitemaps={STARTUP_USE_SITEMAPS}, "
        f"max_urls_per_faculty={max_urls_per_faculty}, max_depth={max_depth}, "
        f"max_links_per_page={max_links_per_page}, fetch_workers={fetch_workers}, "
        f"skip_vector_index={STARTUP_SKIP_VECTOR_INDEX}",
        flush=True,
    )
    render_terminal_indexing_progress(initial_state, force=True)
    started_at = time.time()
    try:
        document = build_index(
            max_urls_per_faculty=max_urls_per_faculty,
            max_depth=max_depth,
            max_links_per_page=max_links_per_page,
            fetch_workers=fetch_workers,
            use_sitemaps=STARTUP_USE_SITEMAPS,
            skip_vector_index=STARTUP_SKIP_VECTOR_INDEX,
            progress=update_startup_index_progress,
        )
        elapsed = time.time() - started_at
        final_state = set_indexing_state(
            running=False,
            ready=True,
            phase="ready",
            message="Indexarea completa s-a finalizat.",
            progress=100,
            finished_at=utc_now_iso(),
            error="",
            page_count=document.get("page_count", 0),
            chunk_count=document.get("chunk_count", 0),
        )
        render_terminal_indexing_progress(final_state, force=True, final=True)
        print(
            "Startup index rebuild finished. "
            f"pages={document.get('page_count', 0)}, chunks={document.get('chunk_count', 0)}, "
            f"elapsed_seconds={elapsed:.1f}",
            flush=True,
        )
    except Exception as exc:
        error_state = set_indexing_state(
            running=False,
            ready=False,
            phase="error",
            message="Indexarea de startup a esuat. Verifica serviciile locale si logurile backend.",
            finished_at=utc_now_iso(),
            error=compact_exception(exc, 900),
        )
        render_terminal_indexing_progress(error_state, force=True, final=True)
        print("Startup index rebuild failed with traceback:", flush=True)
        print(traceback.format_exc(), flush=True)


def start_startup_index_rebuild(debug: bool) -> None:
    if not should_run_startup_index_rebuild(debug):
        set_indexing_state(enabled=STARTUP_REBUILD_INDEX, running=False, ready=True)
        return

    thread = threading.Thread(target=run_startup_index_rebuild, name="startup-index-rebuild", daemon=True)
    thread.start()




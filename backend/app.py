from __future__ import annotations

import re

from flask import Flask
from flask_cors import CORS

import api.routes_chat as routes_chat
import api.routes_feedback as routes_feedback
import services.chat_service as chat_service
import services.feedback_service as feedback_service
import services.indexing_service as indexing_service
from api.routes_chat import bp as chat_bp
from api.routes_faculties import bp as faculties_bp
from api.routes_feedback import bp as feedback_bp
from api.routes_health import bp as health_bp
from api.routes_indexing import bp as indexing_bp
from core.config import ALLOWED_CORS_ORIGINS, env_bool
from core.logging import setup_logging
from services.indexing_service import start_startup_index_rebuild

BACKEND_ENDPOINTS = ("/health", "/faculties", "/indexing/status", "/chat", "/feedback")

# Backwards-compatible module facade for tests and older scripts that imported
# helpers from app.py before the Flask entrypoint was split into services.
RESPONSE_CACHE = chat_service.RESPONSE_CACHE
CHAT_CACHE_VERSION = chat_service.CHAT_CACHE_VERSION
LIVE_VERIFY_ENABLED = chat_service.LIVE_VERIFY_ENABLED
STARTUP_REBUILD_INDEX = indexing_service.STARTUP_REBUILD_INDEX
LOG_FILE = feedback_service.LOG_FILE
_LIVE_VERIFY_RETRIEVAL_IMPL = chat_service.live_verify_retrieval
_ENSURE_CANONICAL_CONTACT_IMPL = chat_service.ensure_canonical_uvt_contact_source
_BUILD_CACHE_KEY_IMPL = chat_service.build_cache_key

load_index = chat_service.load_index
get_index_status = chat_service.get_index_status
get_vector_index_status = chat_service.get_vector_index_status
rank_index = chat_service.rank_index
rank_lexical_index = chat_service.rank_lexical_index
ask_ollama_json = chat_service.ask_ollama_json
verify_pages = chat_service.verify_pages
should_skip_generation = chat_service.should_skip_generation
needs_faculty_clarification = chat_service.needs_faculty_clarification
source_navigation_topic = chat_service.source_navigation_topic
should_use_source_navigation_answer = chat_service.should_use_source_navigation_answer
build_local_fallback_answer = chat_service.build_local_fallback_answer
merge_ranked_chunks = chat_service.merge_ranked_chunks
get_indexing_state = indexing_service.get_indexing_state
set_indexing_state = indexing_service.set_indexing_state


def _sync_chat_service_overrides() -> None:
    chat_service.CHAT_CACHE_VERSION = CHAT_CACHE_VERSION
    chat_service.LIVE_VERIFY_ENABLED = LIVE_VERIFY_ENABLED
    chat_service.load_index = load_index
    chat_service.get_index_status = get_index_status
    chat_service.get_vector_index_status = get_vector_index_status
    chat_service.rank_index = rank_index
    chat_service.rank_lexical_index = rank_lexical_index
    chat_service.ask_ollama_json = ask_ollama_json
    chat_service.verify_pages = verify_pages
    if globals().get("live_verify_retrieval") is _LIVE_VERIFY_RETRIEVAL_WRAPPER:
        chat_service.live_verify_retrieval = _LIVE_VERIFY_RETRIEVAL_IMPL
    else:
        chat_service.live_verify_retrieval = globals()["live_verify_retrieval"]


def _sync_feedback_service_overrides() -> None:
    feedback_service.LOG_FILE = LOG_FILE


def handle_chat(payload) -> tuple[dict, int]:
    _sync_chat_service_overrides()
    return chat_service.handle_chat(payload)


def handle_feedback(payload) -> dict:
    _sync_feedback_service_overrides()
    return feedback_service.handle_feedback(payload)


def build_cache_key(*args, **kwargs) -> str:
    _sync_chat_service_overrides()
    return _BUILD_CACHE_KEY_IMPL(*args, **kwargs)


def live_verify_retrieval(*args, **kwargs):
    _sync_chat_service_overrides()
    return _LIVE_VERIFY_RETRIEVAL_IMPL(*args, **kwargs)


_LIVE_VERIFY_RETRIEVAL_WRAPPER = live_verify_retrieval


def ensure_canonical_uvt_contact_source(*args, **kwargs) -> dict:
    _sync_chat_service_overrides()
    return _ENSURE_CANONICAL_CONTACT_IMPL(*args, **kwargs)


def should_run_startup_index_rebuild(debug: bool) -> bool:
    indexing_service.STARTUP_REBUILD_INDEX = STARTUP_REBUILD_INDEX
    return indexing_service.should_run_startup_index_rebuild(debug)


routes_chat.handle_chat = handle_chat
routes_feedback.handle_feedback = handle_feedback


def build_cors_origins():
    origins = []
    for origin in ALLOWED_CORS_ORIGINS:
        if origin == "chrome-extension://*":
            origins.append(re.compile(r"^chrome-extension://[a-p]{32}$"))
        else:
            origins.append(origin)
    return origins


def configure_cors(flask_app: Flask) -> None:
    resources = {endpoint: {"origins": build_cors_origins()} for endpoint in BACKEND_ENDPOINTS}
    CORS(
        flask_app,
        resources=resources,
        methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        supports_credentials=False,
    )


def create_app() -> Flask:
    setup_logging()
    flask_app = Flask(__name__)
    configure_cors(flask_app)
    flask_app.register_blueprint(health_bp)
    flask_app.register_blueprint(faculties_bp)
    flask_app.register_blueprint(indexing_bp)
    flask_app.register_blueprint(chat_bp)
    flask_app.register_blueprint(feedback_bp)
    return flask_app


app = create_app()


def flask_debug_enabled() -> bool:
    return env_bool("FLASK_DEBUG", "false")


if __name__ == "__main__":
    debug = flask_debug_enabled()
    start_startup_index_rebuild(debug)
    app.run(host="127.0.0.1", port=5000, debug=debug, use_reloader=debug)

from __future__ import annotations

import re

from flask import Flask
from flask_cors import CORS

from api.routes_chat import bp as chat_bp
from api.routes_faculties import bp as faculties_bp
from api.routes_feedback import bp as feedback_bp
from api.routes_health import bp as health_bp
from api.routes_indexing import bp as indexing_bp
from core.config import ALLOWED_CORS_ORIGINS, env_bool
from core.logging import setup_logging
from services.indexing_service import start_startup_index_rebuild

BACKEND_ENDPOINTS = ("/health", "/faculties", "/indexing/status", "/chat", "/feedback")


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

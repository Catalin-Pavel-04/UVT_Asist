from __future__ import annotations

import time

from flask import Blueprint, jsonify, request

from services.chat_service import handle_chat
from services.telemetry_service import log_chat_exception, log_chat_request, new_request_id

bp = Blueprint("chat", __name__)


@bp.post("/chat")
def chat():
    request_id = new_request_id()
    started_at = time.perf_counter()
    request_payload = request.get_json(silent=True) or {}
    try:
        payload, status = handle_chat(request_payload)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        log_chat_exception(request_id, request_payload, elapsed_ms, exc)
        raise
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    log_chat_request(request_id, request_payload, payload, elapsed_ms)
    return jsonify(payload), status

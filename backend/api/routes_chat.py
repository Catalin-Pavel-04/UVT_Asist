from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.chat_service import handle_chat

bp = Blueprint("chat", __name__)


@bp.post("/chat")
def chat():
    payload, status = handle_chat(request.get_json(silent=True) or {})
    return jsonify(payload), status

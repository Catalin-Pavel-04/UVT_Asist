from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.feedback_service import handle_feedback

bp = Blueprint("feedback", __name__)


@bp.post("/feedback")
def feedback():
    return jsonify(handle_feedback(request.get_json(silent=True) or {}))

from __future__ import annotations

from flask import Blueprint, jsonify

from services.health_service import build_health_payload

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify(build_health_payload())

from __future__ import annotations

from flask import Blueprint, jsonify

from services.indexing_service import get_indexing_state

bp = Blueprint("indexing", __name__)


@bp.get("/indexing/status")
def indexing_status():
    return jsonify({"indexing": get_indexing_state()})

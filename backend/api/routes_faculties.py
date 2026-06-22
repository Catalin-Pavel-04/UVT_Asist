from __future__ import annotations

from flask import Blueprint, jsonify

from faculties import FACULTIES

bp = Blueprint("faculties", __name__)


@bp.get("/faculties")
def faculties():
    return jsonify({
        "faculties": [
            {"id": faculty["id"], "name": faculty["name"]}
            for faculty in FACULTIES
        ]
    })

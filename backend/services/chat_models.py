from __future__ import annotations

from dataclasses import dataclass

from faculties import FACULTIES

GENERAL_FACULTY_ID = "uvt"
FACULTY_MAP = {faculty["id"]: faculty for faculty in FACULTIES}


@dataclass(frozen=True)
class ChatRequest:
    question: str
    requested_faculty_id: str
    history: list[dict]


def get_faculty(faculty_id: str) -> dict:
    return FACULTY_MAP.get(faculty_id, FACULTY_MAP[GENERAL_FACULTY_ID])

from __future__ import annotations

from statistics import mean, median
from typing import Any


LOW_CONFIDENCE_THRESHOLD = 35


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def source_url_matches(source: dict, expected_url_contains: list[str]) -> bool:
    """Return True when a source URL contains any expected URL fragment."""
    url = _as_text(source.get("url")).lower()
    expected = [_as_text(item).lower() for item in expected_url_contains if _as_text(item)]
    return bool(url and expected and any(fragment in url for fragment in expected))


def top_url_match(sources: list[dict], expected_url_contains: list[str], depth: int) -> bool:
    """Check whether any of the first `depth` sources matches the expected URL fragments."""
    if depth <= 0:
        return False
    return any(source_url_matches(source, expected_url_contains) for source in sources[:depth])


def title_matches(source: dict, expected_title_contains: list[str]) -> bool:
    title = _as_text(source.get("title")).lower()
    expected = [_as_text(item).lower() for item in expected_title_contains if _as_text(item)]
    return bool(title and expected and any(fragment in title for fragment in expected))


def is_low_confidence_response(response: dict) -> bool:
    confidence = _as_text(response.get("confidence")).lower()
    if confidence == "low":
        return True
    score = _as_number(response.get("confidence_score"), default=100)
    return score < LOW_CONFIDENCE_THRESHOLD


def expected_unanswerable_handled(question: dict, response: dict) -> bool:
    """Unanswerable questions are handled when metadata signals weak or insufficient evidence."""
    if bool(question.get("should_have_answer", True)):
        return False
    if response.get("error"):
        return False

    evidence = response.get("evidence") if isinstance(response.get("evidence"), dict) else {}
    if evidence.get("answerable") is False:
        return True
    if is_low_confidence_response(response):
        return True
    return not _as_list(response.get("sources"))


def build_evaluation_result(
    question: dict,
    payload: dict | None,
    latency_seconds: float,
    error: str | None = None,
) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    sources = [source for source in _as_list(payload.get("sources")) if isinstance(source, dict)]
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    expected_urls = [_as_text(item) for item in _as_list(question.get("expected_url_contains")) if _as_text(item)]
    expected_titles = [_as_text(item) for item in _as_list(question.get("expected_title_contains")) if _as_text(item)]
    top_source = sources[0] if sources else {}

    result = {
        "id": _as_text(question.get("id")),
        "category": _as_text(question.get("category")),
        "faculty_id": _as_text(question.get("faculty_id") or "uvt"),
        "question": _as_text(question.get("question")),
        "should_have_answer": bool(question.get("should_have_answer", True)),
        "expected_url_contains": expected_urls,
        "expected_title_contains": expected_titles,
        "notes": _as_text(question.get("notes")),
        "latency_seconds": round(float(latency_seconds), 3),
        "answer": _as_text(payload.get("answer")),
        "confidence": _as_text(payload.get("confidence") or "unknown"),
        "confidence_score": payload.get("confidence_score"),
        "matched_faculty_id": _as_text(payload.get("matched_faculty_id")),
        "retrieval_backend": _as_text(payload.get("retrieval_backend")),
        "generation_mode": _as_text(payload.get("generation_mode")),
        "live_verified": _as_bool(payload.get("live_verified")),
        "sources": sources,
        "evidence": evidence,
        "top_source_url": _as_text(top_source.get("url")),
        "top_source_title": _as_text(top_source.get("title")),
        "top1_url_match": top_url_match(sources, expected_urls, depth=1),
        "top3_url_match": top_url_match(sources, expected_urls, depth=3),
        "top1_title_match": title_matches(top_source, expected_titles),
        "error": _as_text(error),
    }
    result["has_answer"] = bool(result["answer"] and not result["error"])
    result["low_confidence"] = bool(not result["error"] and is_low_confidence_response(result))
    result["expected_unanswerable_handled"] = expected_unanswerable_handled(question, result)
    return result


def calculate_metrics(results: list[dict]) -> dict:
    latencies = [
        float(result["latency_seconds"])
        for result in results
        if isinstance(result.get("latency_seconds"), (int, float))
    ]

    return {
        "total_questions": len(results),
        "answered_count": sum(1 for result in results if result.get("has_answer")),
        "low_confidence_count": sum(1 for result in results if result.get("low_confidence")),
        "top1_url_match_count": sum(1 for result in results if result.get("top1_url_match")),
        "top3_url_match_count": sum(1 for result in results if result.get("top3_url_match")),
        "expected_unanswerable_handled_count": sum(
            1 for result in results if result.get("expected_unanswerable_handled")
        ),
        "average_latency_seconds": round(mean(latencies), 3) if latencies else 0,
        "median_latency_seconds": round(median(latencies), 3) if latencies else 0,
    }

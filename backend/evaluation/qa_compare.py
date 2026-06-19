from __future__ import annotations

import re
import unicodedata
from statistics import mean, median
from typing import Any

from evaluation.rag_eval import expected_unanswerable_handled, is_low_confidence_response, top_url_match


ROMANIAN_STOPWORDS = {
    "a", "ai", "al", "ale", "am", "ar", "as", "ca", "care", "ce", "cea", "cel", "cele",
    "cu", "cum", "daca", "de", "din", "este", "fi", "fie", "in", "la", "mai", "o", "pe",
    "pentru", "pot", "sa", "sau", "se", "si", "sunt", "un", "unde",
}


def normalize_text(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9\s:/.-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def content_tokens(text: Any) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) >= 3 and token not in ROMANIAN_STOPWORDS
    }


def phrase_present(text: str, phrase: str) -> bool:
    if "|" in phrase:
        return any(phrase_present(text, option) for option in phrase.split("|") if option.strip())
    return normalize_text(phrase) in normalize_text(text)


def count_present_phrases(text: str, phrases: list[str]) -> int:
    return sum(1 for phrase in phrases if phrase_present(text, phrase))


def ideal_token_coverage(answer: str, ideal_answer: str) -> float:
    ideal_tokens = content_tokens(ideal_answer)
    if not ideal_tokens:
        return 1.0
    answer_tokens = content_tokens(answer)
    return len(ideal_tokens & answer_tokens) / len(ideal_tokens)


def confidence_matches_expectation(result: dict, expected: str) -> bool:
    expected = normalize_text(expected or "")
    low = is_low_confidence_response(result)
    if expected == "low":
        return low
    if expected == "medium_or_high":
        return not low
    if expected == "high":
        return str(result.get("confidence", "")).lower() == "high"
    return True


def compare_qa_result(question: dict, payload: dict, latency_seconds: float, error: str | None = None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    answer = str(payload.get("answer") or "")
    sources = [source for source in payload.get("sources", []) if isinstance(source, dict)]
    expected_urls = [str(item) for item in question.get("expected_url_contains", []) if str(item).strip()]
    must_include = [str(item) for item in question.get("answer_must_include", []) if str(item).strip()]
    must_not_include = [str(item) for item in question.get("answer_should_not_include", []) if str(item).strip()]
    should_have_answer = bool(question.get("should_have_answer", True))
    expected_confidence = str(question.get("expected_confidence") or "")

    result = {
        "id": str(question.get("id", "")),
        "category": str(question.get("category", "")),
        "faculty_id": str(question.get("faculty_id", "uvt")),
        "question": str(question.get("question", "")),
        "ideal_answer": str(question.get("ideal_answer", "")),
        "answer": answer,
        "confidence": str(payload.get("confidence") or "unknown"),
        "confidence_score": payload.get("confidence_score"),
        "matched_faculty_id": str(payload.get("matched_faculty_id") or ""),
        "retrieval_backend": str(payload.get("retrieval_backend") or ""),
        "generation_mode": str(payload.get("generation_mode") or ""),
        "live_verified": bool(payload.get("live_verified")),
        "sources": sources,
        "top_source_url": str(sources[0].get("url", "")) if sources else "",
        "latency_seconds": round(float(latency_seconds), 3),
        "error": str(error or ""),
        "should_have_answer": should_have_answer,
        "expected_confidence": expected_confidence,
        "expected_url_contains": expected_urls,
        "answer_must_include": must_include,
        "answer_should_not_include": must_not_include,
    }

    result["top1_url_match"] = top_url_match(sources, expected_urls, depth=1) if expected_urls else True
    result["top3_url_match"] = top_url_match(sources, expected_urls, depth=3) if expected_urls else True
    result["required_phrase_count"] = count_present_phrases(answer, must_include)
    result["required_phrase_total"] = len(must_include)
    result["required_phrase_coverage"] = (
        round(result["required_phrase_count"] / len(must_include), 3) if must_include else 1.0
    )
    result["forbidden_phrases_found"] = [
        phrase for phrase in must_not_include if phrase_present(answer, phrase)
    ]
    result["ideal_token_coverage"] = round(ideal_token_coverage(answer, result["ideal_answer"]), 3)
    result["confidence_match"] = confidence_matches_expectation(result, expected_confidence)
    result["expected_unanswerable_handled"] = expected_unanswerable_handled(question, result)

    if error:
        score = 0
    elif not should_have_answer:
        score = 0
        score += 45 if result["expected_unanswerable_handled"] else 0
        score += 25 if result["required_phrase_coverage"] >= 0.5 else 0
        score += 20 if result["confidence_match"] else 0
        score += 10 if not result["forbidden_phrases_found"] else 0
    else:
        score = 0
        score += 30 if result["top1_url_match"] else 18 if result["top3_url_match"] else 0
        score += round(30 * result["required_phrase_coverage"])
        score += round(20 * min(1.0, result["ideal_token_coverage"] * 1.35))
        score += 10 if result["confidence_match"] else 0
        score += 10 if not result["forbidden_phrases_found"] else 0

    result["qa_score"] = int(max(0, min(100, score)))
    result["passed"] = bool(result["qa_score"] >= 70)
    return result


def calculate_qa_metrics(results: list[dict]) -> dict:
    latencies = [float(item["latency_seconds"]) for item in results if isinstance(item.get("latency_seconds"), (int, float))]
    scores = [int(item.get("qa_score", 0)) for item in results]
    return {
        "total_questions": len(results),
        "passed_count": sum(1 for item in results if item.get("passed")),
        "failed_count": sum(1 for item in results if not item.get("passed")),
        "average_qa_score": round(mean(scores), 2) if scores else 0,
        "median_qa_score": round(median(scores), 2) if scores else 0,
        "top1_url_match_count": sum(1 for item in results if item.get("top1_url_match")),
        "top3_url_match_count": sum(1 for item in results if item.get("top3_url_match")),
        "confidence_match_count": sum(1 for item in results if item.get("confidence_match")),
        "expected_unanswerable_handled_count": sum(
            1 for item in results if item.get("expected_unanswerable_handled")
        ),
        "average_latency_seconds": round(mean(latencies), 3) if latencies else 0,
        "median_latency_seconds": round(median(latencies), 3) if latencies else 0,
    }

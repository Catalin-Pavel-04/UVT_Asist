from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - depends on local environment.
    requests = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"
DEFAULT_DATASET = BACKEND_DIR / "evaluation" / "eval_qa_1000_independent.json"
DATA_EVALUATION_DATASET = BACKEND_DIR / "data" / "evaluation" / "eval_qa_1000_independent.json"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "data" / "evaluation"

ROMANIAN_STOPWORDS = {
    "a",
    "acest",
    "aceasta",
    "ai",
    "al",
    "ale",
    "am",
    "ar",
    "as",
    "ca",
    "care",
    "ce",
    "cea",
    "cel",
    "cele",
    "cu",
    "cum",
    "daca",
    "de",
    "din",
    "este",
    "fi",
    "fie",
    "in",
    "la",
    "mai",
    "o",
    "pe",
    "pentru",
    "pot",
    "prin",
    "sa",
    "sau",
    "se",
    "si",
    "sunt",
    "un",
    "unde",
}

LIMITATION_TERMS = [
    "nu pot confirma",
    "sursele oficiale",
    "nu sunt suficiente",
    "nu pot garanta",
    "verifica",
    "verifică",
    "clarifica",
    "clarifică",
    "nu exista dovezi",
    "nu există dovezi",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the independent 1000-question UVT_Asist dataset through the local /chat endpoint."
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--category")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=202606)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-label")
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def normalize_backend_url(url: str) -> str:
    return str(url or DEFAULT_BACKEND_URL).strip().rstrip("/") or DEFAULT_BACKEND_URL


def resolve_dataset_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if path.exists():
        return path

    normalized_raw = raw_path.replace("\\", "/")
    fallback_candidates = []
    if normalized_raw.endswith("backend/evaluation/eval_qa_1000_independent.json"):
        fallback_candidates.append(DATA_EVALUATION_DATASET)
    if normalized_raw.endswith("backend/data/evaluation/eval_qa_1000_independent.json"):
        fallback_candidates.append(DEFAULT_DATASET)

    for candidate in fallback_candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Datasetul nu exista: {path}. Pune fisierul la {DATA_EVALUATION_DATASET.relative_to(REPO_ROOT)} "
        f"sau ruleaza cu --dataset <cale>."
    )


def load_dataset(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Datasetul trebuie sa fie un obiect JSON cu metadata si questions.")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Datasetul trebuie sa contina cheia 'questions' cu o lista.")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return metadata, [item for item in questions if isinstance(item, dict)]


def select_questions(questions: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = questions
    if args.category:
        category = str(args.category).casefold()
        selected = [item for item in selected if str(item.get("category", "")).casefold() == category]
    selected = list(selected)
    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(selected)
    if args.limit is not None:
        selected = selected[: max(0, args.limit)]
    return selected


def slugify(value: str | None, default: str = "run") -> str:
    text = normalize_text(value or "").replace(" ", "_")
    text = re.sub(r"[^a-z0-9_.-]+", "_", text).strip("_.-")
    return text or default


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9:/._-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) >= 3 and token not in ROMANIAN_STOPWORDS
    }


def term_present(text: str, term: str) -> bool:
    if "|" in term:
        return any(term_present(text, option) for option in term.split("|") if option.strip())
    return normalize_text(term) in normalize_text(text)


def terms_present(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term_present(text, term)]


def as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def expected_confidence_values(value: Any) -> set[str]:
    raw_items = as_string_list(value)
    values: set[str] = set()
    for item in raw_items:
        normalized = normalize_text(item)
        if normalized in {"medium_or_high", "medium high"}:
            values.update({"medium", "high"})
        elif normalized in {"low_or_medium", "low medium"}:
            values.update({"low", "medium"})
        elif normalized:
            values.add(normalized)
    return values


def confidence_matches(confidence: str, expected_confidence: Any) -> bool | None:
    expected = expected_confidence_values(expected_confidence)
    if not expected:
        return None
    return normalize_text(confidence) in expected


def url_contains(url: str, fragments: list[str]) -> bool:
    normalized_url = normalize_text(url)
    return any(normalize_text(fragment) in normalized_url for fragment in fragments if normalize_text(fragment))


def source_text_blob(answer: str, sources: list[dict[str, Any]]) -> str:
    source_parts: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_parts.extend(
            [
                str(source.get("title") or ""),
                str(source.get("url") or ""),
                str(source.get("page_type") or ""),
                str(source.get("excerpt") or ""),
                str(source.get("snippet") or ""),
            ]
        )
    return f"{answer} {' '.join(source_parts)}"


def source_page_type(source: dict[str, Any] | None) -> str:
    if not isinstance(source, dict):
        return ""
    return str(source.get("page_type") or source.get("type") or "")


def query_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload.get("query_profile")
    return profile if isinstance(profile, dict) else {}


def detected_intent_from_payload(payload: dict[str, Any]) -> str:
    profile = query_profile(payload)
    for key in ("intent", "detected_intent", "primary_intent"):
        value = profile.get(key)
        if value:
            return str(value)
    return str(payload.get("detected_intent") or "")


def evidence_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def evidence_answerable(evidence: dict[str, Any]) -> bool | None:
    if "answerable" not in evidence:
        return None
    return bool(evidence.get("answerable"))


def ideal_overlap_score(answer: str, ideal_answer: str) -> float:
    answer_tokens = content_tokens(answer)
    ideal_tokens = content_tokens(ideal_answer)
    if not answer_tokens or not ideal_tokens:
        return 0.0
    overlap = len(answer_tokens & ideal_tokens)
    return round((2 * overlap / (len(answer_tokens) + len(ideal_tokens))) * 100, 2)


def limitation_present(answer: str) -> bool:
    return any(term_present(answer, term) for term in LIMITATION_TERMS)


def score_answerable_question(
    question: dict[str, Any],
    answer: str,
    sources: list[dict[str, Any]],
    confidence: str,
    detected_intent: str,
) -> dict[str, Any]:
    expected_urls = as_string_list(question.get("expected_url_contains"))
    expected_page_type = str(question.get("expected_page_type") or "").strip()
    expected_intent = str(question.get("expected_intent") or "").strip()
    expected_confidence = question.get("expected_confidence")
    required_terms = as_string_list(question.get("required_terms"))
    forbidden_terms = as_string_list(question.get("forbidden_terms"))

    top1_url = str(sources[0].get("url") or "") if sources else ""
    top3_sources = sources[:3]
    top3_urls = [str(source.get("url") or "") for source in top3_sources]
    top1_page_type = source_page_type(sources[0]) if sources else ""

    earned = 0.0
    applicable = 0.0
    components: dict[str, Any] = {}

    if expected_urls:
        applicable += 25
        top1_match = url_contains(top1_url, expected_urls)
        top3_match = any(url_contains(url, expected_urls) for url in top3_urls)
        url_points = 25 if top1_match else 15 if top3_match else 0
        earned += url_points
        components.update(
            {
                "url_applicable": True,
                "top1_url_match": top1_match,
                "top3_url_match": top3_match,
                "url_points": url_points,
            }
        )
    else:
        components.update(
            {
                "url_applicable": False,
                "top1_url_match": None,
                "top3_url_match": None,
                "url_points": None,
            }
        )

    if expected_page_type:
        applicable += 15
        expected_page_type_norm = normalize_text(expected_page_type)
        page_types = [normalize_text(source_page_type(source)) for source in top3_sources]
        page_match = expected_page_type_norm in page_types or expected_page_type_norm == normalize_text(top1_page_type)
        earned += 15 if page_match else 0
        components.update({"page_type_applicable": True, "page_type_match": page_match})
    else:
        components.update({"page_type_applicable": False, "page_type_match": None})

    if expected_intent:
        applicable += 15
        intent_match = normalize_text(expected_intent) == normalize_text(detected_intent)
        earned += 15 if intent_match else 0
        components.update({"intent_applicable": True, "intent_match": intent_match})
    else:
        components.update({"intent_applicable": False, "intent_match": None})

    combined_text = source_text_blob(answer, sources)
    if required_terms:
        applicable += 20
        required_found = terms_present(combined_text, required_terms)
        coverage = len(required_found) / len(required_terms)
        required_points = 20 * coverage
        earned += required_points
        components.update(
            {
                "required_terms_applicable": True,
                "required_terms_found": required_found,
                "required_terms_total": len(required_terms),
                "required_terms_points": round(required_points, 2),
                "required_terms_coverage": round(coverage, 3),
            }
        )
    else:
        components.update(
            {
                "required_terms_applicable": False,
                "required_terms_found": [],
                "required_terms_total": 0,
                "required_terms_points": None,
                "required_terms_coverage": None,
            }
        )

    confidence_match = confidence_matches(confidence, expected_confidence)
    if confidence_match is not None:
        applicable += 10
        earned += 10 if confidence_match else 0
        components.update({"confidence_applicable": True, "confidence_match": confidence_match})
    else:
        components.update({"confidence_applicable": False, "confidence_match": None})

    forbidden_found = terms_present(answer, forbidden_terms)
    score = (earned / applicable * 100) if applicable else 100.0
    if forbidden_found:
        score -= 20

    components.update(
        {
            "forbidden_terms_found": forbidden_found,
            "forbidden_penalty": 20 if forbidden_found else 0,
            "score_applicable_points": round(applicable, 2),
            "score_earned_points": round(earned, 2),
        }
    )
    score = round(max(0.0, min(100.0, score)), 2)
    return {"score": score, "passed": score >= 70, "scoring": components}


def score_unanswerable_question(
    question: dict[str, Any],
    answer: str,
    sources: list[dict[str, Any]],
    confidence: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    forbidden_terms = as_string_list(question.get("forbidden_terms"))
    answerable = evidence_answerable(evidence)
    source_count = len(sources)

    confidence_low = normalize_text(confidence) == "low"
    no_evidence = answerable is False or source_count == 0
    has_limitation = limitation_present(answer)
    forbidden_found = terms_present(answer, forbidden_terms)

    earned = 0
    earned += 30 if confidence_low else 0
    earned += 25 if no_evidence else 0
    earned += 25 if has_limitation else 0
    earned += 20 if not forbidden_found else 0

    score = round(max(0.0, min(100.0, float(earned))), 2)
    scoring = {
        "confidence_low": confidence_low,
        "no_evidence_or_no_sources": no_evidence,
        "limitation_or_clarification_present": has_limitation,
        "forbidden_terms_found": forbidden_found,
        "expected_unanswerable_handled": confidence_low and no_evidence and has_limitation,
        "score_applicable_points": 100,
        "score_earned_points": earned,
    }
    return {"score": score, "passed": score >= 70, "scoring": scoring}


def compare_result(
    question: dict[str, Any],
    payload: dict[str, Any],
    status_code: int | None,
    latency_seconds: float,
    error: str | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    answer = str(payload.get("answer") or "")
    sources = [source for source in payload.get("sources", []) if isinstance(source, dict)]
    top3_sources = sources[:3]
    confidence = str(payload.get("confidence") or "unknown")
    evidence = evidence_from_payload(payload)
    detected_intent = detected_intent_from_payload(payload)
    should_have_answer = bool(question.get("should_have_answer", True))

    top1_url = str(sources[0].get("url") or "") if sources else ""
    top3_urls = [str(source.get("url") or "") for source in top3_sources]
    top1_page_type = source_page_type(sources[0]) if sources else ""

    if error:
        score_payload = {
            "score": 0.0,
            "passed": False,
            "scoring": {
                "url_applicable": bool(as_string_list(question.get("expected_url_contains"))),
                "top1_url_match": False,
                "top3_url_match": False,
                "confidence_match": False,
                "expected_unanswerable_handled": False,
                "forbidden_terms_found": [],
                "error_forced_failure": True,
            },
        }
    elif should_have_answer:
        score_payload = score_answerable_question(question, answer, sources, confidence, detected_intent)
    else:
        score_payload = score_unanswerable_question(question, answer, sources, confidence, evidence)

    scoring = score_payload["scoring"]
    confidence_match_value = scoring.get("confidence_match")
    if confidence_match_value is None:
        confidence_match_value = confidence_matches(confidence, question.get("expected_confidence"))
    result = {
        "id": str(question.get("id", "")),
        "category": str(question.get("category", "")),
        "faculty_id": str(question.get("faculty_id", "uvt")),
        "faculty_name": str(question.get("faculty_name", "")),
        "question": str(question.get("question", "")),
        "ideal_answer": str(question.get("ideal_answer", "")),
        "should_have_answer": should_have_answer,
        "answer_type": str(question.get("answer_type", "")),
        "expected_intent": str(question.get("expected_intent", "")),
        "expected_page_type": str(question.get("expected_page_type", "")),
        "expected_url_contains": as_string_list(question.get("expected_url_contains")),
        "expected_confidence": as_string_list(question.get("expected_confidence")),
        "required_terms": as_string_list(question.get("required_terms")),
        "forbidden_terms": as_string_list(question.get("forbidden_terms")),
        "difficulty": str(question.get("difficulty", "")),
        "notes": str(question.get("notes", "")),
        "answer": answer,
        "sources": sources,
        "source_count": len(sources),
        "top1_url": top1_url,
        "top3_urls": top3_urls,
        "top1_page_type": top1_page_type,
        "confidence": confidence,
        "confidence_score": payload.get("confidence_score"),
        "confidence_reason": str(payload.get("confidence_reason") or ""),
        "query_profile": query_profile(payload),
        "detected_intent": detected_intent,
        "retrieval_backend": str(payload.get("retrieval_backend") or ""),
        "generation_mode": str(payload.get("generation_mode") or ""),
        "evidence": evidence,
        "live_verified": bool(payload.get("live_verified")),
        "status_code": status_code,
        "latency_seconds": round(float(latency_seconds), 3),
        "error": str(error or ""),
        "score": score_payload["score"],
        "passed": bool(score_payload["passed"]),
        "ideal_overlap_score": ideal_overlap_score(answer, str(question.get("ideal_answer", ""))),
        "scoring": scoring,
        "url_applicable": bool(scoring.get("url_applicable")),
        "top1_url_match": scoring.get("top1_url_match"),
        "top3_url_match": scoring.get("top3_url_match"),
        "confidence_match": confidence_match_value,
        "expected_unanswerable_handled": bool(scoring.get("expected_unanswerable_handled")),
        "forbidden_terms_found": scoring.get("forbidden_terms_found", []),
    }
    return result


def check_backend(session: requests.Session, backend_url: str, timeout: float) -> dict[str, Any]:
    try:
        response = session.get(f"{backend_url}/health", timeout=min(timeout, 15))
        response.raise_for_status()
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            raise RuntimeError("Raspunsul /health nu este un obiect JSON.")
        return data
    except Exception as exc:
        raise RuntimeError(
            f"Backendul nu raspunde la {backend_url}/health. Porneste Flask manual cu: "
            f"python backend/app.py. Detalii: {exc}"
        ) from exc


def post_chat(
    session: requests.Session,
    backend_url: str,
    question: dict[str, Any],
    timeout: float,
) -> tuple[int | None, dict[str, Any], str | None]:
    payload = {
        "question": str(question.get("question") or ""),
        "faculty_id": str(question.get("faculty_id") or "uvt"),
        "history": [],
    }
    try:
        response = session.post(f"{backend_url}/chat", json=payload, timeout=timeout)
        status_code = response.status_code
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
            return status_code, data, "Raspunsul /chat nu este JSON valid."
        if not isinstance(data, dict):
            return status_code, {}, "Raspunsul /chat nu este un obiect JSON."
        if not response.ok:
            message = data.get("answer") or data.get("message") or response.reason
            return status_code, data, f"HTTP {status_code}: {message}"
        return status_code, data, None
    except Exception as exc:
        return None, {}, str(exc)


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * percent / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    value = ordered[lower] * (1 - weight) + ordered[upper] * weight
    return round(value, 3)


def distribution(results: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(item.get(field) or "unknown") for item in results)
    return dict(sorted(counts.items()))


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(item.get("score", 0)) for item in results]
    overlaps = [float(item.get("ideal_overlap_score", 0)) for item in results]
    latencies = [
        float(item.get("latency_seconds", 0))
        for item in results
        if isinstance(item.get("latency_seconds"), (int, float))
    ]
    url_applicable = [item for item in results if item.get("url_applicable")]
    confidence_applicable = [item for item in results if item.get("confidence_match") is not None]
    unanswerable = [item for item in results if not item.get("should_have_answer", True)]

    total = len(results)
    passed = sum(1 for item in results if item.get("passed"))
    return {
        "total_questions": total,
        "answered_count": sum(1 for item in results if str(item.get("answer") or "").strip()),
        "passed_count": passed,
        "failed_count": total - passed,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "average_score": round(mean(scores), 2) if scores else 0.0,
        "median_score": round(median(scores), 2) if scores else 0.0,
        "average_ideal_overlap_score": round(mean(overlaps), 2) if overlaps else 0.0,
        "median_ideal_overlap_score": round(median(overlaps), 2) if overlaps else 0.0,
        "top1_url_match_count": sum(1 for item in url_applicable if item.get("top1_url_match")),
        "top1_url_match_denominator": len(url_applicable),
        "top3_url_match_count": sum(1 for item in url_applicable if item.get("top3_url_match")),
        "top3_url_match_denominator": len(url_applicable),
        "confidence_match_count": sum(1 for item in confidence_applicable if item.get("confidence_match")),
        "confidence_match_denominator": len(confidence_applicable),
        "expected_unanswerable_handled_count": sum(
            1 for item in unanswerable if item.get("expected_unanswerable_handled")
        ),
        "expected_unanswerable_denominator": len(unanswerable),
        "average_latency": round(mean(latencies), 3) if latencies else 0.0,
        "median_latency": round(median(latencies), 3) if latencies else 0.0,
        "p75_latency": percentile(latencies, 75),
        "p90_latency": percentile(latencies, 90),
        "p95_latency": percentile(latencies, 95),
        "max_latency": round(max(latencies), 3) if latencies else 0.0,
        "error_count": sum(1 for item in results if item.get("error")),
        "generation_mode_distribution": distribution(results, "generation_mode"),
        "retrieval_backend_distribution": distribution(results, "retrieval_backend"),
        "confidence_distribution": distribution(results, "confidence"),
    }


def calculate_category_metrics(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        grouped[str(item.get("category") or "uncategorized")].append(item)
    return {category: calculate_metrics(items) for category, items in sorted(grouped.items())}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "category",
        "faculty_id",
        "should_have_answer",
        "answer_type",
        "difficulty",
        "question",
        "ideal_answer",
        "answer",
        "score",
        "passed",
        "ideal_overlap_score",
        "confidence",
        "confidence_score",
        "confidence_match",
        "source_count",
        "top1_url",
        "top3_urls",
        "top1_page_type",
        "top1_url_match",
        "top3_url_match",
        "expected_intent",
        "detected_intent",
        "expected_page_type",
        "expected_url_contains",
        "expected_confidence",
        "required_terms",
        "forbidden_terms_found",
        "retrieval_backend",
        "generation_mode",
        "live_verified",
        "status_code",
        "latency_seconds",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in results:
            writer.writerow({field: csv_value(item.get(field, "")) for field in fields})


def markdown_metric_table(metrics: dict[str, Any]) -> str:
    rows = [
        ("Total intrebari", metrics["total_questions"]),
        ("Raspunsuri generate", metrics["answered_count"]),
        ("Passed", metrics["passed_count"]),
        ("Failed", metrics["failed_count"]),
        ("Pass rate", f"{metrics['pass_rate']}%"),
        ("Scor mediu", metrics["average_score"]),
        ("Scor median", metrics["median_score"]),
        ("Overlap ideal mediu", metrics["average_ideal_overlap_score"]),
        ("Top-1 URL match", f"{metrics['top1_url_match_count']}/{metrics['top1_url_match_denominator']}"),
        ("Top-3 URL match", f"{metrics['top3_url_match_count']}/{metrics['top3_url_match_denominator']}"),
        (
            "Confidence match",
            f"{metrics['confidence_match_count']}/{metrics['confidence_match_denominator']}",
        ),
        (
            "Intrebari fara raspuns sigur tratate",
            f"{metrics['expected_unanswerable_handled_count']}/{metrics['expected_unanswerable_denominator']}",
        ),
        ("Erori", metrics["error_count"]),
    ]
    lines = ["| Metrica | Valoare |", "| --- | ---: |"]
    lines.extend(f"| {name} | {value} |" for name, value in rows)
    return "\n".join(lines)


def markdown_category_table(category_metrics: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Categorie | Total | Pass rate | Scor mediu | Top-1 URL | Top-3 URL | Latenta medie | Erori |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, metrics in category_metrics.items():
        lines.append(
            "| "
            f"{category} | "
            f"{metrics['total_questions']} | "
            f"{metrics['pass_rate']}% | "
            f"{metrics['average_score']} | "
            f"{metrics['top1_url_match_count']}/{metrics['top1_url_match_denominator']} | "
            f"{metrics['top3_url_match_count']}/{metrics['top3_url_match_denominator']} | "
            f"{metrics['average_latency']}s | "
            f"{metrics['error_count']} |"
        )
    return "\n".join(lines)


def markdown_latency_table(metrics: dict[str, Any]) -> str:
    rows = [
        ("Medie", metrics["average_latency"]),
        ("Mediana", metrics["median_latency"]),
        ("P75", metrics["p75_latency"]),
        ("P90", metrics["p90_latency"]),
        ("P95", metrics["p95_latency"]),
        ("Max", metrics["max_latency"]),
    ]
    lines = ["| Latenta | Secunde |", "| --- | ---: |"]
    lines.extend(f"| {name} | {value} |" for name, value in rows)
    return "\n".join(lines)


def markdown_distribution(title: str, values: dict[str, int]) -> str:
    lines = [f"### {title}", "", "| Valoare | Numar |", "| --- | ---: |"]
    if values:
        lines.extend(f"| {key} | {count} |" for key, count in values.items())
    else:
        lines.append("| - | 0 |")
    return "\n".join(lines)


def write_markdown_summary(
    path: Path,
    run_metadata: dict[str, Any],
    global_metrics: dict[str, Any],
    category_metrics: dict[str, dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    failures = sorted((item for item in results if not item.get("passed")), key=lambda item: item.get("score", 0))[:20]
    slowest = sorted(results, key=lambda item: item.get("latency_seconds", 0), reverse=True)[:10]

    lines = [
        "# Evaluare Q&A 1000 independent",
        "",
        "## Metadata run",
        "",
        "| Cheie | Valoare |",
        "| --- | --- |",
    ]
    for key, value in run_metadata.items():
        lines.append(f"| {key} | {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value} |")

    lines.extend(
        [
            "",
            "## Rezumat global",
            "",
            markdown_metric_table(global_metrics),
            "",
            "## Rezumat pe categorii",
            "",
            markdown_category_table(category_metrics),
            "",
            "## Latente",
            "",
            markdown_latency_table(global_metrics),
            "",
            "## Top 20 esecuri",
            "",
            "| ID | Categorie | Scor | Confidence | Top-1 URL | Eroare |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    if failures:
        for item in failures:
            lines.append(
                "| "
                f"{item.get('id', '')} | "
                f"{item.get('category', '')} | "
                f"{item.get('score', 0)} | "
                f"{item.get('confidence', '')} | "
                f"{item.get('top1_url', '')} | "
                f"{item.get('error', '')} |"
            )
    else:
        lines.append("| - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## Top 10 cele mai lente intrebari",
            "",
            "| ID | Categorie | Latenta | Scor | Top-1 URL |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for item in slowest:
        lines.append(
            "| "
            f"{item.get('id', '')} | "
            f"{item.get('category', '')} | "
            f"{item.get('latency_seconds', 0)}s | "
            f"{item.get('score', 0)} | "
            f"{item.get('top1_url', '')} |"
        )

    lines.extend(
        [
            "",
            markdown_distribution("Distributie generation_mode", global_metrics["generation_mode_distribution"]),
            "",
            markdown_distribution("Distributie retrieval_backend", global_metrics["retrieval_backend_distribution"]),
            "",
            markdown_distribution("Distributie confidence", global_metrics["confidence_distribution"]),
            "",
            "## Nota metodologica",
            "",
            (
                "Scorul principal nu compara textul exact cu ideal_answer. Ideal_answer este tratat ca rubrica, "
                "iar evaluatorul foloseste semnale verificabile: potrivirea surselor asteptate, page_type, intent, "
                "termeni obligatorii, confidence si penalizari pentru termeni interzisi. "
                "ideal_overlap_score este salvat doar informativ."
            ),
            "",
            (
                "Rezultatele reprezinta performanta sistemului pe setul independent definit in proiect. "
                "Ele nu sunt o garantie universala pentru toate intrebarile posibile."
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def checkpoint_path(output_dir: Path, run_slug: str) -> Path:
    return output_dir / f"qa1000_independent_checkpoint_{run_slug}.json"


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(path, payload)


def output_paths(output_dir: Path, run_label: str | None) -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = slugify(run_label, default="") if run_label else ""
    suffix = f"{label}_{timestamp}" if label else timestamp
    return (
        output_dir / f"qa1000_independent_results_{suffix}.json",
        output_dir / f"qa1000_independent_results_{suffix}.csv",
        output_dir / f"qa1000_independent_summary_{suffix}.md",
    )


def run_evaluation(args: argparse.Namespace) -> int:
    if requests is None:
        print("Lipseste pachetul requests. Ruleaza: pip install -r backend/requirements.txt", file=sys.stderr)
        return 2

    dataset_path = resolve_dataset_path(args.dataset)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    backend_url = normalize_backend_url(args.backend_url)
    metadata, all_questions = load_dataset(dataset_path)
    questions = select_questions(all_questions, args)
    if not questions:
        print("Nu exista intrebari de evaluat pentru filtrele selectate.", file=sys.stderr)
        return 1

    run_slug = slugify(args.run_label or dataset_path.stem)
    checkpoint = checkpoint_path(output_dir, run_slug)
    checkpoint_payload = load_checkpoint(checkpoint) if args.resume else {}
    results = [item for item in checkpoint_payload.get("results", []) if isinstance(item, dict)]
    completed_ids = {str(item.get("id", "")) for item in results if str(item.get("id", ""))}

    with requests.Session() as session:
        health = check_backend(session, backend_url, args.timeout)
        print(f"Backend OK: {backend_url}/health")

        run_metadata = {
            "dataset": str(dataset_path.relative_to(REPO_ROOT) if dataset_path.is_relative_to(REPO_ROOT) else dataset_path),
            "dataset_metadata": metadata,
            "backend_url": backend_url,
            "run_label": args.run_label or "",
            "category": args.category or "",
            "limit": args.limit,
            "shuffle": bool(args.shuffle),
            "seed": args.seed,
            "timeout": args.timeout,
            "delay_ms": args.delay_ms,
            "resume": bool(args.resume),
            "checkpoint": str(checkpoint.relative_to(REPO_ROOT) if checkpoint.is_relative_to(REPO_ROOT) else checkpoint),
            "health_status": health,
            "started_at": checkpoint_payload.get("started_at")
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        if args.resume and results:
            print(f"Resume activ: {len(results)} rezultate incarcate din checkpoint.")

        evaluated_since_checkpoint = 0
        total = len(questions)
        for index, question in enumerate(questions, start=1):
            question_id = str(question.get("id", ""))
            if question_id and question_id in completed_ids:
                continue

            start = time.perf_counter()
            status_code, payload, error = post_chat(session, backend_url, question, args.timeout)
            latency = time.perf_counter() - start
            result = compare_result(question, payload, status_code, latency, error)
            results.append(result)
            if question_id:
                completed_ids.add(question_id)

            evaluated_since_checkpoint += 1
            status = "PASS" if result["passed"] else "FAIL"
            print(
                f"[{index}/{total}] {status} {result['id']} "
                f"score={result['score']} latency={result['latency_seconds']}s"
            )

            if args.checkpoint_every > 0 and evaluated_since_checkpoint >= args.checkpoint_every:
                save_checkpoint(
                    checkpoint,
                    {
                        "run_metadata": run_metadata,
                        "results": results,
                        "started_at": run_metadata["started_at"],
                    },
                )
                evaluated_since_checkpoint = 0
                print(f"Checkpoint salvat: {checkpoint}")

            if args.delay_ms > 0:
                time.sleep(args.delay_ms / 1000)

    global_metrics = calculate_metrics(results)
    category_metrics = calculate_category_metrics(results)
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_metadata["finished_at"] = finished_at

    json_path, csv_path, md_path = output_paths(output_dir, args.run_label)
    payload = {
        "run_metadata": run_metadata,
        "global_metrics": global_metrics,
        "category_metrics": category_metrics,
        "results": results,
    }
    write_json(json_path, payload)
    write_csv(csv_path, results)
    write_markdown_summary(md_path, run_metadata, global_metrics, category_metrics, results)
    save_checkpoint(
        checkpoint,
        {
            "run_metadata": run_metadata,
            "results": results,
            "started_at": run_metadata["started_at"],
            "completed": True,
        },
    )

    print("\nEvaluare finalizata.")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    print(f"Markdown: {md_path}")
    print(f"Pass rate: {global_metrics['pass_rate']}%")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_evaluation(args)
    except KeyboardInterrupt:
        print("\nEvaluare intrerupta de utilizator.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

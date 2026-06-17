from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - depends on local environment.
    requests = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.rag_eval import build_evaluation_result, calculate_metrics

DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"
DEFAULT_QUESTIONS = BACKEND_DIR / "evaluation" / "eval_questions.json"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate UVT_Asist RAG answers through the /chat endpoint.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--category")
    return parser.parse_args()


def load_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list):
        raise ValueError("Questions file must contain a JSON list or an object with a 'questions' list.")
    return [item for item in questions if isinstance(item, dict)]


def filter_questions(questions: list[dict], category: str | None, limit: int | None) -> list[dict]:
    if category:
        questions = [item for item in questions if str(item.get("category", "")).lower() == category.lower()]
    if limit is not None:
        questions = questions[:max(0, limit)]
    return questions


def normalize_backend_url(url: str) -> str:
    return str(url or DEFAULT_BACKEND_URL).strip().rstrip("/") or DEFAULT_BACKEND_URL


def check_backend(session: requests.Session, backend_url: str, timeout: float) -> tuple[bool, str]:
    try:
        response = session.get(f"{backend_url}/health", timeout=min(timeout, 10))
        response.raise_for_status()
        return True, ""
    except requests.RequestException as exc:
        return False, (
            f"Backend-ul nu răspunde la {backend_url}/health. "
            "Pornește-l cu: python backend/app.py. "
            f"Detalii: {exc}"
        )


def post_chat(session: requests.Session, backend_url: str, question: dict, timeout: float) -> dict:
    payload = {
        "question": question.get("question", ""),
        "faculty_id": question.get("faculty_id", "uvt"),
        "history": [],
    }
    response = session.post(f"{backend_url}/chat", json=payload, timeout=timeout)
    data = response.json() if response.content else {}
    if not response.ok:
        message = data.get("answer") or data.get("message") or response.reason
        raise RuntimeError(f"HTTP {response.status_code}: {message}")
    if not isinstance(data, dict):
        raise RuntimeError("Backend response is not a JSON object.")
    return data


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_csv(path: Path, results: list[dict]) -> None:
    fields = [
        "id",
        "category",
        "faculty_id",
        "question",
        "should_have_answer",
        "confidence",
        "confidence_score",
        "matched_faculty_id",
        "retrieval_backend",
        "generation_mode",
        "live_verified",
        "latency_seconds",
        "top1_url_match",
        "top3_url_match",
        "expected_unanswerable_handled",
        "error",
        "top_source_url",
        "top_source_title",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({field: result.get(field, "") for field in fields})


def write_markdown_summary(path: Path, created_at: str, backend_url: str, metrics: dict, results: list[dict]) -> None:
    failed = [result for result in results if result.get("error")]
    missed_top3 = [
        result
        for result in results
        if result.get("expected_url_contains") and not result.get("top3_url_match") and not result.get("error")
    ]
    unhandled = [
        result
        for result in results
        if result.get("should_have_answer") is False
        and not result.get("expected_unanswerable_handled")
        and not result.get("error")
    ]

    lines = [
        "# UVT_Asist RAG Evaluation Summary",
        "",
        f"- Created at: `{created_at}`",
        f"- Backend: `{backend_url}`",
        f"- Total questions: `{metrics['total_questions']}`",
        f"- Answered: `{metrics['answered_count']}`",
        f"- Low confidence: `{metrics['low_confidence_count']}`",
        f"- Top-1 URL matches: `{metrics['top1_url_match_count']}`",
        f"- Top-3 URL matches: `{metrics['top3_url_match_count']}`",
        f"- Expected unanswerable handled: `{metrics['expected_unanswerable_handled_count']}`",
        f"- Average latency: `{metrics['average_latency_seconds']}s`",
        f"- Median latency: `{metrics['median_latency_seconds']}s`",
        "",
    ]

    if failed:
        lines.extend(["## Errors", "", "| ID | Error |", "| --- | --- |"])
        lines.extend(f"| {item['id']} | {str(item.get('error', '')).replace('|', '/')} |" for item in failed[:25])
        lines.append("")

    if missed_top3:
        lines.extend(["## Expected URL Misses", "", "| ID | Top Source | Expected |", "| --- | --- | --- |"])
        for item in missed_top3[:25]:
            expected = ", ".join(item.get("expected_url_contains", []))
            lines.append(f"| {item['id']} | {item.get('top_source_url', '')} | {expected} |")
        lines.append("")

    if unhandled:
        lines.extend(["## Unanswerable Not Handled", "", "| ID | Confidence | Top Source |", "| --- | --- | --- |"])
        for item in unhandled[:25]:
            lines.append(f"| {item['id']} | {item.get('confidence', '')} | {item.get('top_source_url', '')} |")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_summary(metrics: dict, output_paths: dict[str, Path]) -> None:
    print("\nRezumat evaluare RAG")
    print(f"- Întrebări evaluate: {metrics['total_questions']}")
    print(f"- Răspunsuri primite: {metrics['answered_count']}")
    print(f"- Confidence low: {metrics['low_confidence_count']}")
    print(f"- Top-1 URL match: {metrics['top1_url_match_count']}")
    print(f"- Top-3 URL match: {metrics['top3_url_match_count']}")
    print(f"- Întrebări fără răspuns sigur tratate corect: {metrics['expected_unanswerable_handled_count']}")
    print(f"- Latență medie: {metrics['average_latency_seconds']}s")
    print(f"- Latență mediană: {metrics['median_latency_seconds']}s")
    print(f"- JSON: {output_paths['json']}")
    print(f"- CSV: {output_paths['csv']}")
    print(f"- Markdown: {output_paths['markdown']}")


def main() -> int:
    if requests is None:
        print("ERROR: Pachetul requests nu este instalat. Rulează: pip install -r backend/requirements.txt")
        return 2

    args = parse_args()
    backend_url = normalize_backend_url(args.backend_url)
    questions_path = Path(args.questions)
    out_dir = Path(args.out_dir)

    try:
        questions = filter_questions(load_questions(questions_path), args.category, args.limit)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: Nu pot citi întrebările de evaluare din {questions_path}: {exc}")
        return 2

    if not questions:
        print("WARNING: Nu există întrebări de evaluat pentru filtrele date.")
        return 0

    session = requests.Session()
    backend_ok, backend_error = check_backend(session, backend_url, args.timeout)
    if not backend_ok:
        print(f"ERROR: {backend_error}")
        return 2

    results = []
    total = len(questions)
    for index, question in enumerate(questions, start=1):
        start = time.perf_counter()
        payload = {}
        error = None
        try:
            payload = post_chat(session, backend_url, question, args.timeout)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            error = str(exc)
        latency = time.perf_counter() - start
        result = build_evaluation_result(question, payload, latency, error=error)
        results.append(result)
        status = "ERROR" if error else "OK"
        print(f"[{index}/{total}] {status} {result['id']} ({result['latency_seconds']}s)")

    metrics = calculate_metrics(results)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "json": out_dir / f"eval_results_{timestamp}.json",
        "csv": out_dir / f"eval_results_{timestamp}.csv",
        "markdown": out_dir / f"eval_summary_{timestamp}.md",
    }
    write_json(output_paths["json"], {
        "created_at": created_at,
        "backend_url": backend_url,
        "questions_file": str(questions_path),
        "filters": {"category": args.category, "limit": args.limit},
        "summary": metrics,
        "results": results,
    })
    write_csv(output_paths["csv"], results)
    write_markdown_summary(output_paths["markdown"], created_at, backend_url, metrics, results)
    print_summary(metrics, output_paths)
    return 1 if any(result.get("error") for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

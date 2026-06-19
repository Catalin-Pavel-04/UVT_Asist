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
except ModuleNotFoundError:  # pragma: no cover
    requests = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.qa_compare import calculate_qa_metrics, compare_qa_result

DEFAULT_BACKEND_URL = "http://127.0.0.1:5000"
DEFAULT_QUESTIONS = BACKEND_DIR / "evaluation" / "eval_qa_100.json"
DEFAULT_OUT_DIR = BACKEND_DIR / "data" / "evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare /chat answers with a 100-question ideal Q&A rubric.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--category")
    return parser.parse_args()


def load_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    questions = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(questions, list):
        raise ValueError("Questions file must be a JSON list or an object with a questions list.")
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
            "Pentru diagnostic rulează: python backend/scripts/demo_check.py. "
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
        "qa_score",
        "passed",
        "confidence",
        "confidence_score",
        "confidence_match",
        "top1_url_match",
        "top3_url_match",
        "required_phrase_coverage",
        "ideal_token_coverage",
        "expected_unanswerable_handled",
        "latency_seconds",
        "retrieval_backend",
        "generation_mode",
        "top_source_url",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow({field: result.get(field, "") for field in fields})


def write_markdown(path: Path, created_at: str, backend_url: str, metrics: dict, results: list[dict]) -> None:
    weakest = sorted(results, key=lambda item: int(item.get("qa_score", 0)))[:20]
    lines = [
        "# UVT_Asist 100 Q&A Evaluation",
        "",
        f"- Created at: `{created_at}`",
        f"- Backend: `{backend_url}`",
        f"- Total questions: `{metrics['total_questions']}`",
        f"- Passed: `{metrics['passed_count']}`",
        f"- Failed: `{metrics['failed_count']}`",
        f"- Average QA score: `{metrics['average_qa_score']}`",
        f"- Median QA score: `{metrics['median_qa_score']}`",
        f"- Top-1 URL matches: `{metrics['top1_url_match_count']}`",
        f"- Top-3 URL matches: `{metrics['top3_url_match_count']}`",
        f"- Confidence matches: `{metrics['confidence_match_count']}`",
        f"- Expected unanswerable handled: `{metrics['expected_unanswerable_handled_count']}`",
        f"- Average latency: `{metrics['average_latency_seconds']}s`",
        f"- Median latency: `{metrics['median_latency_seconds']}s`",
        "",
        "## Weakest Results",
        "",
        "| ID | Score | Top Source | Required Coverage | Notes |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for item in weakest:
        notes = []
        if not item.get("top3_url_match"):
            notes.append("source miss")
        if item.get("required_phrase_coverage", 1) < 0.75:
            notes.append("keyword miss")
        if not item.get("confidence_match"):
            notes.append("confidence")
        if item.get("forbidden_phrases_found"):
            notes.append("forbidden phrase")
        if item.get("error"):
            notes.append("error")
        lines.append(
            f"| {item['id']} | {item.get('qa_score', 0)} | {item.get('top_source_url', '')} | "
            f"{item.get('required_phrase_coverage', 0)} | {', '.join(notes)} |"
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_summary(metrics: dict, output_paths: dict[str, Path]) -> None:
    print("\nRezumat evaluare Q&A")
    print(f"- Întrebări evaluate: {metrics['total_questions']}")
    print(f"- Trecute: {metrics['passed_count']}")
    print(f"- Eșuate: {metrics['failed_count']}")
    print(f"- Scor mediu Q&A: {metrics['average_qa_score']}")
    print(f"- Top-1 URL match: {metrics['top1_url_match_count']}")
    print(f"- Top-3 URL match: {metrics['top3_url_match_count']}")
    print(f"- Confidence match: {metrics['confidence_match_count']}")
    print(f"- Latență medie: {metrics['average_latency_seconds']}s")
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
        print(f"ERROR: Nu pot citi întrebările Q&A din {questions_path}: {exc}")
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
        result = compare_qa_result(question, payload, time.perf_counter() - start, error)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{index}/{total}] {status} {result['id']} score={result['qa_score']} "
            f"({result['latency_seconds']}s)",
            flush=True,
        )

    metrics = calculate_qa_metrics(results)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "json": out_dir / f"qa_eval_results_{timestamp}.json",
        "csv": out_dir / f"qa_eval_results_{timestamp}.csv",
        "markdown": out_dir / f"qa_eval_summary_{timestamp}.md",
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
    write_markdown(output_paths["markdown"], created_at, backend_url, metrics, results)
    print_summary(metrics, output_paths)
    return 1 if metrics["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

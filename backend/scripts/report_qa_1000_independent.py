from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "evaluation"
DEFAULT_DATA_OUT_DIR = BACKEND_DIR / "data" / "evaluation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build thesis-ready Markdown, LaTeX, and CSV reports from a QA1000 evaluation JSON."
    )
    parser.add_argument("--input", required=True, help="Path to qa1000_independent_results_<timestamp>.json")
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_DATA_OUT_DIR))
    return parser.parse_args()


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else REPO_ROOT / path


def load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Nu exista fisierul de input: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Fisierul de input trebuie sa fie un obiect JSON.")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Fisierul de input trebuie sa contina cheia 'results' cu o lista.")
    payload.setdefault("run_metadata", {})
    payload.setdefault("global_metrics", {})
    payload.setdefault("category_metrics", {})
    return payload


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def percentage(count: Any, denominator: Any) -> str:
    try:
        count_value = float(count)
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return "n/a"
    if denominator_value <= 0:
        return "n/a"
    return f"{count_value / denominator_value * 100:.2f}%"


def metric_value(metrics: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return default


def category_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("category") or "uncategorized") for item in results).items()))


def distribution_from_metrics(metrics: dict[str, Any], key: str, results: list[dict[str, Any]], field: str) -> dict[str, int]:
    value = metrics.get(key)
    if isinstance(value, dict):
        return dict(sorted((str(item_key), int(item_value)) for item_key, item_value in value.items()))
    return dict(sorted(Counter(str(item.get(field) or "unknown") for item in results).items()))


def latency_rows(metrics: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        ("Medie", metric_value(metrics, "average_latency", "average_latency_seconds", default=0)),
        ("Mediana", metric_value(metrics, "median_latency", "median_latency_seconds", default=0)),
        ("P75", metric_value(metrics, "p75_latency", default=0)),
        ("P90", metric_value(metrics, "p90_latency", default=0)),
        ("P95", metric_value(metrics, "p95_latency", default=0)),
        ("Max", metric_value(metrics, "max_latency", default=0)),
    ]


def markdown_table(headers: list[str], rows: list[list[Any]], align_right: set[int] | None = None) -> str:
    align_right = align_right or set()
    separator = ["---:" if index in align_right else "---" for index in range(len(headers))]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def global_metric_rows(metrics: dict[str, Any]) -> list[list[Any]]:
    top1_count = metric_value(metrics, "top1_url_match_count", default=0)
    top1_denominator = metric_value(metrics, "top1_url_match_denominator", default=0)
    top3_count = metric_value(metrics, "top3_url_match_count", default=0)
    top3_denominator = metric_value(metrics, "top3_url_match_denominator", default=0)
    confidence_count = metric_value(metrics, "confidence_match_count", default=0)
    confidence_denominator = metric_value(metrics, "confidence_match_denominator", default=0)
    return [
        ["Total intrebari", metric_value(metrics, "total_questions", default=0)],
        ["Raspunsuri generate", metric_value(metrics, "answered_count", default=0)],
        ["Passed", metric_value(metrics, "passed_count", default=0)],
        ["Failed", metric_value(metrics, "failed_count", default=0)],
        ["Pass rate", f"{metric_value(metrics, 'pass_rate', default=0)}%"],
        ["Scor mediu", metric_value(metrics, "average_score", "average_qa_score", default=0)],
        ["Scor median", metric_value(metrics, "median_score", "median_qa_score", default=0)],
        ["Overlap ideal mediu", metric_value(metrics, "average_ideal_overlap_score", default=0)],
        ["Top-1 URL match", f"{top1_count}/{top1_denominator} ({percentage(top1_count, top1_denominator)})"],
        ["Top-3 URL match", f"{top3_count}/{top3_denominator} ({percentage(top3_count, top3_denominator)})"],
        ["Confidence match", f"{confidence_count}/{confidence_denominator} ({percentage(confidence_count, confidence_denominator)})"],
        ["Erori", metric_value(metrics, "error_count", default=0)],
    ]


def category_rows(category_metrics: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for category, metrics in sorted(category_metrics.items()):
        if not isinstance(metrics, dict):
            continue
        top1_count = metric_value(metrics, "top1_url_match_count", default=0)
        top1_denominator = metric_value(metrics, "top1_url_match_denominator", default=0)
        top3_count = metric_value(metrics, "top3_url_match_count", default=0)
        top3_denominator = metric_value(metrics, "top3_url_match_denominator", default=0)
        rows.append(
            [
                category,
                metric_value(metrics, "total_questions", default=0),
                f"{metric_value(metrics, 'pass_rate', default=0)}%",
                metric_value(metrics, "average_score", "average_qa_score", default=0),
                f"{top1_count}/{top1_denominator}",
                f"{top3_count}/{top3_denominator}",
                metric_value(metrics, "average_latency", "average_latency_seconds", default=0),
                metric_value(metrics, "error_count", default=0),
            ]
        )
    return rows


def distribution_rows(distribution: dict[str, int]) -> list[list[Any]]:
    if not distribution:
        return [["-", 0]]
    return [[key, value] for key, value in sorted(distribution.items(), key=lambda item: (-item[1], item[0]))]


def failure_rows(results: list[dict[str, Any]], limit: int = 20) -> list[list[Any]]:
    failures = [item for item in results if not item.get("passed")]
    failures.sort(key=lambda item: (float(item.get("score") or 0), -float(item.get("latency_seconds") or 0)))
    rows: list[list[Any]] = []
    for item in failures[:limit]:
        rows.append(
            [
                item.get("id", ""),
                item.get("category", ""),
                item.get("score", 0),
                item.get("confidence", ""),
                item.get("top1_url", ""),
                item.get("error", ""),
            ]
        )
    return rows or [["-", "-", "-", "-", "-", "-"]]


def slowest_rows(results: list[dict[str, Any]], limit: int = 10) -> list[list[Any]]:
    ordered = sorted(results, key=lambda item: float(item.get("latency_seconds") or 0), reverse=True)
    rows: list[list[Any]] = []
    for item in ordered[:limit]:
        rows.append(
            [
                item.get("id", ""),
                item.get("category", ""),
                item.get("latency_seconds", 0),
                item.get("score", 0),
                item.get("generation_mode", ""),
                item.get("top1_url", ""),
            ]
        )
    return rows or [["-", "-", "-", "-", "-", "-"]]


def write_markdown_report(
    path: Path,
    payload: dict[str, Any],
    category_distribution: dict[str, int],
    confidence_distribution: dict[str, int],
    retrieval_distribution: dict[str, int],
    generation_distribution: dict[str, int],
) -> None:
    metadata = payload["run_metadata"]
    metrics = payload["global_metrics"]
    category_metrics = payload["category_metrics"]
    results = payload["results"]

    dataset_metadata = metadata.get("dataset_metadata") if isinstance(metadata.get("dataset_metadata"), dict) else {}
    metadata_rows = [
        ["Dataset", metadata.get("dataset", "")],
        ["Run label", metadata.get("run_label", "")],
        ["Backend URL", metadata.get("backend_url", "")],
        ["Started at", metadata.get("started_at", "")],
        ["Finished at", metadata.get("finished_at", "")],
        ["Total in fisierul evaluat", metrics.get("total_questions", len(results))],
    ]
    for key, value in sorted(dataset_metadata.items()):
        metadata_rows.append([f"Dataset metadata: {key}", json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])

    lines = [
        "# Raport evaluare Q&A 1000 independent",
        "",
        "## Scopul evaluarii",
        "",
        (
            "Acest raport sintetizeaza rezultatele evaluatorului independent de 1000 de intrebari pentru UVT_Asist. "
            "Evaluatorul trimite intrebarile catre backendul local si compara raspunsurile cu rubricile definite in dataset."
        ),
        "",
        "## Descrierea datasetului",
        "",
        markdown_table(["Camp", "Valoare"], metadata_rows),
        "",
        "## Distributia pe categorii",
        "",
        markdown_table(["Categorie", "Numar intrebari"], distribution_rows(category_distribution), align_right={1}),
        "",
        "## Metodologia de scoring",
        "",
        (
            "Scorul principal nu compara raspunsul text-la-text cu ideal_answer. Pentru intrebarile cu raspuns asteptat, "
            "scorul combina potrivirea URL-urilor Top-1/Top-3, page_type, intent, required_terms, confidence si penalizarea "
            "pentru forbidden_terms. Pentru intrebarile fara raspuns sigur, scorul favorizeaza confidence low, lipsa dovezilor "
            "suficiente si formularea prudenta de refuz sau clarificare. ideal_overlap_score ramane doar metric informativ."
        ),
        "",
        "## Rezultate globale",
        "",
        markdown_table(["Metrica", "Valoare"], global_metric_rows(metrics), align_right={1}),
        "",
        "## Rezultate pe categorii",
        "",
        markdown_table(
            ["Categorie", "Total", "Pass rate", "Scor mediu", "Top-1 URL", "Top-3 URL", "Latenta medie", "Erori"],
            category_rows(category_metrics),
            align_right={1, 2, 3, 4, 5, 6, 7},
        ),
        "",
        "## Latente",
        "",
        markdown_table(["Metrica", "Secunde"], [[name, value] for name, value in latency_rows(metrics)], align_right={1}),
        "",
        "## Distributie confidence",
        "",
        markdown_table(["Confidence", "Numar"], distribution_rows(confidence_distribution), align_right={1}),
        "",
        "## Distributie retrieval_backend",
        "",
        markdown_table(["Retrieval backend", "Numar"], distribution_rows(retrieval_distribution), align_right={1}),
        "",
        "## Distributie generation_mode",
        "",
        markdown_table(["Generation mode", "Numar"], distribution_rows(generation_distribution), align_right={1}),
        "",
        "## Top esecuri",
        "",
        markdown_table(["ID", "Categorie", "Scor", "Confidence", "Top-1 URL", "Eroare"], failure_rows(results), align_right={2}),
        "",
        "## Cele mai lente intrebari",
        "",
        markdown_table(
            ["ID", "Categorie", "Latenta", "Scor", "Generation mode", "Top-1 URL"],
            slowest_rows(results),
            align_right={2, 3},
        ),
        "",
        "## Interpretare prudenta",
        "",
        (
            "Rezultatele trebuie interpretate ca performanta pe setul definit de evaluare, nu ca garantie universala. "
            "Setul acopera scenarii reprezentative, dar nu toate formularile posibile ale studentilor."
        ),
        "",
        "## Limitari",
        "",
        "- Scorul automat foloseste rubrici si semnale observabile, nu o evaluare umana completa.",
        "- Rezultatele depind de starea indexului local, de modelele Ollama configurate si de disponibilitatea Qdrant.",
        "- Latentele sunt masurate in mediul local in care a fost rulata evaluarea.",
        "- Intrebarile fara raspuns sigur sunt evaluate separat pentru a recompensa refuzul prudent in locul raspunsurilor speculative.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def latex_table(caption: str, label: str, columns: str, headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\caption{{{latex_escape(caption)}}}",
        rf"\label{{{latex_escape(label)}}}",
        rf"\begin{{tabular}}{{{columns}}}",
        r"\hline",
        " & ".join(latex_escape(header) for header in headers) + r" \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(" & ".join(latex_escape(value) for value in row) + r" \\")
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def write_latex_tables(
    path: Path,
    metrics: dict[str, Any],
    category_metrics: dict[str, Any],
    retrieval_distribution: dict[str, int],
    generation_distribution: dict[str, int],
) -> None:
    content = [
        "% Tabele generate automat din rezultatele evaluarii Q&A 1000 independent.",
        "% Include in lucrare cu: \\input{docs/evaluation/qa1000_independent_latex_tables.tex}",
        "",
        latex_table(
            "Rezultate globale pentru evaluarea Q&A 1000",
            "tab:qa1000-global",
            r"p{0.58\linewidth}r",
            ["Metrica", "Valoare"],
            global_metric_rows(metrics),
        ),
        "",
        latex_table(
            "Rezultate pe categorii pentru evaluarea Q&A 1000",
            "tab:qa1000-categorii",
            r"p{0.30\linewidth}rrrrrrr",
            ["Categorie", "Total", "Pass rate", "Scor mediu", "Top-1", "Top-3", "Latenta", "Erori"],
            category_rows(category_metrics),
        ),
        "",
        latex_table(
            "Latente pentru evaluarea Q&A 1000",
            "tab:qa1000-latente",
            r"p{0.45\linewidth}r",
            ["Metrica", "Secunde"],
            [[name, value] for name, value in latency_rows(metrics)],
        ),
        "",
        latex_table(
            "Distributia modului de generare",
            "tab:qa1000-generation-mode",
            r"p{0.60\linewidth}r",
            ["Generation mode", "Numar"],
            distribution_rows(generation_distribution),
        ),
        "",
        latex_table(
            "Distributia backendului de retrieval",
            "tab:qa1000-retrieval-backend",
            r"p{0.60\linewidth}r",
            ["Retrieval backend", "Numar"],
            distribution_rows(retrieval_distribution),
        ),
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def write_category_summary_csv(path: Path, category_metrics: dict[str, Any]) -> None:
    fields = [
        "category",
        "total_questions",
        "passed_count",
        "failed_count",
        "pass_rate",
        "average_score",
        "median_score",
        "top1_url_match_count",
        "top1_url_match_denominator",
        "top3_url_match_count",
        "top3_url_match_denominator",
        "average_latency",
        "median_latency",
        "p95_latency",
        "error_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for category, metrics in sorted(category_metrics.items()):
            if not isinstance(metrics, dict):
                continue
            writer.writerow(
                {
                    "category": category,
                    "total_questions": metric_value(metrics, "total_questions", default=0),
                    "passed_count": metric_value(metrics, "passed_count", default=0),
                    "failed_count": metric_value(metrics, "failed_count", default=0),
                    "pass_rate": metric_value(metrics, "pass_rate", default=0),
                    "average_score": metric_value(metrics, "average_score", "average_qa_score", default=0),
                    "median_score": metric_value(metrics, "median_score", "median_qa_score", default=0),
                    "top1_url_match_count": metric_value(metrics, "top1_url_match_count", default=0),
                    "top1_url_match_denominator": metric_value(metrics, "top1_url_match_denominator", default=0),
                    "top3_url_match_count": metric_value(metrics, "top3_url_match_count", default=0),
                    "top3_url_match_denominator": metric_value(metrics, "top3_url_match_denominator", default=0),
                    "average_latency": metric_value(metrics, "average_latency", "average_latency_seconds", default=0),
                    "median_latency": metric_value(metrics, "median_latency", "median_latency_seconds", default=0),
                    "p95_latency": metric_value(metrics, "p95_latency", default=0),
                    "error_count": metric_value(metrics, "error_count", default=0),
                }
            )


def write_failures_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "category",
        "faculty_id",
        "question",
        "score",
        "confidence",
        "confidence_score",
        "source_count",
        "top1_url",
        "top3_urls",
        "detected_intent",
        "retrieval_backend",
        "generation_mode",
        "latency_seconds",
        "error",
    ]
    failures = sorted(
        [item for item in results if not item.get("passed")],
        key=lambda item: (float(item.get("score") or 0), str(item.get("id") or "")),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in failures:
            row = dict(item)
            row["top3_urls"] = json.dumps(row.get("top3_urls", []), ensure_ascii=False)
            writer.writerow({field: row.get(field, "") for field in fields})


def build_reports(input_path: Path, docs_dir: Path, output_dir: Path) -> dict[str, Path]:
    payload = load_results(input_path)
    results = [item for item in payload["results"] if isinstance(item, dict)]
    payload["results"] = results

    metrics = payload["global_metrics"]
    confidence_distribution = distribution_from_metrics(metrics, "confidence_distribution", results, "confidence")
    retrieval_distribution = distribution_from_metrics(metrics, "retrieval_backend_distribution", results, "retrieval_backend")
    generation_distribution = distribution_from_metrics(metrics, "generation_mode_distribution", results, "generation_mode")
    categories = category_counts(results)

    docs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "markdown": docs_dir / "qa1000_independent_report.md",
        "latex": docs_dir / "qa1000_independent_latex_tables.tex",
        "category_csv": output_dir / "qa1000_independent_category_summary.csv",
        "failures_csv": output_dir / "qa1000_independent_failures.csv",
    }

    write_markdown_report(
        paths["markdown"],
        payload,
        categories,
        confidence_distribution,
        retrieval_distribution,
        generation_distribution,
    )
    write_latex_tables(paths["latex"], metrics, payload["category_metrics"], retrieval_distribution, generation_distribution)
    write_category_summary_csv(paths["category_csv"], payload["category_metrics"])
    write_failures_csv(paths["failures_csv"], results)
    return paths


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    docs_dir = resolve_path(args.docs_dir)
    output_dir = resolve_path(args.output_dir)
    try:
        paths = build_reports(input_path, docs_dir, output_dir)
    except Exception as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 2

    print("Rapoarte generate:")
    for key, path in paths.items():
        print(f"- {key}: {rel(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

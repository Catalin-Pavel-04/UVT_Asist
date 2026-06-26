from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:  # pragma: no cover - depends on local environment.
    matplotlib = None
    plt = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "evaluation" / "figures"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate simple PNG charts from qa1000_independent_results_<timestamp>.json."
    )
    parser.add_argument("--input", required=True, help="Path to qa1000_independent_results_<timestamp>.json")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated PNG figures")
    return parser.parse_args()


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else REPO_ROOT / path


def load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Nu exista fisierul de input: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Fisierul de input trebuie sa fie un obiect JSON.")
    if not isinstance(payload.get("results"), list):
        raise ValueError("Fisierul de input trebuie sa contina cheia 'results' cu o lista.")
    payload.setdefault("global_metrics", {})
    payload.setdefault("category_metrics", {})
    return payload


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def category_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    category_metrics = payload.get("category_metrics")
    rows: list[dict[str, Any]] = []
    if isinstance(category_metrics, dict) and category_metrics:
        for category, metrics in category_metrics.items():
            if not isinstance(metrics, dict):
                continue
            rows.append(
                {
                    "category": str(category),
                    "pass_rate": number(metrics.get("pass_rate")),
                    "average_latency": number(metrics.get("average_latency", metrics.get("average_latency_seconds"))),
                }
            )
    else:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in payload["results"]:
            if isinstance(item, dict):
                grouped[str(item.get("category") or "uncategorized")].append(item)
        for category, items in grouped.items():
            total = len(items)
            passed = sum(1 for item in items if bool(item.get("passed")))
            latencies = [number(item.get("latency_seconds")) for item in items]
            rows.append(
                {
                    "category": category,
                    "pass_rate": (passed / total * 100) if total else 0.0,
                    "average_latency": sum(latencies) / len(latencies) if latencies else 0.0,
                }
            )
    return sorted(rows, key=lambda item: (-item["pass_rate"], item["category"]))


def distribution(payload: dict[str, Any], metrics_key: str, result_key: str) -> dict[str, int]:
    metrics = payload.get("global_metrics")
    if isinstance(metrics, dict) and isinstance(metrics.get(metrics_key), dict):
        return {
            str(key): int(value)
            for key, value in metrics[metrics_key].items()
            if isinstance(value, (int, float)) or str(value).strip()
        }
    counts: Counter[str] = Counter()
    for item in payload["results"]:
        if isinstance(item, dict):
            counts[str(item.get(result_key) or "unknown")] += 1
    return dict(counts)


def save_horizontal_bar(
    path: Path,
    labels: list[str],
    values: list[float],
    title: str,
    xlabel: str,
    suffix: str = "",
    xlim: tuple[float, float] | None = None,
) -> None:
    figure_height = max(5.0, 0.48 * len(labels) + 1.6)
    fig, ax = plt.subplots(figsize=(11, figure_height))
    positions = range(len(labels))
    bars = ax.barh(positions, values, color="#3b82f6")
    ax.set_yticks(list(positions), labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    if xlim:
        ax.set_xlim(*xlim)
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)

    max_value = max(values) if values else 0
    padding = max(max_value * 0.015, 0.8)
    for bar, value in zip(bars, values):
        label = f"{value:.1f}{suffix}"
        ax.text(value + padding, bar.get_y() + bar.get_height() / 2, label, va="center", fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_distribution_bar(path: Path, data: dict[str, int], title: str, xlabel: str) -> None:
    rows = sorted(data.items(), key=lambda item: (-item[1], item[0]))
    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]

    figure_width = max(7.0, 1.35 * len(labels) + 2.0)
    fig, ax = plt.subplots(figsize=(figure_width, 5.5))
    bars = ax.bar(labels, values, color="#10b981")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Numar raspunsuri")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", rotation=20)

    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value, str(value), ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def generate_figures(payload: dict[str, Any], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    categories = category_summary(payload)
    category_names = [item["category"] for item in categories]

    paths = [
        output_dir / "qa1000_pass_rate_by_category.png",
        output_dir / "qa1000_average_latency_by_category.png",
        output_dir / "qa1000_generation_mode_distribution.png",
        output_dir / "qa1000_retrieval_backend_distribution.png",
    ]

    save_horizontal_bar(
        paths[0],
        category_names,
        [item["pass_rate"] for item in categories],
        "Q&A 1000 - pass rate pe categorii",
        "Pass rate (%)",
        suffix="%",
        xlim=(0, 105),
    )
    save_horizontal_bar(
        paths[1],
        category_names,
        [item["average_latency"] for item in categories],
        "Q&A 1000 - latenta medie pe categorii",
        "Latenta medie (secunde)",
        suffix="s",
    )
    save_distribution_bar(
        paths[2],
        distribution(payload, "generation_mode_distribution", "generation_mode"),
        "Q&A 1000 - distributia modului de generare",
        "Generation mode",
    )
    save_distribution_bar(
        paths[3],
        distribution(payload, "retrieval_backend_distribution", "retrieval_backend"),
        "Q&A 1000 - distributia backendului de retrieval",
        "Retrieval backend",
    )
    return paths


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    if plt is None:
        print("Lipseste pachetul matplotlib. Ruleaza: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    args = parse_args()
    input_path = resolve_path(args.input)
    output_dir = resolve_path(args.output_dir)
    payload = load_payload(input_path)
    paths = generate_figures(payload, output_dir)

    print("Grafice generate:")
    for path in paths:
        print(f"- {rel(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

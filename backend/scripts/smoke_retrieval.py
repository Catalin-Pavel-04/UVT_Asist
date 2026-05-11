from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from page_index import load_index
from retriever import rank_index
from vector_store import get_vector_index_status


@dataclass(frozen=True)
class Scenario:
    faculty_id: str
    question: str
    expected_label: str
    expected_url_part: str | None = None
    expected_page_type: str | None = None


SCENARIOS = [
    Scenario("info", "Unde gasesc orarul?", "Informatics schedule", "info.uvt.ro/orare", "orar"),
    Scenario("info", "Unde gasesc secretariatul facultatii de informatica?", "Informatics contact", "info.uvt.ro/contact", "contact"),
    Scenario("uvt", "Este posibil ca un student sa beneficieze de 2 burse?", "Scholarship policy", "Metodologie-de-acordare-a-burselor", "regulamente"),
    Scenario("uvt", "Unde gasesc informatii despre admitere?", "Admission", None, "admitere"),
    Scenario("info", "Unde gasesc orrarul la info?", "Typo schedule", "info.uvt.ro/orare", "orar"),
]


def print_result(scenario: Scenario, result: dict) -> None:
    print("=" * 80)
    print(f"{scenario.expected_label}")
    print(f"Faculty: {scenario.faculty_id} | Question: {scenario.question}")
    print(
        f"Intent={result['analysis']['intent']} | "
        f"Policy={result['analysis']['is_policy_question']} | "
        f"Confidence={result['confidence']} ({result['confidence_score']}) | "
        f"Backend={result.get('retrieval_backend')}"
    )
    if result.get("vector_error"):
        print(f"Vector error: {result['vector_error']}")
    if result["analysis"]["corrections"]:
        print(f"Corrections: {', '.join(result['analysis']['corrections'])}")

    for index, chunk in enumerate(result["chunks"][:3], start=1):
        print(
            f"{index}. score={chunk['retrieval_score']:.2f} | "
            f"faculty={chunk['faculty_id']} | type={chunk['page_type']} | {chunk['url']}"
        )
        print(f"   title={chunk['title']}")


def scenario_passed(scenario: Scenario, result: dict) -> bool:
    if result.get("retrieval_backend") != "qdrant":
        return False
    if not result.get("chunks"):
        return False

    top = result["chunks"][0]
    url_and_title = f"{top.get('url', '')} {top.get('title', '')}"
    if scenario.expected_url_part and scenario.expected_url_part.lower() not in url_and_title.lower():
        return False
    if scenario.expected_page_type and top.get("page_type") != scenario.expected_page_type:
        return False
    return True


def main() -> int:
    index_document = load_index()
    vector_status = get_vector_index_status()
    print(
        f"Loaded index schema={index_document.get('schema_version')} "
        f"pages={index_document.get('page_count')} chunks={index_document.get('chunk_count')}"
    )
    print(
        f"Qdrant collection={vector_status.get('collection')} "
        f"available={vector_status.get('available')} points={vector_status.get('points_count')}"
    )

    failures: list[str] = []
    for scenario in SCENARIOS:
        result = rank_index(scenario.question, index_document, scenario.faculty_id, top_k=5)
        print_result(scenario, result)
        if not scenario_passed(scenario, result):
            failures.append(scenario.expected_label)

    if failures:
        print("=" * 80)
        print("FAILED scenarios: " + ", ".join(failures))
        return 1

    print("=" * 80)
    print("All retrieval smoke scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

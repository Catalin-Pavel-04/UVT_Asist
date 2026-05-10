from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from page_index import load_index
from retriever import rank_index

SCENARIOS = [
    ("info", "Unde gasesc orarul?"),
    ("info", "Unde gasesc secretariatul facultatii de informatica?"),
    ("uvt", "Este posibil ca un student sa beneficieze de 2 burse?"),
    ("uvt", "Unde gasesc informatii despre admitere?"),
    ("info", "Unde gasesc orrarul la info?"),
]


def print_result(faculty_id: str, question: str, result: dict) -> None:
    print("=" * 80)
    print(f"Faculty: {faculty_id} | Question: {question}")
    print(
        f"Intent={result['analysis']['intent']} | "
        f"Policy={result['analysis']['is_policy_question']} | "
        f"Confidence={result['confidence']} ({result['confidence_score']})"
    )
    if result["analysis"]["corrections"]:
        print(f"Corrections: {', '.join(result['analysis']['corrections'])}")

    for index, chunk in enumerate(result["chunks"][:3], start=1):
        print(
            f"{index}. score={chunk['retrieval_score']:.2f} | "
            f"faculty={chunk['faculty_id']} | type={chunk['page_type']} | {chunk['url']}"
        )
        print(f"   title={chunk['title']}")


def main() -> None:
    index_document = load_index()
    print(
        f"Loaded index schema={index_document.get('schema_version')} "
        f"pages={index_document.get('page_count')} chunks={index_document.get('chunk_count')}"
    )

    for faculty_id, question in SCENARIOS:
        result = rank_index(question, index_document, faculty_id, top_k=5)
        print_result(faculty_id, question, result)


if __name__ == "__main__":
    main()

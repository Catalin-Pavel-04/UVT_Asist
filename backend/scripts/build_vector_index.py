from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from page_index import load_index
from vector_indexer import rebuild_vector_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild the Qdrant vector index from backend/data/page_index.json.")
    parser.add_argument(
        "--no-recreate",
        action="store_true",
        help="Upsert into the existing Qdrant collection instead of recreating it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    index_document = load_index()
    if not index_document.get("chunks"):
        print("No chunks found. Run python backend\\build_index.py first.")
        return 1

    status = rebuild_vector_index(index_document, recreate=not args.no_recreate)
    location = status.get("qdrant_path") or status.get("qdrant_url")
    print(
        f"Indexed {status['indexed_count']} chunks into Qdrant collection "
        f"{status['collection']} at {location} using {status['embedding_model']} "
        f"({status['vector_size']} dimensions)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

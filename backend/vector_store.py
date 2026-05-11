from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

ENV_FILE = Path(__file__).with_name(".env")
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"
DEFAULT_COLLECTION_NAME = "uvt_asist_chunks"
DEFAULT_UPSERT_BATCH_SIZE = 64
PAYLOAD_INDEX_FIELDS = ("faculty_id", "page_type", "url", "last_indexed")

load_dotenv(ENV_FILE)

try:
    from qdrant_client import QdrantClient, models
except ModuleNotFoundError:  # pragma: no cover - exercised when setup is incomplete.
    QdrantClient = None
    models = None


@dataclass(frozen=True)
class VectorStoreSettings:
    url: str
    path: str
    collection_name: str
    timeout: int


def get_vector_settings() -> VectorStoreSettings:
    configured_path = os.getenv("QDRANT_PATH", "").strip()
    if configured_path:
        qdrant_path = Path(configured_path).expanduser()
        if not qdrant_path.is_absolute():
            qdrant_path = REPO_ROOT / qdrant_path
        configured_path = str(qdrant_path)

    return VectorStoreSettings(
        url=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL).strip() or DEFAULT_QDRANT_URL,
        path=configured_path,
        collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION_NAME).strip()
        or DEFAULT_COLLECTION_NAME,
        timeout=int(os.getenv("QDRANT_TIMEOUT_SECONDS", "30")),
    )


def _require_qdrant_client() -> None:
    if QdrantClient is None or models is None:
        raise RuntimeError("qdrant-client is not installed. Run: pip install -r backend\\requirements.txt")


def get_client() -> QdrantClient:
    _require_qdrant_client()
    settings = get_vector_settings()
    if settings.path:
        Path(settings.path).parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=settings.path)
    return QdrantClient(url=settings.url, timeout=settings.timeout)


def point_id_from_chunk_id(chunk_id: str) -> int:
    digest = hashlib.sha1(str(chunk_id).encode("utf-8")).hexdigest()
    return int(digest[:15], 16)


def _collection_vector_size(collection_info) -> int | None:
    vectors = getattr(getattr(collection_info, "config", None), "params", None)
    vectors = getattr(vectors, "vectors", None)

    if getattr(vectors, "size", None):
        return int(vectors.size)
    if isinstance(vectors, dict) and vectors:
        first_config = next(iter(vectors.values()))
        if getattr(first_config, "size", None):
            return int(first_config.size)
    return None


def collection_exists(client: QdrantClient | None = None) -> bool:
    client = client or get_client()
    settings = get_vector_settings()
    return bool(client.collection_exists(settings.collection_name))


def create_payload_indexes(client: QdrantClient | None = None) -> None:
    client = client or get_client()
    settings = get_vector_settings()
    for field_name in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=settings.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


def initialize_collection(vector_size: int, recreate: bool = False) -> None:
    client = get_client()
    settings = get_vector_settings()

    if collection_exists(client):
        existing_size = _collection_vector_size(client.get_collection(settings.collection_name))
        if recreate or existing_size != vector_size:
            client.delete_collection(settings.collection_name)
        else:
            create_payload_indexes(client)
            return

    client.create_collection(
        collection_name=settings.collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )
    create_payload_indexes(client)


def chunk_payload(chunk: dict) -> dict:
    return {
        "chunk_id": str(chunk.get("chunk_id", "")),
        "faculty_id": str(chunk.get("faculty_id", "uvt")),
        "page_type": str(chunk.get("page_type", "general")),
        "title": str(chunk.get("title") or chunk.get("url") or "Official source"),
        "url": str(chunk.get("url", "")),
        "chunk_text": str(chunk.get("chunk_text", "")),
        "last_indexed": str(chunk.get("last_indexed", "")),
    }


def _batched(items: list, batch_size: int) -> Iterable[list]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def upsert_chunks(chunks: list[dict], vectors: list[list[float]], batch_size: int | None = None) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("Chunk and vector counts must match.")

    client = get_client()
    settings = get_vector_settings()
    batch_size = batch_size or int(os.getenv("QDRANT_UPSERT_BATCH_SIZE", str(DEFAULT_UPSERT_BATCH_SIZE)))
    points = []

    for chunk, vector in zip(chunks, vectors):
        payload = chunk_payload(chunk)
        if not payload["chunk_id"] or not payload["chunk_text"] or not vector:
            continue
        points.append(
            models.PointStruct(
                id=point_id_from_chunk_id(payload["chunk_id"]),
                vector=[float(value) for value in vector],
                payload=payload,
            )
        )

    for batch in _batched(points, max(1, batch_size)):
        client.upsert(collection_name=settings.collection_name, points=batch, wait=True)

    return len(points)


def index_chunks(chunks: list[dict], vectors: list[list[float]], recreate: bool = True) -> int:
    if not vectors:
        initialize_collection(vector_size=1, recreate=recreate)
        return 0
    initialize_collection(vector_size=len(vectors[0]), recreate=recreate)
    return upsert_chunks(chunks, vectors)


def _match_condition(key: str, values: Iterable[str]):
    values = [str(value) for value in values if value]
    if not values:
        return None
    if len(values) == 1:
        return models.FieldCondition(key=key, match=models.MatchValue(value=values[0]))
    return models.FieldCondition(key=key, match=models.MatchAny(any=values))


def build_payload_filter(
    faculty_ids: Iterable[str] | None = None,
    page_types: Iterable[str] | None = None,
):
    conditions = []
    faculty_condition = _match_condition("faculty_id", faculty_ids or [])
    page_type_condition = _match_condition("page_type", page_types or [])

    if faculty_condition is not None:
        conditions.append(faculty_condition)
    if page_type_condition is not None:
        conditions.append(page_type_condition)

    return models.Filter(must=conditions) if conditions else None


def search_chunks(
    query_vector: list[float],
    faculty_ids: Iterable[str] | None = None,
    page_types: Iterable[str] | None = None,
    limit: int = 12,
) -> list[dict]:
    client = get_client()
    settings = get_vector_settings()
    query_filter = build_payload_filter(faculty_ids=faculty_ids, page_types=page_types)

    try:
        hits = client.search(
            collection_name=settings.collection_name,
            query_vector=[float(value) for value in query_vector],
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
    except AttributeError:
        response = client.query_points(
            collection_name=settings.collection_name,
            query=[float(value) for value in query_vector],
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        hits = getattr(response, "points", response)

    results: list[dict] = []
    for hit in hits:
        payload = dict(getattr(hit, "payload", {}) or {})
        if not payload:
            continue
        payload["semantic_score"] = round(float(getattr(hit, "score", 0.0) or 0.0), 6)
        results.append(payload)
    return results


def get_vector_index_status() -> dict:
    settings = get_vector_settings()
    status = {
        "url": settings.url,
        "path": settings.path,
        "collection": settings.collection_name,
        "available": False,
        "exists": False,
        "points_count": 0,
    }

    try:
        client = get_client()
        status["exists"] = collection_exists(client)
        if status["exists"]:
            info = client.get_collection(settings.collection_name)
            status["available"] = True
            status["points_count"] = int(getattr(info, "points_count", 0) or 0)
            status["vector_size"] = _collection_vector_size(info)
    except Exception as exc:
        status["error"] = str(exc)

    return status

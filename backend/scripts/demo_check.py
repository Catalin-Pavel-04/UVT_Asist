from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE_FILE = BACKEND_DIR / ".env.example"
INDEX_FILE = BACKEND_DIR / "data" / "page_index.json"

DEFAULTS = {
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "OLLAMA_GENERATION_MODEL": "qwen3:4b",
    "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
    "QDRANT_URL": "http://127.0.0.1:6333",
    "QDRANT_COLLECTION": "uvt_asist_chunks",
}

REQUIRED_IMPORTS = {
    "flask": "Flask",
    "flask_cors": "flask-cors",
    "bs4": "beautifulsoup4",
    "requests": "requests",
    "dotenv": "python-dotenv",
    "pypdf": "pypdf",
    "docx": "python-docx",
    "qdrant_client": "qdrant-client",
}


class Reporter:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print(f"OK: {message}")

    def warning(self, message: str, suggestion: str | None = None) -> None:
        self.warnings += 1
        print(f"WARNING: {message}")
        if suggestion:
            print(f"  Fix: {suggestion}")

    def error(self, message: str, suggestion: str | None = None) -> None:
        self.errors += 1
        print(f"ERROR: {message}")
        if suggestion:
            print(f"  Fix: {suggestion}")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config() -> dict[str, str]:
    config = dict(DEFAULTS)
    config.update(read_env_file(ENV_EXAMPLE_FILE))
    config.update(read_env_file(ENV_FILE))
    for key in DEFAULTS:
        if os.getenv(key):
            config[key] = os.getenv(key, "")
    return {key: str(value).strip().rstrip("/") if key.endswith("_URL") else str(value).strip() for key, value in config.items()}


def fetch_json(url: str, timeout: float = 5) -> tuple[dict | None, str | None]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
        return data if isinstance(data, dict) else {}, None
    except HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def model_is_installed(model_name: str, installed_models: list[str]) -> bool:
    if model_name in installed_models:
        return True
    if ":" not in model_name:
        return f"{model_name}:latest" in installed_models or any(
            installed.startswith(f"{model_name}:") for installed in installed_models
        )
    return False


def check_imports(reporter: Reporter) -> None:
    missing = []
    for module_name, package_name in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(package_name)

    if missing:
        reporter.error(
            f"Lipsesc pachete Python: {', '.join(missing)}.",
            "pip install -r backend/requirements.txt",
        )
    else:
        reporter.ok("Pachetele Python principale pot fi importate.")


def check_env(reporter: Reporter) -> None:
    if ENV_FILE.exists():
        reporter.ok("backend/.env există.")
    elif ENV_EXAMPLE_FILE.exists():
        reporter.warning(
            "backend/.env lipsește, dar există backend/.env.example.",
            "Copy-Item backend/.env.example backend/.env",
        )
    else:
        reporter.error("Nu există nici backend/.env, nici backend/.env.example.")


def check_ollama(reporter: Reporter, config: dict[str, str]) -> None:
    base_url = config["OLLAMA_BASE_URL"]
    data, error = fetch_json(f"{base_url}/api/tags", timeout=5)
    if error:
        reporter.error(
            f"Ollama nu răspunde la {base_url}/api/tags.",
            "ollama serve",
        )
        return

    models = data.get("models") if isinstance(data, dict) else []
    installed = [str(model.get("name", "")) for model in models if isinstance(model, dict) and model.get("name")]
    reporter.ok(f"Ollama răspunde. Modele instalate: {len(installed)}.")

    generation_model = config["OLLAMA_GENERATION_MODEL"]
    embedding_model = config["OLLAMA_EMBEDDING_MODEL"]
    if model_is_installed(generation_model, installed):
        reporter.ok(f"Modelul de generare este instalat: {generation_model}.")
    else:
        reporter.error(
            f"Modelul de generare lipsește: {generation_model}.",
            f"ollama pull {generation_model}",
        )

    if model_is_installed(embedding_model, installed):
        reporter.ok(f"Modelul de embedding este instalat: {embedding_model}.")
    else:
        reporter.error(
            f"Modelul de embedding lipsește: {embedding_model}.",
            f"ollama pull {embedding_model}",
        )


def check_qdrant_server(reporter: Reporter, config: dict[str, str]) -> bool:
    qdrant_url = config["QDRANT_URL"]
    data, error = fetch_json(f"{qdrant_url}/collections", timeout=5)
    if error:
        reporter.error(
            f"Qdrant nu răspunde la {qdrant_url}.",
            "docker compose up -d qdrant",
        )
        return False

    collections = ((data or {}).get("result") or {}).get("collections") or []
    reporter.ok(f"Qdrant răspunde. Colecții raportate: {len(collections)}.")
    return True


def check_json_index(reporter: Reporter) -> int:
    if not INDEX_FILE.exists():
        reporter.warning(
            "Indexul JSON lipsește: backend/data/page_index.json.",
            "python backend/build_index.py",
        )
        return 0

    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        chunk_count = int(data.get("chunk_count") or len(data.get("chunks") or []))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reporter.warning(
            f"Indexul JSON există, dar nu poate fi citit corect: {exc}.",
            "python backend/build_index.py",
        )
        return 0

    if chunk_count <= 0:
        reporter.warning(
            "Indexul JSON există, dar nu conține fragmente.",
            "python backend/build_index.py",
        )
        return 0

    reporter.ok(f"Indexul JSON există și raportează {chunk_count} fragmente.")
    return chunk_count


def check_qdrant_collection_direct(reporter: Reporter, config: dict[str, str]) -> int:
    qdrant_url = config["QDRANT_URL"]
    collection = config["QDRANT_COLLECTION"]
    data, error = fetch_json(f"{qdrant_url}/collections/{collection}", timeout=5)
    if error:
        reporter.warning(
            f"Colecția Qdrant `{collection}` nu poate fi citită direct: {error}.",
            "python backend/scripts/build_vector_index.py",
        )
        return 0

    result = (data or {}).get("result") or {}
    points = int(result.get("points_count") or result.get("vectors_count") or 0)
    if points <= 0:
        reporter.warning(
            f"Colecția Qdrant `{collection}` nu are vectori indexați.",
            "Pornește Qdrant și rulează: python backend/build_index.py",
        )
        return 0

    reporter.ok(f"Colecția Qdrant `{collection}` conține {points} puncte.")
    return points


def check_backend_health(reporter: Reporter, json_chunks: int) -> bool:
    data, error = fetch_json("http://127.0.0.1:5000/health", timeout=5)
    if error:
        reporter.warning(
            "Backend-ul Flask nu răspunde la http://127.0.0.1:5000/health.",
            "python backend/app.py",
        )
        return False

    status = data.get("status", "unknown")
    if status == "ok":
        reporter.ok("Backend-ul Flask răspunde și raportează status ok.")
    else:
        reasons = data.get("status_reasons") if isinstance(data.get("status_reasons"), list) else []
        reporter.warning(
            f"Backend-ul Flask răspunde, dar statusul este `{status}`. {' '.join(map(str, reasons))}".strip(),
            "Rulează comenzile sugerate pentru componentele marcate cu WARNING/ERROR.",
        )

    vector_index = data.get("vector_index") if isinstance(data.get("vector_index"), dict) else {}
    points = int(vector_index.get("points_count") or 0)
    if points > 0:
        reporter.ok(f"/health raportează {points} puncte în Qdrant.")
    elif vector_index:
        reporter.warning(
            "/health raportează Qdrant gol sau indisponibil.",
            "docker compose up -d qdrant; python backend/build_index.py",
        )

    health_index = data.get("index") if isinstance(data.get("index"), dict) else {}
    health_chunks = int(health_index.get("chunk_count") or 0)
    if health_chunks and points and health_chunks != points:
        reporter.warning(
            f"Numărul de chunks JSON ({health_chunks}) nu corespunde cu punctele Qdrant ({points}).",
            "python backend/scripts/build_vector_index.py",
        )
    elif json_chunks and points and json_chunks != points:
        reporter.warning(
            f"Indexul local are {json_chunks} chunks, dar Qdrant are {points} puncte.",
            "python backend/scripts/build_vector_index.py",
        )
    return True


def main() -> int:
    reporter = Reporter()
    config = load_config()

    print("UVT_Asist demo check\n")
    check_imports(reporter)
    check_env(reporter)
    check_ollama(reporter, config)
    qdrant_available = check_qdrant_server(reporter, config)
    json_chunks = check_json_index(reporter)
    backend_available = check_backend_health(reporter, json_chunks)
    if qdrant_available and not backend_available:
        points = check_qdrant_collection_direct(reporter, config)
        if json_chunks and points and json_chunks != points:
            reporter.warning(
                f"Indexul local are {json_chunks} chunks, dar Qdrant are {points} puncte.",
                "python backend/scripts/build_vector_index.py",
            )

    print("\nRezultat")
    print(f"- OK: verificările fără mesaj de eroare au trecut")
    print(f"- WARNING: {reporter.warnings}")
    print(f"- ERROR: {reporter.errors}")
    if reporter.errors:
        print("\nComenzi utile:")
        print("- ollama pull qwen3:4b")
        print("- ollama pull nomic-embed-text")
        print("- docker compose up -d qdrant")
        print("- python backend/build_index.py")
        print("- python backend/app.py")
    return 1 if reporter.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

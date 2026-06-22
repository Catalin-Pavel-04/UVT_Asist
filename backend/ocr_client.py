from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
from io import BytesIO
from pathlib import Path

from core.config import env_bool, env_int, env_str
from core.logging import get_logger

LOGGER = get_logger(__name__)

try:
    from pypdf import PdfReader, PdfWriter
except ModuleNotFoundError:
    PdfReader = None
    PdfWriter = None

OCR_SCRIPT = Path(__file__).parent / "scripts" / "paddle_ocr_extract.py"
DEFAULT_OCR_VENV_PYTHON = Path(__file__).with_name(".ocr-venv") / "Scripts" / "python.exe"
OCR_CACHE = {}
OCR_CACHE_LOCK = threading.Lock()
DEFAULT_OCR_TIMEOUT = 120
DEFAULT_OCR_LANG = "ro"
DEFAULT_OCR_MIN_TEXT_CHARS = 120
DEFAULT_OCR_MAX_PAGES = 6
OCR_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def _get_bool_env(name: str, default: bool = False) -> bool:
    return env_bool(name, default)


def _get_int_env(name: str, default: int) -> int:
    return env_int(name, default, strict=False)


def is_paddle_ocr_enabled() -> bool:
    return _get_bool_env("ENABLE_PADDLE_OCR", False) and bool(get_paddle_ocr_python())


def get_paddle_ocr_python() -> str:
    configured = env_str("PADDLE_OCR_PYTHON", "")
    if configured:
        return configured

    if DEFAULT_OCR_VENV_PYTHON.exists():
        return str(DEFAULT_OCR_VENV_PYTHON)

    return ""


def get_paddle_ocr_lang() -> str:
    return env_str("PADDLE_OCR_LANG", DEFAULT_OCR_LANG)


def get_paddle_ocr_timeout() -> int:
    return _get_int_env("PADDLE_OCR_TIMEOUT", DEFAULT_OCR_TIMEOUT)


def get_paddle_ocr_max_pages() -> int:
    return max(1, _get_int_env("PADDLE_OCR_MAX_PAGES", DEFAULT_OCR_MAX_PAGES))


def should_run_pdf_ocr(text: str) -> bool:
    min_chars = max(1, _get_int_env("PADDLE_OCR_MIN_TEXT_CHARS", DEFAULT_OCR_MIN_TEXT_CHARS))
    normalized = re.sub(r"\s+", " ", text or "").strip()
    alnum_chars = sum(char.isalnum() for char in normalized)
    return alnum_chars < min_chars


def _get_cached_ocr(key: str) -> str | None:
    with OCR_CACHE_LOCK:
        return OCR_CACHE.get(key)


def _set_cached_ocr(key: str, text: str) -> None:
    with OCR_CACHE_LOCK:
        OCR_CACHE[key] = text


def _build_ocr_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _truncate_pdf_for_ocr(content: bytes) -> bytes:
    max_pages = get_paddle_ocr_max_pages()
    if PdfReader is None or PdfWriter is None:
        return content

    try:
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) <= max_pages:
            return content

        writer = PdfWriter()
        for page in reader.pages[:max_pages]:
            writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception:
        return content


def is_supported_ocr_image_extension(extension: str) -> bool:
    return extension.lower() in OCR_IMAGE_EXTENSIONS


def _run_paddle_ocr(content: bytes, suffix: str, prepared_content: bytes | None = None) -> str:
    if not is_paddle_ocr_enabled():
        return ""

    cache_key = hashlib.sha256(suffix.encode("utf-8") + b":" + content).hexdigest()
    cached = _get_cached_ocr(cache_key)
    if cached is not None:
        return cached

    file_content = prepared_content if prepared_content is not None else content

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(file_content)
        temp_path = Path(handle.name)

    try:
        command = [
            get_paddle_ocr_python(),
            str(OCR_SCRIPT),
            str(temp_path),
            "--lang",
            get_paddle_ocr_lang(),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=get_paddle_ocr_timeout(),
            check=False,
            env=_build_ocr_subprocess_env(),
        )
        if result.returncode != 0:
            return ""

        payload = json.loads(result.stdout or "{}")
        text = re.sub(r"\s+", " ", payload.get("text", "")).strip()
        _set_cached_ocr(cache_key, text)
        return text
    except Exception:
        return ""
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception as exc:
            LOGGER.warning("Could not remove OCR temporary file %s: %s", temp_path, exc)


def run_paddle_ocr_on_pdf(content: bytes) -> str:
    return _run_paddle_ocr(content, ".pdf", prepared_content=_truncate_pdf_for_ocr(content))


def run_paddle_ocr_on_image(content: bytes, extension: str) -> str:
    if not is_supported_ocr_image_extension(extension):
        return ""

    return _run_paddle_ocr(content, extension.lower())

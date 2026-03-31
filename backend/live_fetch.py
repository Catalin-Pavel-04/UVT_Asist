import os
import re
import threading
import time
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from docx import Document
from ocr_client import (
    is_paddle_ocr_enabled,
    is_supported_ocr_image_extension,
    run_paddle_ocr_on_image,
    run_paddle_ocr_on_pdf,
    should_run_pdf_ocr,
)
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "UVT_Asist/1.0"
}

BAD_EXTENSIONS = (
    ".gif", ".svg",
    ".zip", ".rar", ".doc", ".xls", ".xlsx", ".ppt", ".pptx"
)
MAX_TEXT_LENGTH = 16000
MAX_PDF_PAGES = 12

PAGE_CACHE = {}
LINK_CACHE = {}
CACHE_TTL = max(60, int(os.getenv("LIVE_FETCH_CACHE_TTL", "300")))
SESSION_LOCAL = threading.local()
CACHE_LOCK = threading.Lock()
NON_HTML_LINK_PREFIXES = ("#", "mailto:", "tel:", "javascript:")
REMOVABLE_SELECTORS = (
    "header",
    "nav",
    "aside",
    "form",
    "iframe",
    "button",
    "input",
    "select",
    "textarea",
    "[role='navigation']",
    ".menu",
    ".nav",
    ".navbar",
    ".breadcrumbs",
    ".breadcrumb",
    ".cookie",
    ".cookies",
    ".gdpr",
    ".banner",
    ".sidebar",
    ".search-form",
    ".newsletter",
    "#cookie-notice",
    "#cookie-law-info-bar",
)


def get_session() -> requests.Session:
    session = getattr(SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(HEADERS)
        SESSION_LOCAL.session = session

    return session


def get_cached(cache: dict, key: str, now: float):
    with CACHE_LOCK:
        cached = cache.get(key)
        if cached and now - cached["timestamp"] < CACHE_TTL:
            return cached["data"]

    return None


def set_cached(cache: dict, key: str, data) -> None:
    with CACHE_LOCK:
        cache[key] = {
            "timestamp": time.time(),
            "data": data
        }


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_hostname(hostname: str) -> str:
    hostname = hostname.strip().lower()
    if hostname.startswith("www."):
        return hostname[4:]

    return hostname


def same_domain(url: str, base_urls: list[str]) -> bool:
    try:
        host = normalize_hostname(urlparse(url).hostname or "")
        return any(host == normalize_hostname(urlparse(base).hostname or "") for base in base_urls)
    except Exception:
        return False


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "img", "footer", "template"]):
        tag.decompose()

    for selector in REMOVABLE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    text = soup.get_text(separator=" ")
    return normalize_whitespace(text)


def get_url_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    return PurePosixPath(path).suffix


def is_html_response(content_type: str, url: str) -> bool:
    extension = get_url_extension(url)
    normalized_type = (content_type or "").lower()
    return "html" in normalized_type or extension in ("", ".html", ".htm", ".php", ".aspx")


def is_pdf_response(content_type: str, url: str) -> bool:
    normalized_type = (content_type or "").lower()
    return "application/pdf" in normalized_type or get_url_extension(url) == ".pdf"


def is_docx_response(content_type: str, url: str) -> bool:
    normalized_type = (content_type or "").lower()
    extension = get_url_extension(url)
    return (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in normalized_type
        or extension == ".docx"
    )


def is_text_response(content_type: str, url: str) -> bool:
    normalized_type = (content_type or "").lower()
    return normalized_type.startswith("text/plain") or get_url_extension(url) == ".txt"


def is_ocr_image_response(content_type: str, url: str) -> bool:
    normalized_type = (content_type or "").lower()
    extension = get_url_extension(url)
    return (
        normalized_type.startswith("image/jpeg")
        or normalized_type.startswith("image/png")
        or is_supported_ocr_image_extension(extension)
    )


def truncate_text(text: str) -> str:
    return normalize_whitespace(text)[:MAX_TEXT_LENGTH]


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []

    for page in reader.pages[:MAX_PDF_PAGES]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)

        if sum(len(item) for item in pages) >= MAX_TEXT_LENGTH:
            break

    return truncate_text(" ".join(pages))


def extract_pdf_text_with_fallback(content: bytes) -> str:
    text = extract_pdf_text(content)
    if should_run_pdf_ocr(text):
        ocr_text = run_paddle_ocr_on_pdf(content)
        if ocr_text:
            return truncate_text(ocr_text)

    return text


def extract_image_text(content: bytes, url: str) -> str:
    extension = get_url_extension(url) or ".png"
    ocr_text = run_paddle_ocr_on_image(content, extension)
    if not ocr_text:
        return ""

    return truncate_text(ocr_text)


def extract_docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]

    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                paragraphs.append(row_text)

    return truncate_text(" ".join(paragraphs))


def extract_filename_from_content_disposition(content_disposition: str) -> str:
    if not content_disposition:
        return ""

    encoded_match = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)", content_disposition)
    if encoded_match:
        return unquote(encoded_match.group(1).strip().strip('"'))

    plain_match = re.search(r'filename\s*=\s*"?(?P<name>[^";]+)"?', content_disposition)
    if plain_match:
        return plain_match.group("name").strip()

    return ""


def build_title_from_url(url: str, fallback: str = "") -> str:
    filename = extract_filename_from_content_disposition(fallback)
    if filename:
        return filename

    path = PurePosixPath(urlparse(url).path)
    return path.name or fallback.strip() or url


def fetch_page(url: str, timeout: int = 10) -> dict:
    now = time.time()
    cache_key = f"{url}|ocr={int(is_paddle_ocr_enabled())}"
    cached = get_cached(PAGE_CACHE, cache_key, now)
    if cached is not None:
        return cached

    try:
        response = get_session().get(url, timeout=(2, timeout))
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        content_disposition = response.headers.get("Content-Disposition", "")
        title = url
        text = ""

        if is_html_response(content_type, url):
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else build_title_from_url(url)
            text = clean_html_text(response.text)
        elif is_pdf_response(content_type, url):
            title = build_title_from_url(url, fallback=content_disposition)
            text = extract_pdf_text_with_fallback(response.content)
        elif is_docx_response(content_type, url):
            title = build_title_from_url(url, fallback=content_disposition)
            text = extract_docx_text(response.content)
        elif is_text_response(content_type, url):
            title = build_title_from_url(url, fallback=content_disposition)
            text = truncate_text(response.text)
        elif is_ocr_image_response(content_type, url):
            title = build_title_from_url(url, fallback=content_disposition)
            text = extract_image_text(response.content, url)

        data = {
            "url": url,
            "title": title,
            "text": text[:MAX_TEXT_LENGTH],
            "type": (
                "html" if is_html_response(content_type, url) else
                "pdf" if is_pdf_response(content_type, url) else
                "docx" if is_docx_response(content_type, url) else
                "text" if is_text_response(content_type, url) else
                "image" if is_ocr_image_response(content_type, url) else
                "unknown"
            ),
        }

        set_cached(PAGE_CACHE, cache_key, data)
        return data
    except Exception as e:
        return {
            "url": url,
            "title": url,
            "text": "",
            "error": str(e),
            "type": "error",
        }


def extract_candidate_links(start_url: str, base_urls: list[str], max_links: int = 20, timeout: int = 10) -> list[str]:
    now = time.time()
    cache_key = f"{start_url}|ocr={int(is_paddle_ocr_enabled())}"
    cached = get_cached(LINK_CACHE, cache_key, now)
    if cached is not None:
        return cached[:max_links]

    try:
        response = get_session().get(start_url, timeout=(2, timeout))
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if not is_html_response(content_type, start_url):
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links = []

        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue

            if href.lower().startswith(NON_HTML_LINK_PREFIXES):
                continue

            full_url = urljoin(start_url, href).split("#")[0]
            parsed_url = urlparse(full_url)
            if parsed_url.scheme not in {"http", "https"}:
                continue

            if not same_domain(full_url, base_urls):
                continue

            normalized_url = full_url.lower()
            if normalized_url.endswith((".jpg", ".jpeg", ".png")) and not is_paddle_ocr_enabled():
                continue

            if normalized_url.endswith(BAD_EXTENSIONS):
                continue

            if full_url not in links:
                links.append(full_url)

        set_cached(LINK_CACHE, cache_key, links)
        return links[:max_links]
    except Exception:
        return []

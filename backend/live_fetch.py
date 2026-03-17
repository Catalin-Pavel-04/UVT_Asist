from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "UVT_Asist/1.0"
}
BAD_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".zip",
    ".rar",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def canonical_host(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def same_domain(url: str, base_urls: list[str]) -> bool:
    try:
        host = canonical_host(url)
        return any(host == canonical_host(base) for base in base_urls)
    except Exception:
        return False


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "img", "footer"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return normalize_whitespace(text)


def fetch_page(url: str, timeout: int = 12) -> dict:
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return {
                "url": url,
                "title": url,
                "text": "",
                "error": f"Unsupported content type: {content_type or 'unknown'}",
            }

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else url
        text = clean_html_text(response.text)
        return {
            "url": url,
            "title": title,
            "text": text[:20000],
        }
    except Exception as exc:
        return {
            "url": url,
            "title": url,
            "text": "",
            "error": str(exc),
        }


def extract_candidate_links(
    start_url: str,
    base_urls: list[str],
    max_links: int = 20,
    timeout: int = 12,
) -> list[str]:
    try:
        response = requests.get(start_url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links: list[str] = []

        for anchor in soup.select("a[href]"):
            href = anchor.get("href")
            if not href:
                continue

            full_url = urljoin(start_url, href).split("#")[0]
            if not same_domain(full_url, base_urls):
                continue
            if full_url.lower().endswith(BAD_EXTENSIONS):
                continue
            if full_url not in links:
                links.append(full_url)

        return links[:max_links]
    except Exception:
        return []

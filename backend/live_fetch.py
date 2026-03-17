import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "UVT_Asist/1.0"
}

BAD_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg",
    ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx"
)

PAGE_CACHE = {}
CACHE_TTL = 300  # 5 minute


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def same_domain(url: str, base_urls: list[str]) -> bool:
    try:
        host = urlparse(url).netloc
        return any(host == urlparse(base).netloc for base in base_urls)
    except Exception:
        return False


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "img", "footer"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    return normalize_whitespace(text)


def fetch_page(url: str, timeout: int = 10) -> dict:
    now = time.time()

    if url in PAGE_CACHE:
        cached = PAGE_CACHE[url]
        if now - cached["timestamp"] < CACHE_TTL:
            return cached["data"]

    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else url
        text = clean_html_text(response.text)

        data = {
            "url": url,
            "title": title,
            "text": text[:16000]
        }

        PAGE_CACHE[url] = {
            "timestamp": now,
            "data": data
        }

        return data
    except Exception as e:
        return {
            "url": url,
            "title": url,
            "text": "",
            "error": str(e)
        }


def extract_candidate_links(start_url: str, base_urls: list[str], max_links: int = 20, timeout: int = 10) -> list[str]:
    try:
        response = requests.get(start_url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        links = []

        for a in soup.select("a[href]"):
            href = a.get("href")
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

"""Optional crawler to enrich backend/data/docs.json

Usage:
  python scripts/crawl_uvt.py --faculty uvt --max_pages 30
  python scripts/crawl_uvt.py --faculty fmi --max_pages 30
"""

from __future__ import annotations
import argparse
import json
import os
import re
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_PATH = os.path.join(APP_DIR, "data", "docs.json")

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from faculties import FACULTIES


def strip_noise(soup: BeautifulSoup) -> None:
    """Remove non-content elements to cut boilerplate from indexed text."""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for selector in [
        "header", "footer", "nav", "form", ".nav", ".navbar", ".menu",
        ".sidebar", ".breadcrumb", ".breadcrumbs", ".footer", ".header",
        ".social", ".share", ".popup", ".modal", ".cookie"
    ]:
        for node in soup.select(selector):
            node.decompose()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def extract_sections(html: str, url: str, page_title: str):
    soup = BeautifulSoup(html, "html.parser")
    strip_noise(soup)
    body = soup.body or soup
    elements = body.find_all(["h1", "h2", "h3", "p", "li"])

    sections = []
    buffer = []
    current_heading = None

    def flush_buffer():
        if not buffer:
            return
        text = clean_text(" ".join(buffer))
        buffer.clear()
        if len(text) < 80:
            return
        sections.append({
            "title": page_title,
            "section": current_heading,
            "url": url,
            "text": text,
        })

    for el in elements:
        content = el.get_text(" ", strip=True)
        if not content:
            continue
        if el.name in ["h1", "h2", "h3"]:
            flush_buffer()
            current_heading = content
        else:
            buffer.append(content)
            if len(" ".join(buffer)) > 1600:
                flush_buffer()

    flush_buffer()

    if not sections:
        # Fallback to the whole page if we could not split by headings.
        text = clean_text(body.get_text(" ", strip=True))
        if text:
            sections.append({"title": page_title, "section": None, "url": url, "text": text})

    return sections

def normalize_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")

def same_domain(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc

def crawl(base_urls, max_pages: int = 30):
    base_urls = [normalize_url(u) for u in base_urls]
    q = deque(base_urls)
    seen = set(base_urls)
    out = []
    pages_crawled = 0
    seen_sections = set()

    while q and pages_crawled < max_pages:
        url = q.popleft()
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "UVT_Asist_Crawler/0.1"})
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type",""):
                continue

            html = r.text
            soup_links = BeautifulSoup(html, "html.parser")
            title = soup_links.title.get_text(strip=True) if soup_links.title else url

            sections = extract_sections(html, url, title)
            for sec in sections:
                dedupe_key = (sec["title"], sec.get("section"), sec["text"][:120])
                if dedupe_key in seen_sections:
                    continue
                seen_sections.add(dedupe_key)
                out.append(sec)
            pages_crawled += 1

            for a in soup_links.select("a[href]"):
                href = a.get("href")
                if not href:
                    continue
                nxt = normalize_url(urljoin(url, href))
                if nxt in seen:
                    continue
                if any(nxt.startswith(s) for s in ["mailto:", "tel:"]):
                    continue
                if any(ext in nxt.lower() for ext in [".pdf", ".jpg", ".png", ".zip", ".doc", ".docx"]):
                    continue
                if any(same_domain(nxt, b) for b in base_urls):
                    seen.add(nxt)
                    q.append(nxt)
        except Exception:
            continue

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--faculty", required=True)
    ap.add_argument("--max_pages", type=int, default=30)
    args = ap.parse_args()

    faculty = next((f for f in FACULTIES if f["id"] == args.faculty), None)
    if not faculty:
        raise SystemExit(f"Unknown faculty id: {args.faculty}")

    docs = {}
    if os.path.exists(DOCS_PATH):
        with open(DOCS_PATH, "r", encoding="utf-8") as f:
            docs = json.load(f)

    sections = crawl(faculty["base_urls"], max_pages=args.max_pages)
    docs[args.faculty] = sections

    with open(DOCS_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(sections)} sections for {args.faculty} into {DOCS_PATH}")

if __name__ == "__main__":
    main()

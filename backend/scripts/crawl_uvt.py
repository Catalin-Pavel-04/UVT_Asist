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

from faculties import FACULTIES

def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]

def same_domain(url: str, base: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc

def crawl(base_urls, max_pages: int = 30):
    q = deque(base_urls)
    seen = set(base_urls)
    out = []

    while q and len(out) < max_pages:
        url = q.popleft()
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "UVT_Asist_Crawler/0.1"})
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type",""):
                continue

            html = r.text
            text = clean_text(html)
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else url

            out.append({"title": title, "url": url, "text": text})

            for a in soup.select("a[href]"):
                href = a.get("href")
                if not href:
                    continue
                nxt = urljoin(url, href).split("#")[0]
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

    pages = crawl(faculty["base_urls"], max_pages=args.max_pages)
    docs[args.faculty] = pages

    with open(DOCS_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(pages)} pages for {args.faculty} into {DOCS_PATH}")

if __name__ == "__main__":
    main()

import re


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokenize(text: str) -> list[str]:
    text = normalize(text)
    text = re.sub(r"[^a-z0-9ăâîșț\s-]", " ", text)
    return [tok for tok in text.split() if len(tok) > 2]


def chunk_text(text: str, chunk_size: int = 850, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == text_len:
            break

        start = max(end - overlap, 0)

    return chunks


def score_chunk(question: str, chunk: str, page_title: str = "", page_url: str = "") -> int:
    q = normalize(question)
    q_tokens = tokenize(question)
    hay = normalize(page_title + " " + page_url + " " + chunk)

    score = 0

    for token in q_tokens:
        if token in hay:
            score += 2

    if any(tok in normalize(page_title) for tok in q_tokens):
        score += 3

    if any(tok in normalize(page_url) for tok in q_tokens):
        score += 3

    if "orar" in q:
        if "orar" in normalize(page_title):
            score += 8
        if "/orare" in normalize(page_url):
            score += 12
        if "/orar" in normalize(page_url):
            score += 10

    if "burs" in q:
        if "burs" in normalize(page_title):
            score += 8
        if "/burse" in normalize(page_url):
            score += 12

    if "contact" in q or "secretariat" in q or "program" in q:
        if "contact" in normalize(page_title) or "secretariat" in normalize(page_title):
            score += 8
        if "/contact" in normalize(page_url):
            score += 12

    if "admitere" in q:
        if "admitere" in normalize(page_title):
            score += 8
        if "/admitere" in normalize(page_url):
            score += 12

    if "student" in q:
        if "/studenti" in normalize(page_url):
            score += 8

    return score


def build_page_chunks(pages: list[dict]) -> list[dict]:
    built_chunks = []
    for page in pages:
        page_title = page.get("title", "")
        page_url = page.get("url", "")
        page_text = page.get("text", "")

        for chunk in chunk_text(page_text):
            built_chunks.append({
                "title": page_title,
                "url": page_url,
                "chunk": chunk
            })

    return built_chunks


def rank_prebuilt_chunks(question: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    scored = []

    for item in chunks:
        score = score_chunk(
            question,
            item.get("chunk", ""),
            item.get("title", ""),
            item.get("url", ""),
        )
        if score > 0:
            scored.append({
                "score": score,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "chunk": item.get("chunk", "")
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def rank_chunks(question: str, pages: list[dict], top_k: int = 3) -> list[dict]:
    return rank_prebuilt_chunks(question, build_page_chunks(pages), top_k=top_k)

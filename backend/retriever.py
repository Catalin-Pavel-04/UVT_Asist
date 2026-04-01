import re
import unicodedata

INTENT_TO_PAGE_TYPES = {
    "orar": ["orar", "studenti"],
    "burse": ["burse", "studenti", "regulamente"],
    "contact": ["contact"],
    "admitere": ["admitere"],
    "regulamente": ["regulamente", "studenti"],
    "general": ["general", "studenti", "contact", "admitere", "burse", "orar", "regulamente"],
}
COMMON_TEXT_PATTERNS = (
    (r"\binformatia\b", "informatica"),
    (r"\binformatici\b", "informatica"),
    (r"\binformaticii\b", "informatica"),
    (r"\bfmi\b", "informatica"),
    (r"\bfac(?:ultatea)?(?:\s+de)?\s+info(?:rmatica)?\b", "informatica"),
    (r"\bsecretaruat\b", "secretariat"),
    (r"\bsecreteriat\b", "secretariat"),
    (r"\bbursw\b", "burse"),
    (r"\badmiterw\b", "admitere"),
    (r"\boraru\b", "orar"),
)


def normalize_common_terms(text: str) -> str:
    normalized = f" {text} "

    for pattern, replacement in COMMON_TEXT_PATTERNS:
        normalized = re.sub(pattern, replacement, normalized)

    return re.sub(r"\s+", " ", normalized).strip()


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalize_common_terms(normalized)


def tokenize(text: str) -> list[str]:
    normalized = normalize(text)
    cleaned = "".join(char if char.isalnum() or char in {" ", "-"} else " " for char in normalized)
    return [token for token in cleaned.split() if len(token) > 2]


def detect_intent(question: str) -> str:
    question_text = normalize(question)

    if "orar" in question_text:
        return "orar"
    if "burs" in question_text:
        return "burse"
    if "contact" in question_text or "secretariat" in question_text or "program" in question_text:
        return "contact"
    if "admitere" in question_text or "inscriere" in question_text:
        return "admitere"
    if "regulament" in question_text or "metodologie" in question_text or "procedura" in question_text:
        return "regulamente"

    return "general"


def tokens_related(left: str, right: str) -> bool:
    if left == right:
        return True

    if min(len(left), len(right)) < 4:
        return False

    return (
        left.startswith(right)
        or right.startswith(left)
        or left in right
        or right in left
    )


def count_token_matches(question_tokens: list[str], candidate_tokens: set[str]) -> int:
    matches = 0

    for question_token in question_tokens:
        if any(tokens_related(question_token, candidate_token) for candidate_token in candidate_tokens):
            matches += 1

    return matches


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
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


def score_index_item(question: str, item: dict, selected_faculty: str, intent: str) -> int:
    question_tokens = tokenize(question)
    if not question_tokens:
        return 0

    title = item.get("title", "")
    url = item.get("url", "")
    text = item.get("text", "")
    hay = normalize(f"{title} {url} {text}")
    item_tokens = set(tokenize(f"{title} {url} {text}"))
    score = 0

    for token in question_tokens:
        if token in hay:
            score += 2

    score += count_token_matches(question_tokens, item_tokens) * 2

    item_faculty = item.get("faculty_id")

    if item_faculty == selected_faculty:
        score += 8
    elif item_faculty == "uvt":
        score += 3
    elif selected_faculty != "uvt":
        score -= 6

    if item.get("page_type") in INTENT_TO_PAGE_TYPES.get(intent, ["general"]):
        score += 8

    url = normalize(url)
    title = normalize(title)

    if intent == "orar" and ("/orare" in url or "orar" in title):
        score += 12
    if intent == "burse" and ("/burse" in url or "burs" in title):
        score += 12
    if intent == "contact" and ("/contact" in url or "secretariat" in title or "contact" in title):
        score += 12
    if intent == "admitere" and ("/admitere" in url or "admitere" in title):
        score += 12
    if intent == "regulamente" and any(keyword in f"{title} {url}" for keyword in ("regulament", "metodolog", "procedur")):
        score += 12

    return max(score, 0)


def rank_index(question: str, index_items: list[dict], selected_faculty: str, top_k: int = 5) -> list[dict]:
    intent = detect_intent(question)
    scored = []

    for item in index_items:
        score = score_index_item(question, item, selected_faculty, intent)
        if score > 0:
            scored.append({**item, "score": score})

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def score_chunk(question: str, chunk: str, page_title: str = "", page_url: str = "") -> int:
    question_tokens = tokenize(question)
    if not question_tokens:
        return 0

    intent = detect_intent(question)
    hay = normalize(f"{page_title} {page_url} {chunk}")
    title_norm = normalize(page_title)
    url_norm = normalize(page_url)
    chunk_tokens = set(tokenize(chunk))
    title_tokens = set(tokenize(page_title))
    url_tokens = set(tokenize(page_url))

    score = 0
    for token in question_tokens:
        if token in hay:
            score += 2

    score += count_token_matches(question_tokens, chunk_tokens) * 2
    score += count_token_matches(question_tokens, title_tokens) * 3
    score += count_token_matches(question_tokens, url_tokens) * 3

    if any(tokens_related(token, title_norm) for token in question_tokens):
        score += 3
    if any(tokens_related(token, url_norm) for token in question_tokens):
        score += 3

    if intent == "orar" and ("/orare" in url_norm or "/orar" in url_norm or "orar" in title_norm):
        score += 12
    if intent == "burse" and ("/burse" in url_norm or "burs" in title_norm):
        score += 12
    if intent == "contact" and ("/contact" in url_norm or "secretariat" in title_norm or "contact" in title_norm):
        score += 12
    if intent == "admitere" and ("/admitere" in url_norm or "admitere" in title_norm):
        score += 12
    if intent == "regulamente" and any(
        keyword in f"{title_norm} {url_norm}"
        for keyword in ("regulament", "metodolog", "procedur")
    ):
        score += 12

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
                "chunk": chunk,
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
                "chunk": item.get("chunk", ""),
            })

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def rank_chunks(question: str, pages: list[dict], top_k: int = 3) -> list[dict]:
    return rank_prebuilt_chunks(question, build_page_chunks(pages), top_k=top_k)


def compute_confidence(top_chunks: list[dict]) -> str:
    if not top_chunks:
        return "low"

    best_score = top_chunks[0].get("score", 0)
    if best_score >= 18:
        return "high"
    if best_score >= 10:
        return "medium"
    return "low"

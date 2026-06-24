from __future__ import annotations

import re
import unicodedata

from rag.constants import STOPWORDS


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text).lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[’`']", "'", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_for_tokens(text: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", normalize(text))


def _canonical_token(token: str) -> str:
    return token


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    tokens = []
    for raw_token in _clean_for_tokens(text).split():
        token = _canonical_token(raw_token.strip("-"))
        if not token:
            continue
        if remove_stopwords and (token in STOPWORDS or (len(token) < 2 and not token.isdigit())):
            continue
        tokens.append(token)
    return tokens


def correct_query_terms(question: str) -> tuple[str, list[str]]:
    """Compatibility wrapper.

    Semantic typo correction is intentionally delegated to Ollama query analysis.
    This function now returns only the technically normalized question.
    """
    return normalize(question), []

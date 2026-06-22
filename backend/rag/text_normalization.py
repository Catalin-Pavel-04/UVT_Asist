from __future__ import annotations

import re
import unicodedata
from difflib import get_close_matches

from rag.constants import COMMON_REPLACEMENTS, DOMAIN_VOCABULARY, STOPWORDS, TOKEN_ALIASES

def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text).lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[’`']", "'", value)
    value = re.sub(r"\s+", " ", value).strip()

    for pattern, replacement in COMMON_REPLACEMENTS:
        value = re.sub(pattern, replacement, value)

    return re.sub(r"\s+", " ", value).strip()


def _clean_for_tokens(text: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", normalize(text))


def _canonical_token(token: str) -> str:
    return TOKEN_ALIASES.get(token, token)


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
    corrected_tokens: list[str] = []
    corrections: list[str] = []

    for token in tokenize(question, remove_stopwords=False):
        replacement = token
        if token in STOPWORDS:
            corrected_tokens.append(replacement)
            continue
        if token not in DOMAIN_VOCABULARY and len(token) >= 4 and not token.isdigit():
            matches = get_close_matches(token, DOMAIN_VOCABULARY, n=1, cutoff=0.82)
            if matches:
                replacement = matches[0]

        corrected_tokens.append(replacement)
        if replacement != token:
            corrections.append(f"{token}->{replacement}")

    corrected_text = " ".join(corrected_tokens).strip()
    return corrected_text or normalize(question), corrections

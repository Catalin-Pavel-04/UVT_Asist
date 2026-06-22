from __future__ import annotations

from rag.ranking.faculty import _faculty_score
from rag.ranking.lexical import _contains_any, _contains_token, _counter, _field_overlap_score, _lexical_score
from rag.ranking.page_type import (
    _academic_year_starts,
    _current_academic_year_start,
    _is_document_url,
    _is_homepage,
    _page_type_score,
    _specific_page_score,
    _upload_year_from_path,
    _url_path,
    _url_slug_tokens,
)
from rag.ranking.policy import _is_institutional_policy_document, _policy_score

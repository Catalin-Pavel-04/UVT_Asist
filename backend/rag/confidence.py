from __future__ import annotations

from rag.query_analysis import QueryAnalysis

def compute_confidence(scored_chunks: list[dict], analysis: QueryAnalysis | dict | None = None) -> dict:
    if not scored_chunks:
        return {
            "label": "low",
            "score": 10,
            "reason": "Nu au fost gasite fragmente oficiale suficient de relevante.",
        }

    analysis_dict = analysis.to_dict() if isinstance(analysis, QueryAnalysis) else (analysis or {})
    top = scored_chunks[0]
    best_score = float(top.get("retrieval_score", 0.0))
    second_score = float(scored_chunks[1].get("retrieval_score", 0.0)) if len(scored_chunks) > 1 else 0.0
    unique_pages = len({chunk.get("url") for chunk in scored_chunks[:4] if chunk.get("url")})
    signals = set(top.get("match_signals", []))
    direct_support = any(
        signal.startswith("lexical:")
        or signal in {"all_terms", "phrase", "housing_exact", "housing_content", "academic_calendar"}
        or signal.startswith("hint:")
        or signal.endswith("_path")
        for signal in signals
    )
    lexical_count = 0
    for signal in signals:
        if signal.startswith("lexical:"):
            try:
                lexical_count = max(lexical_count, int(signal.split(":", 1)[1]))
            except ValueError:
                pass

    numeric_score = int(min(100, 28 + best_score * 0.45 + second_score * 0.12 + unique_pages * 4 + len(signals) * 2))

    if not direct_support:
        numeric_score = min(numeric_score, 44)
    elif lexical_count == 0 and not {"housing_exact", "housing_content", "academic_calendar"} & signals:
        numeric_score = min(numeric_score, 58)
    elif lexical_count == 1 and analysis_dict.get("intent") == "general":
        numeric_score = min(numeric_score, 62)

    if "generic_penalty" in signals:
        numeric_score = min(numeric_score, 58)
    if "faculty:other_uvt_scope_penalty" in signals:
        numeric_score = min(numeric_score, 70)
    if "housing_missing" in signals:
        numeric_score = min(numeric_score, 50)
    if "calendar_missing" in signals:
        numeric_score = min(numeric_score, 50)
    if analysis_dict.get("is_policy_question") and not any(signal.startswith("policy:") for signal in signals):
        numeric_score = min(numeric_score, 48)
    if analysis_dict.get("is_policy_question") and "policy:cumulation_missing" in signals:
        numeric_score = min(numeric_score, 72)
    if top.get("page_type") in analysis_dict.get("page_type_preferences", ()):
        numeric_score = min(100, numeric_score + 4)

    if numeric_score >= 78:
        label = "high"
        reason = "Sursele potrivite corespund bine cu intrebarea, facultatea si tipul paginii."
    elif numeric_score >= 52:
        label = "medium"
        reason = "Exista surse oficiale relevante, dar potrivirea are unele limite."
    else:
        label = "low"
        reason = "Au fost gasite doar dovezi partiale sau prea generale."

    return {"label": label, "score": numeric_score, "reason": reason}

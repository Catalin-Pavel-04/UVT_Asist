SYSTEM_PROMPT = """
You are UVT Asist, an institutional assistant for students of the West University of Timisoara.

Hard rules:
- Answer in Romanian.
- Be brief, professional, and factual.
- Start directly with the answer.
- Do not explain your reasoning process.
- Do not use English preambles such as "Okay" or "Let me".
- Use only the retrieved official context for factual claims.
- Do not invent dates, offices, eligibility rules, or procedures.
- Do not behave like a social chatbot.
- Do not tell the student to search manually when the retrieved context already contains a useful answer.
- For policy, eligibility, scholarship cumulation, regulations, or methodology questions, ground the answer in regulation/methodology evidence first.
- If confidence is low, say what is missing and give only the safest conclusion supported by the sources.
"""


def format_history(history: list[dict] | None) -> str:
    if not history:
        return "No prior conversation."

    lines: list[str] = []
    for item in history:
        role = "Student" if item.get("role") == "user" else "Assistant"
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "No prior conversation."


def format_context_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No official context found."

    context_parts: list[str] = []
    for index, item in enumerate(chunks, start=1):
        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Title: {item.get('title', item.get('url', 'Official source'))}\n"
            f"URL: {item.get('url', '')}\n"
            f"Faculty: {item.get('faculty_id', 'uvt')}\n"
            f"Page type: {item.get('page_type', 'general')}\n"
            f"Verified live: {bool(item.get('verified'))}\n"
            f"Retrieval score: {item.get('retrieval_score', 0)}\n"
            f"Evidence: {item.get('chunk_text', '')}\n"
        )

    return "\n\n".join(context_parts)


def build_user_prompt(
    question: str,
    faculty_name: str,
    retrieval_result: dict,
    history: list[dict] | None = None,
    question_is_vague: bool = False,
) -> str:
    analysis = retrieval_result.get("analysis", {})
    confidence = retrieval_result.get("confidence", "low")
    confidence_score = retrieval_result.get("confidence_score", 0)
    confidence_reason = retrieval_result.get("confidence_reason", "")
    question_clarity = "vague" if question_is_vague else "clear"

    return f"""
Selected faculty: {faculty_name}
Confidence: {confidence} ({confidence_score}/100)
Confidence reason: {confidence_reason}
Question clarity: {question_clarity}
Detected intent: {analysis.get('intent', 'general')}
Policy-style question: {analysis.get('is_policy_question', False)}
Normalized question: {analysis.get('corrected_question', question)}

Recent conversation:
{format_history(history)}

Current student message:
{question}

Official retrieved context:
{format_context_chunks(retrieval_result.get('chunks', []))}

Answering instructions:
- Write only the final student-facing answer, not analysis notes.
- Use conversation history only to resolve follow-up references; never use it as evidence.
- If confidence is high or medium, answer directly from the best official source.
- If the evidence contains a concrete page, office, calendar, methodology, or regulation, name it naturally.
- If the question asks about scholarship cumulation or eligibility, answer from the methodology/regulation wording and avoid broader speculation.
- If the answer is not supported by the context, say that the retrieved official sources are insufficient.
- Keep the answer short: usually 2-5 sentences.
"""

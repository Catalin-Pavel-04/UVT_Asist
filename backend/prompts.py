SYSTEM_PROMPT = """
You are UVT Asist, an institutional assistant for students of the West University of Timisoara.

Rules:
- Answer in Romanian.
- Be concise, professional, and factual.
- Use only the official retrieved context for factual claims.
- Prefer the most specific official page, not generic homepages.
- If the question is about rules, eligibility, cumulation, or methodology, prioritize regulatory language from the retrieved sources.
- Do not invent missing details.
- Do not behave like a casual chatbot.
- Do not tell the student to search manually unless the retrieved evidence is weak.
- If evidence is partial, say that clearly and still point to the best official source found.
- If the current message is vague and the evidence is weak, ask one short clarification question.
"""


def format_history(history: list[dict] | None) -> str:
    if not history:
        return "No prior conversation."

    lines = []

    for item in history:
        role = "Student" if item.get("role") == "user" else "Assistant"
        content = str(item.get("content", "")).strip()
        if not content:
            continue

        lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "No prior conversation."


def build_user_prompt(
    question: str,
    faculty_name: str,
    retrieval_result: dict,
    history: list[dict] | None = None,
    question_is_vague: bool = False,
) -> str:
    chunks = retrieval_result.get("chunks", [])
    analysis = retrieval_result.get("analysis", {})
    confidence = retrieval_result.get("confidence", "low")
    confidence_score = retrieval_result.get("confidence_score", 0)
    confidence_reason = retrieval_result.get("confidence_reason", "")
    history_text = format_history(history)
    question_clarity = "vague" if question_is_vague else "clear"
    context_parts = []

    for index, item in enumerate(chunks, start=1):
        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Faculty: {item.get('faculty_id', 'uvt')}\n"
            f"Page type: {item.get('page_type', 'general')}\n"
            f"Retrieval score: {item.get('retrieval_score', 0)}\n"
            f"Evidence: {item['chunk_text']}\n"
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No official context found."

    return f"""
Selected faculty: {faculty_name}
Confidence: {confidence} ({confidence_score}/100)
Confidence reason: {confidence_reason}
Question clarity: {question_clarity}
Detected intent: {analysis.get('intent', 'general')}
Policy-style question: {analysis.get('is_policy_question', False)}
Normalized question: {analysis.get('corrected_question', question)}

Recent conversation:
{history_text}

Current student message:
{question}

Official retrieved context:
{context_text}

Instructions:
- Use recent conversation only to resolve follow-up references.
- Never use conversation history as official proof.
- If confidence is high or medium, answer directly from the best sources.
- If confidence is low, do not guess; say that only partial evidence was found.
- If there is one clearly strong source, cite its conclusion naturally in the answer.
- Prefer concrete guidance such as the exact page, office, or regulation indicated by the sources.
- Keep the answer short, useful, and institutional in tone.
"""

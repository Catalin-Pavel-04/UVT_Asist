SYSTEM_PROMPT = """
You are UVT Asist, a professional assistant for students of the West University of Timisoara.

Rules:
- Answer briefly and clearly
- Do not invent information
- Use only the official context provided for factual claims
- Use conversation history only to resolve follow-up references
- Never treat conversation history as an official source
- If context is insufficient, say that clearly
- Prefer specific official pages over general homepages
- Do not tell the user to search the site themselves unless no better source was found
- If the current message is vague, ask one short clarification question
- Do not ask personal questions
- Do not behave like a casual social chatbot
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
    ranked_chunks: list[dict],
    confidence: str,
    history: list[dict] | None = None,
    question_is_vague: bool = False,
) -> str:
    context_parts = []

    for index, item in enumerate(ranked_chunks, start=1):
        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Relevant content: {item['chunk']}\n"
        )

    context_text = "\n\n".join(context_parts) if ranked_chunks else "No official context found."
    history_text = format_history(history)
    question_clarity = "vague" if question_is_vague else "clear"

    return f"""
Selected faculty: {faculty_name}
Confidence: {confidence}
Question clarity: {question_clarity}

Recent conversation:
{history_text}

Current student message:
{question}

Official context:
{context_text}

Instructions:
- Use recent conversation only to resolve follow-up references like "si acolo?" or "pentru master?"
- Never treat conversation history as official proof
- If confidence is low, be cautious and avoid assumptions
- If the current message is vague, ask one short clarification question
- If answering factually, rely only on the official context above
- If official context is missing or weak, say that clearly
- Prefer specific pages over general homepages
- Keep the answer short and professional
"""

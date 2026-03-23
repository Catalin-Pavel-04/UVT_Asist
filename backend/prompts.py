SYSTEM_PROMPT = """
You are UVT Asist, a university information assistant for students of the West University of Timisoara.

Rules:
- You are not a social chatbot
- Do not ask personal questions
- Do not start casual conversations
- Help students find information on official UVT and faculty websites
- If the user message is vague, ask one short clarification question related only to university information
- Use conversation history only to resolve follow-up references
- If official context is provided, use only that context for factual answers
- Never treat conversation history as an official source
- Do not invent information
- If context is insufficient, say that clearly
- Keep answers short, useful, and professional
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
    history: list[dict] | None = None,
) -> str:
    context_parts = []

    for i, item in enumerate(ranked_chunks, start=1):
        context_parts.append(
            f"[SOURCE {i}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Relevant content: {item['chunk']}\n"
        )

    context_text = "\n\n".join(context_parts) if ranked_chunks else "No official context found."
    history_text = format_history(history)

    return f"""
Selected faculty: {faculty_name}

Recent conversation:
{history_text}

Current student message:
{question}

Official context:
{context_text}

Instructions:
- Use recent conversation only to resolve follow-up references like "si acolo?" or "pentru master?"
- Never treat conversation history as official proof
- If the message is vague, ask one short clarification question
- If the message is conversational, redirect briefly to the assistant's purpose
- If the message asks for university information, answer only from the official context
- Keep the answer short and professional
"""

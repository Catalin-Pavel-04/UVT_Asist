from __future__ import annotations

SYSTEM_PROMPT = """
You are an assistant for UVT students.

Rules:
- Answer briefly
- Use only the official context provided
- Do not invent information
- If context is insufficient, say so clearly
- If clarification is needed, ask only one short clarification question
- Keep the final answer concise and practical
- Answer in Romanian unless the student clearly asked in another language
""".strip()


def build_user_prompt(question: str, faculty_name: str, ranked_chunks: list[dict]) -> str:
    context_parts = []
    for index, item in enumerate(ranked_chunks, start=1):
        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"Relevant content: {item['chunk']}\n"
        )

    context_text = "\n\n".join(context_parts)
    return (
        f"Selected faculty: {faculty_name}\n\n"
        f"Student question:\n{question}\n\n"
        f"Official relevant context:\n{context_text}\n\n"
        "Task:\n"
        "- Give a short answer\n"
        "- Base the answer only on the official context\n"
        "- If the context is not enough, say that clearly\n"
        "- Mention the most useful next step when possible\n"
    )

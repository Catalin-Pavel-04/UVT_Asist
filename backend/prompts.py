from __future__ import annotations

SYSTEM_PROMPT = """
You are UVT Asist, an assistant for students of the West University of Timisoara.

Your role:
- help students find information on the official UVT and faculty websites
- answer briefly, clearly, and naturally
- if the student message is conversational (for example greeting, thanks, or "ce faci"), respond naturally
- if the question is ambiguous, ask one short clarification question
- if official context is provided, use only that context for factual answers
- do not invent information
- if the official context is insufficient, say that clearly
- keep the answer short
- if you ask a clarification question, ask only one
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

    context_text = "\n\n".join(context_parts) if ranked_chunks else "No official context found."

    return f"""
Selected faculty: {faculty_name}

Student message:
{question}

Official context:
{context_text}

Instructions:
- If the message is conversational, respond naturally
- If the message is ambiguous, ask one short clarification question
- If the message asks for factual university information, answer only from the official context
- Keep the answer short
"""

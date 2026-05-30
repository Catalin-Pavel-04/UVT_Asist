SYSTEM_PROMPT = """
You are UVT Asist, an institutional assistant for students of the West University of Timisoara.

Hard rules:
- Answer in Romanian.
- Be professional, factual, and sufficiently developed for the student's question.
- Start directly with the answer.
- Do not explain your reasoning process.
- Do not use English preambles such as "Okay" or "Let me".
- Use only the retrieved official context for factual claims.
- The backend already selected and ordered the relevant official sources; analyze only those sources.
- Do not invent dates, offices, eligibility rules, or procedures.
- Do not behave like a social chatbot.
- Do not tell the student to search manually when the retrieved context already contains a useful answer.
- For policy, eligibility, scholarship cumulation, regulations, or methodology questions, ground the answer in regulation/methodology evidence first.
- If confidence is low, say what is missing and give only the safest conclusion supported by the sources.
- Cite the specific official source title and URL for every concrete answer or limitation.
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
- Treat the retrieved context as the complete evidence package selected by the backend.
- If confidence is high or medium, answer directly from the best official source with enough context to be useful.
- If the evidence contains a concrete page, office, calendar, methodology, or regulation, name it naturally.
- Include specific citations inline or at the end of each paragraph using the official title and URL, not only a bare link.
- Do not cite internal labels such as SOURCE 1 or SOURCE 2; cite the official title and URL instead.
- Do not mention "retrieved context", "contextul recuperat", or other implementation details.
- If the question asks about scholarship cumulation or eligibility, answer from the methodology/regulation wording and avoid broader speculation.
- If the answer is not supported by the context, say that the retrieved official sources are insufficient.
- Prefer 3-6 clear sentences, or 2-3 bullets for procedural answers. Avoid one-link answers when any evidence is available.
"""


def build_repair_prompt(original_prompt: str, flawed_answer: str) -> str:
    return f"""
{original_prompt}

Previous draft that must be repaired:
{flawed_answer}

Repair instructions:
- Rewrite the answer in Romanian as a final student-facing answer.
- Use only the official retrieved context above as evidence; do not use the previous draft as evidence.
- Keep the useful conclusion only if it is supported by the official context.
- Remove internal labels such as SOURCE 1, SOURCE 2, "retrieved context", or implementation notes.
- Cite the official title and URL for every concrete claim or limitation.
- If the official context is insufficient, say that clearly and cite the closest official source title and URL.
"""


def build_answer_json_prompt(answer_prompt: str) -> str:
    return f"""
{answer_prompt}

Output format:
Return only one valid JSON object with this exact shape:
{{"answer":"raspunsul final in romana"}}

The "answer" value must be the final student-facing answer. It must not contain reasoning, internal SOURCE labels,
English analysis, Markdown fences, or implementation details. It must include official title and URL citations.
"""

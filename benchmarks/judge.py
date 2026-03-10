"""LLM-as-judge scoring for benchmark answers."""

import json
import random
from anthropic import Anthropic

client = Anthropic()

JUDGE_PROMPT = """You are evaluating two answers to a coding question about the Click library.

Question: {question}

Ground Truth (the correct answer):
{answer_key}

Answer A:
{answer_a}

Answer B:
{answer_b}

Score each answer on a 1-5 scale for:
- accuracy: correctness of facts, code references, and technical claims
- completeness: coverage of all key points in the ground truth
- relevance: focus on what was asked, without unnecessary tangents or filler

Return ONLY valid JSON (no markdown):
{{"a": {{"accuracy": N, "completeness": N, "relevance": N}}, "b": {{"accuracy": N, "completeness": N, "relevance": N}}}}"""


def judge_answers(
    question: str,
    answer_key: str,
    symdex_answer: str,
    raw_answer: str,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Score both answers using LLM-as-judge.

    Randomizes A/B assignment to avoid position bias.

    Returns:
        {"symdex": {"accuracy": N, "completeness": N, "relevance": N},
         "raw": {"accuracy": N, "completeness": N, "relevance": N},
         "order": "symdex_first" | "raw_first"}
    """
    # Randomize order to prevent position bias
    symdex_first = random.random() < 0.5
    if symdex_first:
        answer_a, answer_b = symdex_answer, raw_answer
    else:
        answer_a, answer_b = raw_answer, symdex_answer

    response = client.messages.create(
        model=model,
        max_tokens=256,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(
                question=question,
                answer_key=answer_key,
                answer_a=answer_a,
                answer_b=answer_b,
            ),
        }],
    )

    text = response.content[0].text.strip()
    scores = json.loads(text)

    if symdex_first:
        return {"symdex": scores["a"], "raw": scores["b"], "order": "symdex_first"}
    else:
        return {"symdex": scores["b"], "raw": scores["a"], "order": "raw_first"}

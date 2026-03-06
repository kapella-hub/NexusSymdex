"""Explain a symbol using LLM or fallback heuristics."""

import os
import time
from typing import Optional

from ..storage import IndexStore
from ._utils import resolve_repo


def _build_explain_prompt(symbol: dict, source: str) -> str:
    """Build a prompt asking the LLM to explain a symbol."""
    return (
        "Explain the following code symbol. Respond in this exact JSON format:\n"
        "{\n"
        '  "purpose": "1-2 sentence description of what it does",\n'
        '  "inputs": [{"name": "param_name", "type": "type_if_visible"}],\n'
        '  "output": "description of return value",\n'
        '  "side_effects": ["list of side effects, or empty"],\n'
        '  "complexity": "simple|moderate|complex"\n'
        "}\n\n"
        f"Symbol: {symbol['kind']} {symbol['name']}\n"
        f"Signature: {symbol['signature']}\n"
        f"File: {symbol['file']}\n\n"
        f"Source code:\n```\n{source}\n```"
    )


def _basic_explanation(symbol: dict, source: str) -> dict:
    """Generate a basic explanation from signature, docstring, and summary."""
    docstring = symbol.get("docstring", "")
    summary = symbol.get("summary", "")
    sig = symbol.get("signature", "")

    purpose = docstring.split("\n")[0].strip() if docstring else summary or f"{symbol['kind']} {symbol['name']}"

    return {
        "purpose": purpose,
        "inputs": [],
        "output": "unknown",
        "side_effects": [],
        "complexity": "unknown",
        "provider": "fallback",
    }


def _parse_json_response(text: str) -> Optional[dict]:
    """Extract JSON from LLM response text."""
    import json

    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from code fence
    for marker in ("```json", "```"):
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

    return None


async def _explain_via_anthropic(prompt: str) -> Optional[dict]:
    """Try explaining via Anthropic API (async to avoid blocking the event loop)."""
    try:
        from anthropic import AsyncAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.content[0].text)
    except Exception:
        return None


async def _explain_via_gemini(prompt: str) -> Optional[dict]:
    """Try explaining via Google Gemini API (async to avoid blocking the event loop)."""
    try:
        import google.generativeai as genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(prompt)
        return _parse_json_response(response.text)
    except Exception:
        return None


async def _explain_via_openai(prompt: str) -> Optional[dict]:
    """Try explaining via OpenAI-compatible endpoint."""
    try:
        import httpx

        api_base = os.environ.get("OPENAI_API_BASE")
        if not api_base:
            return None

        api_base = api_base.rstrip("/")
        api_key = os.environ.get("OPENAI_API_KEY", "local-llm")
        model = os.environ.get("OPENAI_MODEL", "qwen3-coder")

        timeout_str = os.environ.get("OPENAI_TIMEOUT", "60.0")
        try:
            timeout = float(timeout_str)
        except ValueError:
            timeout = 60.0

        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        ) as client:
            response = await client.post(
                f"{api_base}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            return _parse_json_response(text)
    except Exception:
        return None


async def explain_symbol(
    repo: str,
    symbol_id: str,
    storage_path: Optional[str] = None,
) -> dict:
    """Send symbol source to an LLM for structured explanation.

    Tries providers in order: Anthropic > Gemini > OpenAI/local.
    Falls back to basic heuristic explanation if no LLM is available.

    Args:
        repo: Repository identifier (owner/repo or just repo name).
        symbol_id: Symbol ID from get_file_outline or search_symbols.
        storage_path: Custom storage path.

    Returns:
        Dict with structured explanation and _meta envelope.
    """
    start = time.perf_counter()

    try:
        owner, name = resolve_repo(repo, storage_path)
    except ValueError as e:
        return {"error": str(e)}

    store = IndexStore(base_path=storage_path)
    index = store.load_index(owner, name)

    if not index:
        return {"error": f"Repository not indexed: {owner}/{name}"}

    symbol = index.get_symbol(symbol_id)
    if not symbol:
        return {"error": f"Symbol not found: {symbol_id}"}

    source = store.get_symbol_content(owner, name, symbol_id) or ""

    prompt = _build_explain_prompt(symbol, source)

    # Try providers in priority order
    explanation = None
    provider = None

    if os.environ.get("ANTHROPIC_API_KEY"):
        explanation = await _explain_via_anthropic(prompt)
        if explanation:
            provider = "anthropic"

    if not explanation and os.environ.get("GOOGLE_API_KEY"):
        explanation = await _explain_via_gemini(prompt)
        if explanation:
            provider = "gemini"

    if not explanation and os.environ.get("OPENAI_API_BASE"):
        explanation = await _explain_via_openai(prompt)
        if explanation:
            provider = "openai"

    if not explanation:
        explanation = _basic_explanation(symbol, source)
        provider = "fallback"

    elapsed = (time.perf_counter() - start) * 1000

    return {
        "symbol_id": symbol["id"],
        "name": symbol["name"],
        "kind": symbol["kind"],
        "file": symbol["file"],
        "explanation": explanation,
        "_meta": {
            "timing_ms": round(elapsed, 1),
            "provider": provider,
        },
    }

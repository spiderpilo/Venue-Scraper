"""
Rewrites incentive teasers that exceed a word limit using a local LLM (Ollama).
"""

import os
import requests

OLLAMA_MODEL = "llama3.2:3b"
MAX_WORDS = 7

_OLLAMA_URLS = [
    os.environ.get("OLLAMA_URL", ""),
    "http://localhost:11434/api/generate",
    "http://host.docker.internal:11434/api/generate",
]

_PROMPT_WITH_PRICE = (
    "Rewrite this venue incentive description in {max_words} words or fewer. "
    "The price/deal MUST appear in your rewrite. "
    "Only output the rewritten text, nothing else.\n\n"
    "Description: {text}"
)

_PROMPT_NO_PRICE = (
    "Rewrite this venue incentive description in {max_words} words or fewer. "
    "Keep days and times if present. "
    "Only output the rewritten text, nothing else.\n\n"
    "Description: {text}"
)

_active_url = None


def _call_ollama(prompt: str, timeout: float = 15.0) -> str:
    global _active_url
    urls = [_active_url] if _active_url else [u for u in _OLLAMA_URLS if u]
    for url in urls:
        try:
            r = requests.post(
                url,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            if r.status_code == 200:
                _active_url = url
                return r.json().get("response", "").strip()
        except Exception:
            continue
    return ""


def _has_price(text: str) -> bool:
    return "$" in text or "% off" in text.lower()


def rewrite_teaser(teaser: str, max_words: int = MAX_WORDS) -> str:
    """Rewrite a teaser if it exceeds max_words. Returns original if short enough or LLM fails."""
    if not teaser or teaser == "No incentive found":
        return teaser

    if len(teaser.split()) <= max_words:
        return teaser

    template = _PROMPT_WITH_PRICE if _has_price(teaser) else _PROMPT_NO_PRICE
    prompt = template.format(max_words=max_words, text=teaser)
    result = _call_ollama(prompt)

    if not result or len(result) >= len(teaser):
        return teaser

    if _has_price(teaser) and not _has_price(result):
        return teaser

    return result

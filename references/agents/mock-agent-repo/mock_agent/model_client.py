from __future__ import annotations


def call_openai_chat(prompt: str) -> dict[str, object]:
    return {"role": "assistant", "content": prompt}

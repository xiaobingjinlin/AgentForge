"""代码文本清洗工具。"""

from __future__ import annotations

import re

_FENCE_BLOCK = re.compile(r"```(?:[\w-]+)?\s*\n([\s\S]*?)\n```", re.IGNORECASE)


def strip_code_fences(text: str) -> str:
    """移除 LLM 输出中的 Markdown 代码块标记。"""
    stripped = text.strip()
    if not stripped:
        return stripped

    match = _FENCE_BLOCK.search(stripped)
    if match:
        return match.group(1).strip()

    lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()

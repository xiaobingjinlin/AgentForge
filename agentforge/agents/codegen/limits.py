"""代码生成输出体量限制。"""

from __future__ import annotations

MAX_SKELETON_CHARS = 1200
MAX_IMPLEMENT_CHARS = 3500
MAX_TEST_FIX_CHARS = 2000
MAX_SINGLE_TOOL_OUTPUT_CHARS = 3500


def enforce_output_limit(
    text: str,
    *,
    max_chars: int = MAX_SINGLE_TOOL_OUTPUT_CHARS,
    label: str = "output",
) -> tuple[str, bool]:
    """截断超长输出，返回 (内容, 是否被截断)。"""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped, False
    truncated = stripped[:max_chars] + f"\n// ... [{label} truncated at {max_chars} chars]"
    return truncated, True

"""代码生成输出体量限制。"""

from __future__ import annotations

from agentforge.utils.code_text import strip_code_fences

__all__ = ["strip_code_fences", "enforce_output_limit", "MAX_SKELETON_CHARS"]
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
    """清洗 Markdown 标记并截断超长输出，返回 (内容, 是否被截断)。"""
    stripped = strip_code_fences(text)
    if len(stripped) <= max_chars:
        return stripped, False
    truncated = stripped[:max_chars] + f"\n// ... [{label} truncated at {max_chars} chars]"
    return truncated, True

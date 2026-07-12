"""Maven / JVM 编译输出清洗。"""

from __future__ import annotations

import re

# 可忽略的 Maven/JVM 警告行（不影响编译成败判断的展示）
_IGNORABLE_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"restricted method in java\.lang\.System has been called", re.I),
    re.compile(r"java\.lang\.System::load has been called by org\.fusesource\.jansi", re.I),
    re.compile(r"org\.fusesource\.jansi", re.I),
    re.compile(r"WARNING:\s*Please use --enable-native-access=ALL-UNNAMED", re.I),
    re.compile(r"WARNING:\s*Use --enable-native-access", re.I),
    re.compile(r"^\s*WARNING:\s*A terminally deprecated method", re.I),
    re.compile(r"^\s*WARNING:\s*sun\.misc\.Unsafe", re.I),
)


def is_ignorable_maven_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(pattern.search(stripped) for pattern in _IGNORABLE_LINE_PATTERNS)


def sanitize_maven_output(message: str) -> str:
    """移除可忽略的 JVM/Jansi 警告行，保留真实编译信息。"""
    if not message:
        return ""

    kept: list[str] = []
    for line in message.splitlines():
        if is_ignorable_maven_line(line):
            continue
        kept.append(line.rstrip())

    return "\n".join(kept).strip()


def display_maven_message(message: str, *, max_chars: int = 500) -> str:
    """供摘要/前端展示用的 Maven 信息。"""
    cleaned = sanitize_maven_output(message)
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "..."

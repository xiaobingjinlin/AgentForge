"""文档分块。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    start_offset: int
    end_offset: int


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    text: str,
    *,
    max_chars: int = 900,
    overlap: int = 120,
) -> list[TextChunk]:
    """按段落聚合后切块，保留重叠以维持上下文。"""
    if not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    chunks: list[TextChunk] = []
    buffer = ""
    buffer_start = 0
    cursor = 0
    chunk_index = 0

    for para in paragraphs:
        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) <= max_chars:
            if not buffer:
                buffer_start = cursor
            buffer = candidate
            cursor += len(para) + 2
            continue

        if buffer:
            chunks.append(
                TextChunk(
                    index=chunk_index,
                    content=buffer,
                    start_offset=buffer_start,
                    end_offset=buffer_start + len(buffer),
                )
            )
            chunk_index += 1
            tail = buffer[-overlap:] if overlap and len(buffer) > overlap else ""
            buffer = f"{tail}\n\n{para}".strip() if tail else para
            buffer_start = max(0, cursor - len(buffer))
        else:
            buffer = para
            buffer_start = cursor

        while len(buffer) > max_chars:
            piece = buffer[:max_chars]
            chunks.append(
                TextChunk(
                    index=chunk_index,
                    content=piece,
                    start_offset=buffer_start,
                    end_offset=buffer_start + len(piece),
                )
            )
            chunk_index += 1
            buffer = buffer[max_chars - overlap :] if overlap else buffer[max_chars:]
            buffer_start += max_chars - overlap

        cursor += len(para) + 2

    if buffer:
        chunks.append(
            TextChunk(
                index=chunk_index,
                content=buffer,
                start_offset=buffer_start,
                end_offset=buffer_start + len(buffer),
            )
        )

    return chunks

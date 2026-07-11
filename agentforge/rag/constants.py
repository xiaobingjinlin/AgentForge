"""RAG 常量。"""

from __future__ import annotations

from agentforge.core.constants import EMBEDDING_DIM

DEFAULT_TOP_K = 8
DEFAULT_RERANK_TOP_N = 3
RAG_CACHE_TTL_SECONDS = 3600

__all__ = ["DEFAULT_RERANK_TOP_N", "DEFAULT_TOP_K", "EMBEDDING_DIM", "RAG_CACHE_TTL_SECONDS"]

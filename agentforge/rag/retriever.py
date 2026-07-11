"""RAG 检索：域内 top-k + rerank 精排。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from loguru import logger

from agentforge.cache.redis_store import RedisStore
from agentforge.db.vector_store import ChunkRecord, VectorStore
from agentforge.rag.constants import DEFAULT_RERANK_TOP_N, DEFAULT_TOP_K, RAG_CACHE_TTL_SECONDS
from agentforge.rag.embeddings import EmbeddingService
from agentforge.utils.llm_util import LLMUtil


@dataclass
class RetrievedChunk:
    content: str
    domain: str
    source_path: str | None
    similarity: float | None
    rerank_score: float | None = None


class RagRetriever:
    """域内向量召回 + 云端 rerank，Redis 缓存热点查询。"""

    def __init__(
        self,
        store: VectorStore | None = None,
        embedder: EmbeddingService | None = None,
        llm: LLMUtil | None = None,
        cache: RedisStore | None = None,
        *,
        use_cache: bool = True,
        use_rerank: bool = True,
    ) -> None:
        self.store = store or VectorStore()
        self.embedder = embedder or EmbeddingService(llm=llm)
        self.llm = llm
        self.cache = cache or RedisStore()
        self.use_cache = use_cache
        self.use_rerank = use_rerank

    def _cache_key(
        self,
        query: str,
        *,
        domain: str | None,
        framework_version: str | None,
        top_k: int,
        rerank_top_n: int,
    ) -> str:
        raw = f"{domain}|{framework_version}|{top_k}|{rerank_top_n}|{query}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
        return f"rag:search:{digest}"

    def retrieve(
        self,
        query: str,
        *,
        domain: str | None = None,
        framework_version: str | None = "4.0",
        top_k: int = DEFAULT_TOP_K,
        rerank_top_n: int = DEFAULT_RERANK_TOP_N,
    ) -> list[RetrievedChunk]:
        query = query.strip()
        if not query:
            return []

        cache_key = self._cache_key(
            query,
            domain=domain,
            framework_version=framework_version,
            top_k=top_k,
            rerank_top_n=rerank_top_n,
        )
        if self.use_cache:
            cached = self.cache.get_value(cache_key)
            if cached:
                try:
                    payload = json.loads(cached)
                    return [RetrievedChunk(**item) for item in payload]
                except (json.JSONDecodeError, TypeError):
                    pass

        query_vec = self.embedder.embed(query)
        candidates = self.store.search(
            query_vec,
            top_k=top_k,
            domain=domain,
            framework_version=framework_version,
        )
        if not candidates and domain:
            # 域内无命中时回退到全库检索
            candidates = self.store.search(
                query_vec,
                top_k=top_k,
                framework_version=framework_version,
            )

        results = self._to_retrieved(candidates)
        if self.use_rerank and len(results) > 1:
            results = self._rerank(query, results, rerank_top_n=rerank_top_n)
        else:
            results = results[:rerank_top_n]

        if self.use_cache and results:
            payload = [
                {
                    "content": r.content,
                    "domain": r.domain,
                    "source_path": r.source_path,
                    "similarity": r.similarity,
                    "rerank_score": r.rerank_score,
                }
                for r in results
            ]
            self.cache.set_value(
                cache_key,
                json.dumps(payload, ensure_ascii=False),
                ttl_seconds=RAG_CACHE_TTL_SECONDS,
            )

        logger.bind(domain=domain, hits=len(results)).debug("RAG 检索完成")
        return results

    def format_context(self, chunks: list[RetrievedChunk], *, max_chars: int = 2400) -> str:
        if not chunks:
            return "（知识库无相关片段）"

        lines: list[str] = []
        used = 0
        for idx, chunk in enumerate(chunks, start=1):
            source = chunk.source_path or "unknown"
            score = chunk.rerank_score if chunk.rerank_score is not None else chunk.similarity
            header = f"[{idx}] {source}"
            if score is not None:
                header += f" (score={score:.4f})" if isinstance(score, float) else f" (score={score})"
            block = f"{header}\n{chunk.content.strip()}"
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n\n".join(lines)

    def _to_retrieved(self, records: list[ChunkRecord]) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                content=r.content,
                domain=r.domain,
                source_path=r.source_path,
                similarity=r.similarity,
            )
            for r in records
        ]

    def _rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        rerank_top_n: int,
    ) -> list[RetrievedChunk]:
        llm = self.llm or self.embedder.llm
        documents = [c.content for c in candidates]
        try:
            ranked = llm.rerank(query, documents, top_n=min(rerank_top_n, len(documents)))
        except Exception as exc:
            logger.warning("Rerank 失败，回退向量排序: {}", exc)
            return candidates[:rerank_top_n]

        index_map = {i: candidates[i] for i in range(len(candidates))}
        results: list[RetrievedChunk] = []
        for item in ranked:
            idx = item.get("index", item.get("document", {}).get("index"))
            if idx is None:
                continue
            base = index_map.get(int(idx))
            if not base:
                continue
            score = item.get("relevance_score", item.get("score"))
            results.append(
                RetrievedChunk(
                    content=base.content,
                    domain=base.domain,
                    source_path=base.source_path,
                    similarity=base.similarity,
                    rerank_score=float(score) if score is not None else None,
                )
            )
        return results or candidates[:rerank_top_n]

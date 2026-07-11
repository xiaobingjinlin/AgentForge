"""RAG 知识库入库。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from agentforge.core.config import PROJECT_ROOT
from agentforge.db.vector_store import VectorStore
from agentforge.plugins.spring_boot_meta import DOMAIN_EXECUTION_ORDER
from agentforge.rag.chunker import chunk_text
from agentforge.rag.embeddings import EmbeddingService

KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge"
TEMPLATE_ROOT = PROJECT_ROOT / "templates"

_TEXT_SUFFIXES = {".md", ".txt", ".java", ".yml", ".yaml", ".xml", ".properties"}
_DOMAIN_SET = set(DOMAIN_EXECUTION_ORDER)


@dataclass
class IndexStats:
    files_scanned: int = 0
    chunks_indexed: int = 0
    chunks_skipped: int = 0


def _infer_domain_from_path(path: Path) -> str | None:
    parts = [p.lower() for p in path.parts]
    for part in parts:
        if part in _DOMAIN_SET:
            return part
    name = path.stem.lower()
    for domain in _DOMAIN_SET:
        if domain in name:
            return domain
    return None


def _doc_id(source_path: str, framework_version: str) -> str:
    digest = hashlib.sha1(f"{framework_version}:{source_path}".encode()).hexdigest()[:16]
    return f"sb{framework_version.replace('.', '')}-{digest}"


class CorpusIndexer:
    """采集 Spring Boot 文档与示例代码，分块写入 pgvector。"""

    def __init__(
        self,
        store: VectorStore | None = None,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.store = store or VectorStore()
        self.embedder = embedder or EmbeddingService()

    def index_spring_boot(
        self,
        *,
        framework_version: str = "4.0",
        include_templates: bool = True,
        knowledge_root: Path | None = None,
    ) -> IndexStats:
        stats = IndexStats()
        roots: list[Path] = []
        kb = knowledge_root or KNOWLEDGE_ROOT / "spring-boot" / framework_version
        if kb.exists():
            roots.append(kb)
        if include_templates:
            tpl = TEMPLATE_ROOT / "spring-boot" / framework_version
            if tpl.exists():
                roots.append(tpl)

        if not roots:
            raise FileNotFoundError(f"未找到 Spring Boot {framework_version} 知识库目录")

        for root in roots:
            for file_path in sorted(root.rglob("*")):
                if not file_path.is_file() or file_path.suffix.lower() not in _TEXT_SUFFIXES:
                    continue
                stats.files_scanned += 1
                domain = _infer_domain_from_path(file_path.relative_to(root)) or "general"
                rel_path = str(file_path.relative_to(PROJECT_ROOT))
                try:
                    indexed = self._index_file(
                        file_path,
                        domain=domain,
                        framework_version=framework_version,
                        source_path=rel_path,
                    )
                    stats.chunks_indexed += indexed
                except Exception as exc:
                    stats.chunks_skipped += 1
                    logger.warning("跳过文件 {}: {}", rel_path, exc)

        logger.info(
            "RAG 入库完成: files={} chunks={} skipped={}",
            stats.files_scanned,
            stats.chunks_indexed,
            stats.chunks_skipped,
        )
        return stats

    def _index_file(
        self,
        file_path: Path,
        *,
        domain: str,
        framework_version: str,
        source_path: str,
    ) -> int:
        content = file_path.read_text(encoding="utf-8")
        chunks = chunk_text(content)
        if not chunks:
            return 0

        doc_id = _doc_id(source_path, framework_version)
        self.store.delete_by_doc_id(doc_id)

        indexed = 0
        for chunk in chunks:
            embedding = self.embedder.embed(chunk.content)
            self.store.upsert_chunk(
                doc_id=doc_id,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=embedding,
                domain=domain,
                framework_version=framework_version,
                source_path=source_path,
                metadata={
                    "file_name": file_path.name,
                    "chunk_chars": len(chunk.content),
                },
            )
            indexed += 1
        return indexed

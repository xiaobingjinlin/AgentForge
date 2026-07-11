"""框架文档快照：按版本 pin 检索与入库。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from agentforge.core.config import PROJECT_ROOT
from agentforge.db.meta_store import MetaStore
from agentforge.rag.indexer import KNOWLEDGE_ROOT, CorpusIndexer

SUPPORTED_VERSIONS = ("2.7", "3.2", "4.0")


class DocSnapshotService:
    """管理 knowledge/{framework}/{version} 文档快照与索引状态。"""

    def __init__(
        self,
        meta: MetaStore | None = None,
        indexer: CorpusIndexer | None = None,
    ) -> None:
        self.meta = meta or MetaStore()
        self.indexer = indexer or CorpusIndexer()

    def snapshot_path(self, framework: str, version: str) -> Path:
        return KNOWLEDGE_ROOT / framework / version

    def list_versions(self, framework: str = "spring-boot") -> list[dict[str, Any]]:
        root = KNOWLEDGE_ROOT / framework
        if not root.exists():
            return []
        versions = []
        for child in sorted(root.iterdir()):
            if child.is_dir():
                versions.append(self.describe_version(framework, child.name))
        return versions

    def describe_version(self, framework: str, version: str) -> dict[str, Any]:
        path = self.snapshot_path(framework, version)
        file_count = sum(1 for _ in path.rglob("*") if _.is_file()) if path.exists() else 0
        snap = self.meta.get_doc_snapshot(framework, version)
        return {
            "framework": framework,
            "version": version,
            "snapshot_path": str(path.relative_to(PROJECT_ROOT)) if path.exists() else None,
            "file_count": file_count,
            "indexed_at": snap.get("indexed_at") if snap else None,
            "chunk_count": self.meta.count_chunks_for_version(framework, version),
        }

    def register_snapshot(
        self,
        framework: str,
        version: str,
        *,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        path = self.snapshot_path(framework, version)
        if not path.exists():
            raise FileNotFoundError(f"快照目录不存在: {path}")
        rel = str(path.relative_to(PROJECT_ROOT))
        self.meta.upsert_doc_snapshot(
            framework=framework,
            version=version,
            snapshot_path=rel,
            source_url=source_url,
        )
        return self.describe_version(framework, version)

    def index_version(
        self,
        framework: str,
        version: str,
        *,
        include_templates: bool = True,
    ) -> dict[str, Any]:
        if framework != "spring-boot":
            raise ValueError(f"暂不支持框架: {framework}")
        stats = self.indexer.index_spring_boot(
            framework_version=version,
            include_templates=include_templates and version == "4.0",
            knowledge_root=self.snapshot_path(framework, version),
        )
        indexed_at = datetime.now(timezone.utc).isoformat()
        self.meta.upsert_doc_snapshot(
            framework=framework,
            version=version,
            snapshot_path=str(self.snapshot_path(framework, version).relative_to(PROJECT_ROOT)),
            indexed_at=indexed_at,
            metadata={"chunks_indexed": stats.chunks_indexed},
        )
        logger.info("版本 {} 索引完成: {} chunks", version, stats.chunks_indexed)
        return {
            "framework": framework,
            "version": version,
            "indexed_at": indexed_at,
            "chunks_indexed": stats.chunks_indexed,
            "files_scanned": stats.files_scanned,
        }

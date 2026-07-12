"""代码生成/验证错误记忆：写入向量库并在生成时召回。"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from agentforge.db.vector_store import VectorStore
from agentforge.rag.embeddings import EmbeddingService
from agentforge.utils.maven_output import sanitize_maven_output
from agentforge.utils.llm_util import LLMUtil

if TYPE_CHECKING:
    from agentforge.sandbox.project_verifier import FileIssue, ProjectVerifyResult

CODEGEN_ERROR_DOMAIN = "codegen-errors"
DEFAULT_ERROR_TOP_K = 6
DEFAULT_RECENT_LIMIT = 8
MAX_LESSON_CHARS = 2000
DUPLICATE_SIMILARITY_THRESHOLD = float(
    os.getenv("ERROR_MEMORY_DEDUP_THRESHOLD", "0.90")
)
_COMPILE_ERROR_LINE = re.compile(
    r"\[ERROR\]|cannot find symbol|package .+ does not exist|incompatible types|"
    r"method .+ in .+ cannot be applied|';' expected|illegal character",
    re.IGNORECASE,
)


@dataclass
class ErrorLesson:
    content: str
    source_path: str | None = None
    similarity: float | None = None


class CodegenErrorMemory:
    """将验证/修复轮次中的错误沉淀为向量，供后续生成与修复参考。"""

    def __init__(
        self,
        store: VectorStore | None = None,
        embedder: EmbeddingService | None = None,
        llm: LLMUtil | None = None,
    ) -> None:
        self.store = store or VectorStore()
        self.embedder = embedder or EmbeddingService(llm=llm)
        self._llm = llm

    def record_verify_failure(
        self,
        *,
        project_id: str,
        round_idx: int,
        verify: ProjectVerifyResult,
        user_message: str = "",
        codegen_domain: str | None = None,
    ) -> int:
        """记录一轮验证失败；若向量库已有类似错误则跳过。返回实际写入条数。"""
        records = self._build_records(
            project_id=project_id,
            round_idx=round_idx,
            verify=verify,
            user_message=user_message,
            codegen_domain=codegen_domain,
        )
        saved = 0
        skipped = 0
        for record in records:
            try:
                metadata = record.get("metadata") or {}
                dedup_key = metadata.get("dedup_key")
                if dedup_key and self._has_exact_duplicate(
                    dedup_key,
                    framework_version=record.get("framework_version"),
                ):
                    skipped += 1
                    logger.bind(project_id=project_id).debug(
                        "跳过重复错误记忆(dedup_key): {}",
                        record.get("source_path"),
                    )
                    continue

                canonical = record.get("canonical_content") or record["content"]
                dedup_vec = self.embedder.embed(canonical)
                if self._has_similar_error(
                    dedup_vec,
                    framework_version=record.get("framework_version"),
                ):
                    skipped += 1
                    logger.bind(project_id=project_id).debug(
                        "跳过相似错误记忆: {}",
                        record.get("source_path"),
                    )
                    continue

                storage_vec = self.embedder.embed(record["content"])
                self.store.upsert_chunk(
                    doc_id=record["doc_id"],
                    chunk_index=0,
                    content=record["content"],
                    embedding=storage_vec,
                    domain=CODEGEN_ERROR_DOMAIN,
                    framework_version=record.get("framework_version"),
                    source_path=record.get("source_path"),
                    metadata=record.get("metadata"),
                )
                saved += 1
            except Exception as exc:
                logger.warning("错误记忆写入失败 doc_id={}: {}", record.get("doc_id"), exc)

        if skipped:
            logger.bind(project_id=project_id).info(
                "错误记忆去重: 写入 {} 条，跳过相似 {} 条",
                saved,
                skipped,
            )
        return saved

    def _has_similar_error(
        self,
        embedding: list[float],
        *,
        framework_version: str | None,
    ) -> bool:
        hits = self.store.search(
            embedding,
            top_k=1,
            domain=CODEGEN_ERROR_DOMAIN,
            framework_version=framework_version,
        )
        if not hits:
            return False
        similarity = hits[0].similarity
        return (
            similarity is not None
            and similarity >= DUPLICATE_SIMILARITY_THRESHOLD
        )

    def _has_exact_duplicate(
        self,
        dedup_key: str,
        *,
        framework_version: str | None,
    ) -> bool:
        try:
            recent = self.store.list_recent(
                domain=CODEGEN_ERROR_DOMAIN,
                limit=100,
                framework_version=framework_version,
            )
        except Exception as exc:
            logger.warning("错误记忆精确去重查询失败: {}", exc)
            return False

        for hit in recent:
            meta = hit.metadata or {}
            if meta.get("dedup_key") == dedup_key:
                return True
        return False

    def retrieve_for_codegen(
        self,
        query: str,
        *,
        codegen_domain: str | None = None,
        framework_version: str = "4.0",
        top_k: int = DEFAULT_ERROR_TOP_K,
        recent_limit: int = DEFAULT_RECENT_LIMIT,
    ) -> str:
        """召回与当前任务相关的历史错误教训，供 Prompt 注入。"""
        query = query.strip()
        if not query:
            return ""

        lessons: list[ErrorLesson] = []
        seen: set[str] = set()

        try:
            query_vec = self.embedder.embed(query)
            hits = self.store.search(
                query_vec,
                top_k=top_k,
                domain=CODEGEN_ERROR_DOMAIN,
                framework_version=framework_version,
            )
            for hit in hits:
                key = hit.content[:120]
                if key in seen:
                    continue
                seen.add(key)
                lessons.append(
                    ErrorLesson(
                        content=hit.content,
                        source_path=hit.source_path,
                        similarity=hit.similarity,
                    )
                )
        except Exception as exc:
            logger.warning("错误记忆向量检索失败: {}", exc)

        try:
            recent = self.store.list_recent(
                domain=CODEGEN_ERROR_DOMAIN,
                limit=recent_limit,
                framework_version=framework_version,
            )
            for hit in recent:
                meta = hit.metadata or {}
                if codegen_domain and meta.get("codegen_domain") not in (None, codegen_domain):
                    continue
                key = hit.content[:120]
                if key in seen:
                    continue
                seen.add(key)
                lessons.append(
                    ErrorLesson(
                        content=hit.content,
                        source_path=hit.source_path,
                    )
                )
        except Exception as exc:
            logger.warning("错误记忆最近列表失败: {}", exc)

        if not lessons:
            return ""

        return self.format_lessons(lessons)

    @staticmethod
    def format_lessons(lessons: list[ErrorLesson], *, max_chars: int = MAX_LESSON_CHARS) -> str:
        lines = ["【历史代码错误教训 — 生成时必须避免重复】"]
        used = len(lines[0])
        for idx, lesson in enumerate(lessons, start=1):
            source = lesson.source_path or "unknown"
            header = f"[{idx}] {source}"
            if lesson.similarity is not None:
                header += f" (sim={lesson.similarity:.3f})"
            block = f"{header}\n{lesson.content.strip()}"
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n\n".join(lines)

    def _build_records(
        self,
        *,
        project_id: str,
        round_idx: int,
        verify: ProjectVerifyResult,
        user_message: str,
        codegen_domain: str | None,
    ) -> list[dict]:
        from agentforge.sandbox.project_verifier import ProjectVerifyResult as _PVR

        if not isinstance(verify, _PVR):
            return []

        records: list[dict] = []
        user_snippet = user_message.strip()[:300]

        if verify.static_issues:
            for item in verify.static_issues:
                domain_hint = codegen_domain or _infer_codegen_domain(item.path)
                issues_text = "; ".join(sorted(item.issues))
                canonical_content = (
                    f"静态检查失败\n"
                    f"技术域: {domain_hint or 'unknown'}\n"
                    f"问题: {issues_text}"
                )
                content = (
                    f"验证失败（第 {round_idx} 轮）\n"
                    f"项目: {project_id}\n"
                    f"文件: {item.path}\n"
                    f"技术域: {domain_hint or 'unknown'}\n"
                    f"静态问题: {issues_text}\n"
                    f"用户需求摘要: {user_snippet}\n"
                    f"教训: 生成 Java 代码时禁止重复上述问题（纯源码、英文类名、package 完整、无 Markdown 围栏）。"
                )
                records.append({
                    "doc_id": f"ce-{uuid.uuid4().hex[:16]}",
                    "content": content,
                    "canonical_content": canonical_content,
                    "source_path": item.path,
                    "framework_version": "4.0",
                    "metadata": {
                        "kind": "verify-static",
                        "project_id": project_id,
                        "round": round_idx,
                        "issues": item.issues,
                        "codegen_domain": domain_hint,
                        "user_message": user_snippet,
                        "dedup_key": f"static|{domain_hint}|{issues_text}",
                    },
                })

        if verify.compile_exit_code not in (None, 0) and verify.compile_message:
            cleaned_compile = sanitize_maven_output(verify.compile_message)
            if cleaned_compile:
                compile_snippet = cleaned_compile[:1200]
                normalized_compile = _normalize_compile_for_dedup(compile_snippet)
                canonical_content = (
                    f"Maven 编译失败\n"
                    f"技术域: {codegen_domain or 'project'}\n"
                    f"{normalized_compile}"
                )
                content = (
                    f"验证失败（第 {round_idx} 轮）\n"
                    f"项目: {project_id}\n"
                    f"类型: Maven 编译错误\n"
                    f"技术域: {codegen_domain or 'project'}\n"
                    f"编译输出:\n{compile_snippet}\n"
                    f"用户需求摘要: {user_snippet}\n"
                    f"教训: 生成代码时注意依赖、import、类型与接口一致性，确保 `mvn compile` 可通过。"
                )
                records.append({
                    "doc_id": f"ce-{uuid.uuid4().hex[:16]}",
                    "content": content,
                    "canonical_content": canonical_content,
                    "source_path": "maven-compile",
                    "framework_version": "4.0",
                    "metadata": {
                        "kind": "verify-compile",
                        "project_id": project_id,
                        "round": round_idx,
                        "compile_exit_code": verify.compile_exit_code,
                        "codegen_domain": codegen_domain,
                        "user_message": user_snippet,
                        "dedup_key": f"compile|{codegen_domain or 'project'}|{normalized_compile[:200]}",
                    },
                })

        return records


def _infer_codegen_domain(file_path: str) -> str | None:
    parts = file_path.replace("\\", "/").split("/")
    try:
        idx = parts.index("demo")
    except ValueError:
        return None
    if idx + 1 < len(parts):
        return parts[idx + 1]
    return None


def _normalize_compile_for_dedup(message: str) -> str:
    """提取编译错误关键行，用于相似错误去重。"""
    lines: list[str] = []
    for line in message.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _COMPILE_ERROR_LINE.search(stripped):
            lines.append(stripped)
    if lines:
        return "\n".join(lines[:10])
    return message.strip()[:400]

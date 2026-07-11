"""PostgreSQL + pgvector 向量存储。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from agentforge.db.connection import VECTOR_DATABASE, build_dsn

from agentforge.core.constants import EMBEDDING_DIM


@dataclass
class ChunkRecord:
    id: int
    doc_id: str
    chunk_index: int
    domain: str
    content: str
    similarity: float | None = None
    framework_version: str | None = None
    source_path: str | None = None
    metadata: dict[str, Any] | None = None


class VectorStore:
    """AgentForge RAG 向量库封装。"""

    def __init__(self, pool: ConnectionPool | None = None) -> None:
        self._pool = pool
        self._owned_pool: ConnectionPool | None = None

    def _get_pool(self) -> ConnectionPool:
        if self._pool is not None:
            return self._pool
        try:
            from agentforge.core.pools import PoolManager

            return PoolManager.vector_pool()
        except RuntimeError:
            if self._owned_pool is None:
                from pgvector.psycopg import register_vector

                def _configure(conn: psycopg.Connection) -> None:
                    conn.autocommit = True
                    register_vector(conn)
                    with conn.cursor() as cur:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

                self._owned_pool = ConnectionPool(
                    conninfo=build_dsn(VECTOR_DATABASE),
                    min_size=1,
                    max_size=2,
                    configure=_configure,
                    open=True,
                )
            return self._owned_pool

    def close(self) -> None:
        if self._owned_pool is not None:
            self._owned_pool.close()
            self._owned_pool = None

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ping(self) -> dict[str, Any]:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                pg_version = cur.fetchone()[0]
                cur.execute(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("pgvector 扩展未安装")
                vector_version = row[0]
                cur.execute("SELECT current_database()")
                database = cur.fetchone()[0]

        return {
            "database": database,
            "pg_version": pg_version.split(",")[0],
            "pgvector_version": vector_version,
            "embedding_dim": EMBEDDING_DIM,
        }

    def init_schema(self, schema_sql_path: str | None = None) -> None:
        if schema_sql_path is None:
            schema_sql_path = str(
                Path(__file__).resolve().parents[2] / "sql" / "init_vector_schema.sql"
            )
        with open(schema_sql_path, encoding="utf-8") as f:
            sql = f.read()
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def upsert_chunk(
        self,
        *,
        doc_id: str,
        chunk_index: int,
        content: str,
        embedding: list[float],
        domain: str = "spring-boot",
        framework_version: str | None = None,
        source_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(f"向量维度应为 {EMBEDDING_DIM}，实际为 {len(embedding)}")

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rag_chunks (
                        doc_id, chunk_index, domain, framework_version,
                        source_path, content, metadata, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (doc_id, chunk_index) DO UPDATE SET
                        domain = EXCLUDED.domain,
                        framework_version = EXCLUDED.framework_version,
                        source_path = EXCLUDED.source_path,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                    RETURNING id
                    """,
                    (
                        doc_id,
                        chunk_index,
                        domain,
                        framework_version,
                        source_path,
                        content,
                        psycopg.types.json.Json(metadata or {}),
                        embedding,
                    ),
                )
                return int(cur.fetchone()[0])

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        domain: str | None = None,
        framework_version: str | None = None,
    ) -> list[ChunkRecord]:
        if len(query_embedding) != EMBEDDING_DIM:
            raise ValueError(f"向量维度应为 {EMBEDDING_DIM}，实际为 {len(query_embedding)}")

        conditions = ["embedding IS NOT NULL"]
        filter_params: list[Any] = []
        if domain:
            conditions.append("domain = %s")
            filter_params.append(domain)
        if framework_version:
            conditions.append("framework_version = %s")
            filter_params.append(framework_version)

        where_clause = " AND ".join(conditions)
        params = [query_embedding, *filter_params, query_embedding, top_k]

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        id, doc_id, chunk_index, domain, content,
                        framework_version, source_path, metadata,
                        1 - (embedding <=> %s::vector) AS similarity
                    FROM rag_chunks
                    WHERE {where_clause}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()

        return [
            ChunkRecord(
                id=row[0],
                doc_id=row[1],
                chunk_index=row[2],
                domain=row[3],
                content=row[4],
                framework_version=row[5],
                source_path=row[6],
                metadata=row[7],
                similarity=float(row[8]),
            )
            for row in rows
        ]

    def count_chunks(self, domain: str | None = None) -> int:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                if domain:
                    cur.execute(
                        "SELECT COUNT(*) FROM rag_chunks WHERE domain = %s", (domain,)
                    )
                else:
                    cur.execute("SELECT COUNT(*) FROM rag_chunks")
                return int(cur.fetchone()[0])

    def delete_by_doc_id(self, doc_id: str) -> int:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM rag_chunks WHERE doc_id = %s RETURNING id", (doc_id,)
                )
                return len(cur.fetchall())

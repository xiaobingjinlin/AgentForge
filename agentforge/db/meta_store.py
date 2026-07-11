"""关系型元数据存储（会话、项目、生成历史、文档快照）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg_pool import ConnectionPool

from agentforge.db.connection import META_DATABASE, build_dsn


class MetaStore:
    """AgentForge 关系型数据库封装。"""

    def __init__(self, pool: ConnectionPool | None = None) -> None:
        self._pool = pool
        self._owned_pool: ConnectionPool | None = None

    def _get_pool(self) -> ConnectionPool:
        if self._pool is not None:
            return self._pool
        try:
            from agentforge.core.pools import PoolManager

            return PoolManager.meta_pool()
        except RuntimeError:
            if self._owned_pool is None:
                import psycopg

                def _configure(conn: psycopg.Connection) -> None:
                    conn.autocommit = True

                self._owned_pool = ConnectionPool(
                    conninfo=build_dsn(META_DATABASE),
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

    def __enter__(self) -> MetaStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ping(self) -> dict[str, Any]:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                pg_version = cur.fetchone()[0]
                cur.execute("SELECT current_database()")
                database = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    """
                )
                table_count = int(cur.fetchone()[0])

        return {
            "database": database,
            "pg_version": pg_version.split(",")[0],
            "table_count": table_count,
        }

    def init_schema(self, schema_sql_path: str | None = None) -> None:
        if schema_sql_path is None:
            schema_sql_path = str(
                Path(__file__).resolve().parents[2] / "sql" / "init_meta_schema.sql"
            )
        with open(schema_sql_path, encoding="utf-8") as f:
            sql = f.read()
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def create_project(
        self,
        name: str,
        *,
        tech_stack: str = "spring-boot",
        framework_version: str | None = None,
        root_path: str | None = None,
    ) -> str:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO projects (name, tech_stack, framework_version, root_path)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id::text
                    """,
                    (name, tech_stack, framework_version, root_path),
                )
                project_id = str(cur.fetchone()[0])
        self.update_project_metadata(project_id, {"template_stack": ["base"]})
        return project_id

    def create_session(self, project_id: str, title: str | None = None) -> str:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sessions (project_id, title)
                    VALUES (%s::uuid, %s)
                    RETURNING id::text
                    """,
                    (project_id, title),
                )
                return str(cur.fetchone()[0])

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, project_id::text, title, created_at
                    FROM sessions WHERE id = %s::uuid
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "project_id": row[1],
                    "title": row[2],
                    "created_at": row[3].isoformat(),
                }

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, role, content, created_at
                    FROM session_messages
                    WHERE session_id = %s::uuid
                    ORDER BY id ASC
                    """,
                    (session_id,),
                )
                return [
                    {
                        "id": row[0],
                        "role": row[1],
                        "content": row[2],
                        "created_at": row[3].isoformat(),
                    }
                    for row in cur.fetchall()
                ]

    def add_message(self, session_id: str, role: str, content: str) -> int:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_messages (session_id, role, content)
                    VALUES (%s::uuid, %s, %s)
                    RETURNING id
                    """,
                    (session_id, role, content),
                )
                return int(cur.fetchone()[0])

    def count_projects(self) -> int:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM projects")
                return int(cur.fetchone()[0])

    def delete_project(self, project_id: str) -> None:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM projects WHERE id = %s::uuid", (project_id,))

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, name, tech_stack, framework_version, root_path,
                           metadata, created_at, updated_at
                    FROM projects WHERE id = %s::uuid
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "name": row[1],
                    "tech_stack": row[2],
                    "framework_version": row[3],
                    "root_path": row[4],
                    "metadata": row[5] or {},
                    "created_at": row[6].isoformat(),
                    "updated_at": row[7].isoformat(),
                }

    def list_projects(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, name, tech_stack, framework_version, created_at
                    FROM projects ORDER BY created_at DESC LIMIT %s
                    """,
                    (limit,),
                )
                return [
                    {
                        "id": row[0],
                        "name": row[1],
                        "tech_stack": row[2],
                        "framework_version": row[3],
                        "created_at": row[4].isoformat(),
                    }
                    for row in cur.fetchall()
                ]

    def update_project_metadata(self, project_id: str, metadata: dict[str, Any]) -> None:
        import psycopg

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE projects
                    SET metadata = metadata || %s::jsonb, updated_at = NOW()
                    WHERE id = %s::uuid
                    """,
                    (psycopg.types.json.Json(metadata), project_id),
                )

    def save_project_structure(self, project_id: str, files: list[str]) -> None:
        self.update_project_metadata(
            project_id,
            {"file_tree": files, "structure_updated_at": _utc_now()},
        )

    def add_generation_record(
        self,
        *,
        session_id: str | None,
        project_id: str | None,
        stage: str,
        file_path: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        import psycopg

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO generation_records (
                        session_id, project_id, stage, file_path, content, metadata
                    )
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        session_id,
                        project_id,
                        stage,
                        file_path,
                        content,
                        psycopg.types.json.Json(metadata or {}),
                    ),
                )
                return int(cur.fetchone()[0])

    def list_generation_records(
        self,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = %s::uuid")
            params.append(project_id)
        if session_id:
            conditions.append("session_id = %s::uuid")
            params.append(session_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, session_id::text, project_id::text, stage, file_path,
                           LEFT(content, 500), metadata, created_at
                    FROM generation_records
                    {where}
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    params,
                )
                return [
                    {
                        "id": row[0],
                        "session_id": row[1],
                        "project_id": row[2],
                        "stage": row[3],
                        "file_path": row[4],
                        "content_preview": row[5],
                        "metadata": row[6] or {},
                        "created_at": row[7].isoformat(),
                    }
                    for row in cur.fetchall()
                ]

    def upsert_doc_snapshot(
        self,
        *,
        framework: str,
        version: str,
        snapshot_path: str,
        source_url: str | None = None,
        indexed_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        import psycopg

        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO doc_snapshots (
                        framework, version, source_url, snapshot_path, indexed_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (framework, version) DO UPDATE SET
                        source_url = COALESCE(EXCLUDED.source_url, doc_snapshots.source_url),
                        snapshot_path = EXCLUDED.snapshot_path,
                        indexed_at = COALESCE(EXCLUDED.indexed_at, doc_snapshots.indexed_at),
                        metadata = doc_snapshots.metadata || EXCLUDED.metadata
                    RETURNING id
                    """,
                    (
                        framework,
                        version,
                        source_url,
                        snapshot_path,
                        indexed_at,
                        psycopg.types.json.Json(metadata or {}),
                    ),
                )
                return int(cur.fetchone()[0])

    def get_doc_snapshot(self, framework: str, version: str) -> dict[str, Any] | None:
        with self._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, framework, version, source_url, snapshot_path,
                           indexed_at, metadata, created_at
                    FROM doc_snapshots
                    WHERE framework = %s AND version = %s
                    """,
                    (framework, version),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "framework": row[1],
                    "version": row[2],
                    "source_url": row[3],
                    "snapshot_path": row[4],
                    "indexed_at": row[5].isoformat() if row[5] else None,
                    "metadata": row[6] or {},
                    "created_at": row[7].isoformat(),
                }

    def count_chunks_for_version(self, framework: str, version: str) -> int:
        """从 doc_snapshots metadata 读取 chunk 计数（索引后写入）。"""
        snap = self.get_doc_snapshot(framework, version)
        if not snap:
            return 0
        return int(snap.get("metadata", {}).get("chunks_indexed", 0))


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

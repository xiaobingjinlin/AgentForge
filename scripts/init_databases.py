#!/usr/bin/env python3
"""一键初始化 AgentForge PostgreSQL：建库 → 建表 → 可选 RAG 入库。

依赖环境变量（与运行时相同）：
  POSTGRESQL_USER / POSTGRESQL_PASSWORD（或 PGUSER / PGPASSWORD）
  PGHOST（默认 localhost）、PGPORT（默认 5432）
  EMBEDDING_DIM（默认 2048，影响向量表维度）

用法：
  .venv/bin/python scripts/init_databases.py
  .venv/bin/python scripts/init_databases.py --index-rag
  .venv/bin/python scripts/init_databases.py --index-rag --framework-version 4.0
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg
from psycopg import sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agentforge.core.constants import EMBEDDING_DIM  # noqa: E402
from agentforge.db.connection import (  # noqa: E402
    META_DATABASE,
    VECTOR_DATABASE,
    build_admin_dsn,
    get_password,
    get_user,
)
from agentforge.db.meta_store import MetaStore  # noqa: E402
from agentforge.db.vector_store import VectorStore  # noqa: E402

SQL_DIR = PROJECT_ROOT / "sql"
ADMIN_DB = "postgres"


def _log(step: str, message: str) -> None:
    print(f"[{step}] {message}")


def _connect(database: str) -> psycopg.Connection:
    return psycopg.connect(build_admin_dsn(database), autocommit=True)


def ensure_database(admin_conn: psycopg.Connection, database: str) -> bool:
    """若库不存在则创建，返回是否新建。"""
    with admin_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        if cur.fetchone():
            return False
        cur.execute(
            sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(database)
            )
        )
    return True


def _read_sql(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL 文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def _hnsw_index_sql(dim: int) -> str:
    if dim <= 2000:
        return (
            "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw\n"
            "    ON rag_chunks USING hnsw (embedding vector_cosine_ops);"
        )
    return (
        "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw\n"
        f"    ON rag_chunks USING hnsw ((embedding::halfvec({dim})) halfvec_cosine_ops);"
    )


def _vector_schema_sql(dim: int) -> str:
    raw = _read_sql(SQL_DIR / "init_vector_schema.sql")
    sql_text = re.sub(r"vector\(\d+\)", f"vector({dim})", raw)
    sql_text = re.sub(
        r"CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw.*?;",
        _hnsw_index_sql(dim),
        sql_text,
        flags=re.DOTALL,
    )
    return sql_text


def _current_embedding_dim(conn: psycopg.Connection) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND c.relname = 'rag_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    match = re.search(r"vector\((\d+)\)", row[0])
    return int(match.group(1)) if match else None


def init_vector_schema(store: VectorStore, *, dim: int, force_recreate: bool) -> None:
    current_dim = None
    with store._get_pool().connection() as conn:
        current_dim = _current_embedding_dim(conn)

    if current_dim is not None and current_dim != dim:
        if not force_recreate:
            raise RuntimeError(
                f"rag_chunks.embedding 当前维度为 {current_dim}，与 EMBEDDING_DIM={dim} 不一致。"
                "请加 --force-vector-recreate 重建向量表（会清空已有向量数据）。"
            )
        _log("vector", f"维度 {current_dim} → {dim}，重建 rag_chunks …")
        migrate_sql = _read_sql(SQL_DIR / "migrate_rag_embedding_dim.sql")
        migrate_sql = re.sub(r"vector\(\d+\)", f"vector({dim})", migrate_sql)
        migrate_sql = re.sub(
            r"CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw.*?;",
            _hnsw_index_sql(dim),
            migrate_sql,
            flags=re.DOTALL,
        )
        with store._get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(migrate_sql)
        return

    sql_text = _vector_schema_sql(dim)
    with store._get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
    if current_dim is None:
        _log("vector", f"向量表已初始化（dim={dim}）")
    else:
        _log("vector", f"向量表已就绪（dim={current_dim}）")


def index_rag_corpus(*, framework_version: str, include_templates: bool) -> int:
    from agentforge.rag.indexer import CorpusIndexer

    store = VectorStore()
    try:
        indexer = CorpusIndexer(store=store)
        stats = indexer.index_spring_boot(
            framework_version=framework_version,
            include_templates=include_templates,
        )
        total = store.count_chunks()
        _log("rag", f"扫描 {stats.files_scanned} 个文件，写入 {stats.chunks_indexed} 个 chunk，库内总量 {total}")
        return total
    finally:
        store.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentForge 数据库一键初始化")
    parser.add_argument(
        "--index-rag",
        action="store_true",
        help="初始化后索引 knowledge/ 到向量库（需配置 QWEN_API_KEY）",
    )
    parser.add_argument(
        "--framework-version",
        default="4.0",
        help="RAG 入库的 Spring Boot 版本目录（默认 4.0）",
    )
    parser.add_argument(
        "--no-templates",
        action="store_true",
        help="RAG 入库时不索引 templates 示例代码",
    )
    parser.add_argument(
        "--force-vector-recreate",
        action="store_true",
        help="向量维度不一致时强制重建 rag_chunks（清空向量数据）",
    )
    parser.add_argument(
        "--skip-meta",
        action="store_true",
        help="跳过关系库表结构初始化（仅建库）",
    )
    parser.add_argument(
        "--skip-vector",
        action="store_true",
        help="跳过向量库表结构初始化（仅建库）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user = get_user()

    print("=" * 60)
    print("AgentForge 数据库一键初始化")
    print("=" * 60)
    _log("env", f"用户={user}，向量维度 EMBEDDING_DIM={EMBEDDING_DIM}")
    if not get_password():
        _log("warn", "未设置 POSTGRESQL_PASSWORD / PGPASSWORD，将尝试无密码连接")

    # 1. 连通性 + 建库
    try:
        with _connect(ADMIN_DB) as admin_conn:
            with admin_conn.cursor() as cur:
                cur.execute("SELECT version()")
                pg_version = cur.fetchone()[0].split(",")[0]
            _log("postgres", f"已连接 {ADMIN_DB}（{pg_version}）")

            for db_name in (VECTOR_DATABASE, META_DATABASE):
                created = ensure_database(admin_conn, db_name)
                if created:
                    _log("database", f"已创建库 {db_name}")
                else:
                    _log("database", f"库已存在 {db_name}")
    except Exception as exc:
        print(f"✗ 建库失败: {exc}")
        print("  请确认 PostgreSQL 已启动，且 POSTGRESQL_USER / POSTGRESQL_PASSWORD 正确。")
        raise SystemExit(1) from exc

    meta_store: MetaStore | None = None
    vector_store: VectorStore | None = None

    try:
        # 2. 关系库表结构
        if not args.skip_meta:
            meta_store = MetaStore()
            meta_store.init_schema()
            info = meta_store.ping()
            _log("meta", f"{info['database']} 表数量={info['table_count']}")

        # 3. 向量库表结构
        if not args.skip_vector:
            vector_store = VectorStore()
            init_vector_schema(
                vector_store,
                dim=EMBEDDING_DIM,
                force_recreate=args.force_vector_recreate,
            )
            info = vector_store.ping()
            _log(
                "vector",
                f"{info['database']} pgvector={info['pgvector_version']} dim={info['embedding_dim']}",
            )

        # 4. 可选 RAG 入库
        if args.index_rag:
            if args.skip_vector:
                print("✗ --index-rag 不能与 --skip-vector 同时使用")
                raise SystemExit(1)
            _log("rag", f"开始索引 Spring Boot {args.framework_version} …")
            try:
                index_rag_corpus(
                    framework_version=args.framework_version,
                    include_templates=not args.no_templates,
                )
            except Exception as exc:
                print(f"✗ RAG 入库失败: {exc}")
                print("  数据库已初始化；可稍后单独执行：")
                print("  .venv/bin/python scripts/index_rag_corpus.py")
                raise SystemExit(1) from exc

        print("=" * 60)
        print("数据库初始化完成")
        print("=" * 60)
        print(f"  向量库: {VECTOR_DATABASE}")
        print(f"  关系库: {META_DATABASE}")
        if not args.index_rag:
            print("  提示: 首次部署可执行 RAG 入库：")
            print("    .venv/bin/python scripts/init_databases.py --index-rag")
            print("  或：.venv/bin/python scripts/index_rag_corpus.py")
    except Exception as exc:
        print(f"✗ 初始化失败: {exc}")
        raise SystemExit(1) from exc
    finally:
        if meta_store is not None:
            meta_store.close()
        if vector_store is not None:
            vector_store.close()


if __name__ == "__main__":
    main()

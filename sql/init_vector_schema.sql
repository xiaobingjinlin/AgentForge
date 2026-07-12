-- AgentForge RAG 向量表结构
-- Embedding 维度: 2048 (云端 text-embedding-v4)；本地 Qwen3-Embedding-4B 可设 EMBEDDING_DIM=2560

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      VARCHAR(128) NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    domain      VARCHAR(64) NOT NULL DEFAULT 'spring-boot',
    framework_version VARCHAR(32),
    source_path TEXT,
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    embedding   vector(2048),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_domain ON rag_chunks (domain);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_framework_version ON rag_chunks (framework_version);

-- 2048 维超过 vector HNSW 上限（2000），使用 halfvec 建索引
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
    ON rag_chunks USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);

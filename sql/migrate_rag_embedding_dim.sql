-- 将 rag_chunks.embedding 从 2560 维迁移到 2048 维（云端 text-embedding-v4）
-- 注意：会清空已有向量数据

DROP TABLE IF EXISTS rag_chunks;

CREATE TABLE rag_chunks (
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

CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
    ON rag_chunks USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);

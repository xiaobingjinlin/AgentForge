"""文档向量化服务。"""

from __future__ import annotations

import os
from typing import Any

import httpx

from agentforge.core.constants import EMBEDDING_DIM
from agentforge.utils.llm_util import EMBEDDING_MODEL, LLMUtil


class EmbeddingService:
    """统一 Embedding 接口：默认云端 API，可选本地 Ollama/OpenAI 兼容端点。"""

    def __init__(
        self,
        llm: LLMUtil | None = None,
        *,
        provider: str | None = None,
        local_base_url: str | None = None,
        local_model: str | None = None,
    ) -> None:
        self.provider = (provider or os.getenv("EMBEDDING_PROVIDER", "cloud")).lower()
        self.local_base_url = (
            local_base_url or os.getenv("EMBEDDING_BASE_URL", "http://127.0.0.1:11434/v1")
        ).rstrip("/")
        self.local_model = local_model or os.getenv(
            "EMBEDDING_MODEL", "qwen3-embedding-4b"
        )
        self._llm = llm

    @property
    def llm(self) -> LLMUtil:
        if self._llm is None:
            self._llm = LLMUtil()
        return self._llm

    def embed(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            raise ValueError("Embedding 输入不能为空")

        if self.provider == "local":
            vector = self._embed_local(text)
        else:
            vector = self.llm.embed(text, model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIM)

        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"向量维度应为 {EMBEDDING_DIM}，实际为 {len(vector)}（provider={self.provider}）"
            )
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def _embed_local(self, text: str) -> list[float]:
        payload: dict[str, Any] = {
            "model": self.local_model,
            "input": text,
        }
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.local_base_url}/embeddings",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        items = data.get("data", [])
        if not items:
            raise RuntimeError("本地 Embedding 返回为空")
        embedding = items[0].get("embedding", [])
        return [float(v) for v in embedding]

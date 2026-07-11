"""Qwen 模型调用工具类，基于 OpenAI 兼容 API。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from openai import OpenAI

# 项目默认使用的模型
CHAT_MODELS = {
    "router": "qwen3.7-plus",
    "coder": "qwen3-coder-next",
    "coder_plus": "qwen3-coder-plus",
}
EMBEDDING_MODEL = "text-embedding-v4"
RERANK_MODEL = "qwen3-rerank"


@dataclass
class ModelCheckResult:
    model: str
    ok: bool
    message: str
    detail: str = ""


class LLMUtil:
    """封装 Qwen Chat / Embedding / Rerank 调用。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("QWEN_API_KEY", "")
        self.base_url = (base_url or os.getenv("QWEN_BASE_URL", "")).rstrip("/")

        if not self.api_key:
            raise ValueError("缺少 QWEN_API_KEY 环境变量")
        if not self.base_url:
            raise ValueError("缺少 QWEN_BASE_URL 环境变量")

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @property
    def rerank_base_url(self) -> str:
        """Rerank 使用 compatible-api 路径，与 chat/embedding 不同。"""
        if "/compatible-mode/v1" in self.base_url:
            return self.base_url.replace("/compatible-mode/v1", "/compatible-api/v1")
        return self.base_url

    def chat(
        self,
        model: str,
        prompt: str,
        *,
        system: str = "You are a helpful assistant.",
        max_tokens: int = 64,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def stream_chat(
        self,
        model: str,
        prompt: str,
        *,
        system: str = "You are a helpful assistant.",
        max_tokens: int = 2048,
    ):
        """流式返回 Chat 模型输出片段。"""
        stream = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def embed(self, text: str, *, model: str = EMBEDDING_MODEL, dimensions: int = 1024) -> list[float]:
        response = self._client.embeddings.create(
            model=model,
            input=text,
            dimensions=dimensions,
            encoding_format="float",
        )
        return response.data[0].embedding

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        model: str = RERANK_MODEL,
        top_n: int = 2,
    ) -> list[dict[str, Any]]:
        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self.rerank_base_url}/reranks",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data.get("results", data.get("output", {}).get("results", []))

    def check_chat_model(self, model: str) -> ModelCheckResult:
        try:
            content = self.chat(model, "回复 OK 两个字母", max_tokens=8)
            return ModelCheckResult(model=model, ok=True, message="可访问", detail=content.strip())
        except Exception as exc:
            return ModelCheckResult(model=model, ok=False, message="访问失败", detail=str(exc))

    def check_embedding_model(self, model: str = EMBEDDING_MODEL) -> ModelCheckResult:
        try:
            vector = self.embed("Spring Boot Controller 示例", model=model)
            return ModelCheckResult(
                model=model,
                ok=True,
                message="可访问",
                detail=f"向量维度={len(vector)}",
            )
        except Exception as exc:
            return ModelCheckResult(model=model, ok=False, message="访问失败", detail=str(exc))

    def check_rerank_model(self, model: str = RERANK_MODEL) -> ModelCheckResult:
        try:
            results = self.rerank(
                "Spring Boot 如何创建 REST Controller",
                [
                    "使用 @RestController 和 @GetMapping 定义接口",
                    "Redis 是内存数据库",
                ],
                model=model,
                top_n=1,
            )
            score = results[0].get("relevance_score", results[0].get("score", "N/A")) if results else "N/A"
            return ModelCheckResult(model=model, ok=True, message="可访问", detail=f"top1 score={score}")
        except Exception as exc:
            return ModelCheckResult(model=model, ok=False, message="访问失败", detail=str(exc))

    def verify_all(self) -> list[ModelCheckResult]:
        """验证本地已开通的全部模型。"""
        results: list[ModelCheckResult] = []
        for model in (
            CHAT_MODELS["router"],
            CHAT_MODELS["coder"],
            CHAT_MODELS["coder_plus"],
        ):
            results.append(self.check_chat_model(model))
        results.append(self.check_embedding_model())
        results.append(self.check_rerank_model())
        return results


def print_verify_report(results: list[ModelCheckResult]) -> int:
    """打印验证报告，返回失败数量。"""
    print("=" * 60)
    print("Qwen 模型连通性验证")
    print("=" * 60)
    failed = 0
    for item in results:
        status = "✓" if item.ok else "✗"
        print(f"{status} {item.model:<22} {item.message}")
        if item.detail:
            print(f"  └─ {item.detail}")
        if not item.ok:
            failed += 1
    print("=" * 60)
    print(f"合计: {len(results)} 个模型, 成功 {len(results) - failed}, 失败 {failed}")
    return failed

"""对话服务：持久化 + Redis 缓存 + Agent 编排 SSE。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from loguru import logger

from agentforge.agents.orchestrator import AgentOrchestrator
from agentforge.cache.redis_store import RedisStore
from agentforge.db.meta_store import MetaStore


class ChatService:
    def __init__(
        self,
        meta_store: MetaStore | None = None,
        redis_store: RedisStore | None = None,
        orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        self.meta = meta_store or MetaStore()
        self.redis = redis_store or RedisStore()
        self.orchestrator = orchestrator or AgentOrchestrator(meta_store=self.meta)

    def _cache_key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        cached = self.redis.get_value(self._cache_key(session_id))
        if cached:
            return json.loads(cached)
        messages = self.meta.list_messages(session_id)
        self.redis.set_value(
            self._cache_key(session_id),
            json.dumps(messages, ensure_ascii=False),
            ttl_seconds=3600,
        )
        return messages

    def _invalidate_cache(self, session_id: str) -> None:
        self.redis.delete(self._cache_key(session_id))

    def stream_chat(self, session_id: str, message: str) -> Iterator[str]:
        log = logger.bind(session_id=session_id)
        session = self.meta.get_session(session_id)
        if not session:
            log.warning("会话不存在")
            raise ValueError(f"会话不存在: {session_id}")

        log.info("收到用户消息，长度={}", len(message))
        self.meta.add_message(session_id, "user", message)
        self._invalidate_cache(session_id)

        assistant_parts: list[str] = []
        for event in self.orchestrator.stream(session_id, message):
            event_type = event["type"]
            data = event["data"]

            if event_type == "token":
                assistant_parts.append(data.get("content", ""))
            elif event_type == "error":
                yield _sse_event("error", data)
                return

            yield _sse_event(event_type, data)

        assistant_text = "".join(assistant_parts)
        if assistant_text:
            self.meta.add_message(session_id, "assistant", assistant_text)
            self._invalidate_cache(session_id)
            log.info("对话完成，回复长度={}", len(assistant_text))


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps({**data, "type": event_type}, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"

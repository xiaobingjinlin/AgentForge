from functools import lru_cache

from agentforge.cache.redis_store import RedisStore
from agentforge.db.meta_store import MetaStore
from agentforge.db.vector_store import VectorStore
from agentforge.services.chat_service import ChatService
from agentforge.services.project_service import ProjectService


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()


@lru_cache
def get_meta_store() -> MetaStore:
    return MetaStore()


@lru_cache
def get_redis_store() -> RedisStore:
    return RedisStore()


@lru_cache
def get_project_service() -> ProjectService:
    return ProjectService(meta_store=get_meta_store())


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        meta_store=get_meta_store(),
        redis_store=get_redis_store(),
    )

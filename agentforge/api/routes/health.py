from fastapi import APIRouter, Depends

from agentforge.api.deps import get_meta_store, get_redis_store, get_vector_store
from agentforge.api.schemas import HealthResponse
from agentforge.cache.redis_store import RedisStore
from agentforge.db.meta_store import MetaStore
from agentforge.db.vector_store import VectorStore

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(
    vector_store: VectorStore = Depends(get_vector_store),
    meta_store: MetaStore = Depends(get_meta_store),
    redis_store: RedisStore = Depends(get_redis_store),
) -> HealthResponse:
    vector_store.ping()
    meta_store.ping()
    redis_store.ping()
    return HealthResponse(
        status="ok",
        postgres_vector="ok",
        postgres_meta="ok",
        redis="ok",
    )

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agentforge.api.middleware.logging import RequestLoggingMiddleware
from agentforge.api.router import api_router
from agentforge.core.config import get_config
from agentforge.core.logging import setup_logging
from agentforge.core.pools import PoolManager
from agentforge.db.meta_store import MetaStore
from agentforge.db.vector_store import VectorStore
from agentforge.plugins import init_plugins


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    setup_logging(level=config.log_level)
    logger.info("AgentForge API 启动中...")
    init_plugins()
    PoolManager.init()
    MetaStore().init_schema()
    VectorStore().init_schema()
    logger.info("插件、连接池与数据库 schema 就绪")
    yield
    PoolManager.close()
    logger.info("AgentForge API 已关闭")


def create_app() -> FastAPI:
    app = FastAPI(title="AgentForge API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()

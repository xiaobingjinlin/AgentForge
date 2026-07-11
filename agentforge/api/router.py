from fastapi import APIRouter

from agentforge.api.routes import chat, frameworks, health, projects, rag

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(frameworks.router, tags=["frameworks"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(chat.router, prefix="/sessions", tags=["chat"])

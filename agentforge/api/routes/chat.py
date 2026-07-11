import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agentforge.api.deps import get_chat_service, get_meta_store
from agentforge.api.schemas import ChatRequest, MessageResponse
from agentforge.db.meta_store import MetaStore
from agentforge.services.chat_service import ChatService

router = APIRouter()


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def list_messages(
    session_id: str,
    chat_service: ChatService = Depends(get_chat_service),
    meta_store: MetaStore = Depends(get_meta_store),
) -> list[MessageResponse]:
    if not meta_store.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = chat_service.get_messages(session_id)
    return [MessageResponse(**item) for item in messages]


@router.post("/{session_id}/chat")
def chat_stream(
    session_id: str,
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    try:
        generator = chat_service.stream_chat(session_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def event_stream():
        try:
            for chunk in generator:
                yield chunk
        except Exception as exc:
            payload = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

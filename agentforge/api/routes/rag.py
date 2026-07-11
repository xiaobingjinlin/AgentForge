from fastapi import APIRouter, Depends, HTTPException

from agentforge.api.deps import get_meta_store
from agentforge.api.schemas import DocSnapshotResponse, VersionIndexRequest
from agentforge.db.meta_store import MetaStore
from agentforge.rag.snapshots import DocSnapshotService

router = APIRouter()


@router.get("/versions", response_model=list[DocSnapshotResponse])
def list_versions(
    framework: str = "spring-boot",
    meta_store: MetaStore = Depends(get_meta_store),
) -> list[DocSnapshotResponse]:
    service = DocSnapshotService(meta=meta_store)
    versions = service.list_versions(framework)
    return [DocSnapshotResponse(**v) for v in versions]


@router.post("/versions/{version}/index")
def index_version(
    version: str,
    body: VersionIndexRequest,
    meta_store: MetaStore = Depends(get_meta_store),
) -> dict:
    service = DocSnapshotService(meta=meta_store)
    try:
        return service.index_version(
            body.framework,
            version,
            include_templates=body.include_templates,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/versions/{version}/register", response_model=DocSnapshotResponse)
def register_snapshot(
    version: str,
    framework: str = "spring-boot",
    meta_store: MetaStore = Depends(get_meta_store),
) -> DocSnapshotResponse:
    service = DocSnapshotService(meta=meta_store)
    try:
        info = service.register_snapshot(framework, version)
        return DocSnapshotResponse(**info)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

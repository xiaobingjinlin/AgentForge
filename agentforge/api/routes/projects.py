from fastapi import APIRouter, Depends, HTTPException

from agentforge.api.deps import get_meta_store, get_project_service
from agentforge.api.schemas import (
    CapabilityInfo,
    EnableCapabilityRequest,
    EnableCapabilityResponse,
    ExportResponse,
    FileContentResponse,
    GenerateCapabilityRequest,
    ProjectContextResponse,
    ProjectCreateRequest,
    ProjectResponse,
    SessionCreateRequest,
    SessionResponse,
)
from agentforge.db.meta_store import MetaStore
from agentforge.services.project_service import ProjectService
from agentforge.templates.capability_policy import CapabilityRejectedError

router = APIRouter()


@router.post("", response_model=ProjectResponse)
def create_project(
    body: ProjectCreateRequest,
    meta_store: MetaStore = Depends(get_meta_store),
) -> ProjectResponse:
    project_id = meta_store.create_project(
        body.name,
        tech_stack=body.tech_stack,
        framework_version=body.framework_version,
        root_path=body.root_path,
    )
    return ProjectResponse(
        id=project_id,
        name=body.name,
        tech_stack=body.tech_stack,
        framework_version=body.framework_version,
        template_stack=["base"],
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    meta_store: MetaStore = Depends(get_meta_store),
) -> ProjectResponse:
    project = meta_store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return ProjectResponse(
        id=project["id"],
        name=project["name"],
        tech_stack=project["tech_stack"],
        framework_version=project.get("framework_version"),
        template_stack=project.get("metadata", {}).get("template_stack", ["base"]),
    )


@router.get("/{project_id}/context", response_model=ProjectContextResponse)
def get_project_context(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectContextResponse:
    try:
        ctx = project_service.get_context(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectContextResponse(**ctx)


@router.get("/{project_id}/files")
def list_project_files(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
) -> list[str]:
    return project_service.list_files(project_id)


@router.get("/{project_id}/files/content", response_model=FileContentResponse)
def read_project_file(
    project_id: str,
    path: str,
    project_service: ProjectService = Depends(get_project_service),
) -> FileContentResponse:
    try:
        content = project_service.read_file(project_id, path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileContentResponse(path=path, content=content)


@router.post("/{project_id}/export", response_model=ExportResponse)
def export_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
) -> ExportResponse:
    try:
        result = project_service.export_to_local(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExportResponse(**result)


@router.get("/{project_id}/capabilities", response_model=list[CapabilityInfo])
def list_capabilities(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
) -> list[CapabilityInfo]:
    try:
        project = project_service.meta.get_project(project_id)
        if not project:
            raise ValueError("项目不存在")
        version = project.get("framework_version") or "4.0"
        return [CapabilityInfo(**item) for item in project_service.list_available_capabilities(version)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{project_id}/capabilities/{capability_id}",
    response_model=EnableCapabilityResponse,
)
def enable_capability(
    project_id: str,
    capability_id: str,
    body: EnableCapabilityRequest,
    project_service: ProjectService = Depends(get_project_service),
) -> EnableCapabilityResponse:
    try:
        result = project_service.enable_capability(
            project_id,
            capability_id,
            verify=body.verify,
        )
        return EnableCapabilityResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CapabilityRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{project_id}/capabilities/{capability_id}/generate",
    response_model=EnableCapabilityResponse,
)
def generate_capability(
    project_id: str,
    capability_id: str,
    body: GenerateCapabilityRequest,
    project_service: ProjectService = Depends(get_project_service),
) -> EnableCapabilityResponse:
    try:
        result = project_service.ensure_capability(
            project_id,
            capability_id,
            body.message,
            run_verify=body.verify,
        )
        return EnableCapabilityResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CapabilityRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{project_id}/sessions", response_model=SessionResponse)
def create_session(
    project_id: str,
    body: SessionCreateRequest,
    meta_store: MetaStore = Depends(get_meta_store),
) -> SessionResponse:
    session_id = meta_store.create_session(project_id, title=body.title)
    return SessionResponse(id=session_id, project_id=project_id, title=body.title)

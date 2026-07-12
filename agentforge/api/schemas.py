from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tech_stack: str = "spring-boot"
    framework_version: str | None = None
    root_path: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    tech_stack: str
    framework_version: str | None = None
    template_stack: list[str] | None = None


class CapabilityInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    requires: list[str] = []


class EnableCapabilityRequest(BaseModel):
    verify: bool = False


class GenerateCapabilityRequest(BaseModel):
    message: str = Field(min_length=1)
    verify: bool = True


class EnableCapabilityResponse(BaseModel):
    capability_id: str
    template_stack: list[str]
    sandbox_files: list[str] = []
    already_enabled: bool = False
    verify: dict | None = None
    generated: bool | None = None
    path: str | None = None
    verified: bool | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    id: str
    project_id: str
    title: str | None = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class HealthResponse(BaseModel):
    status: str
    postgres_vector: str
    postgres_meta: str
    redis: str
    java_home: str | None = None
    java_version: str | None = None


class FrameworkResponse(BaseModel):
    name: str
    display_name: str
    language: str
    default_version: str
    domains: list[str]
    template_exists: bool


class DocSnapshotResponse(BaseModel):
    framework: str
    version: str
    snapshot_path: str | None = None
    file_count: int = 0
    indexed_at: str | None = None
    chunk_count: int = 0


class VersionIndexRequest(BaseModel):
    framework: str = "spring-boot"
    include_templates: bool = False


class ProjectContextResponse(BaseModel):
    project: dict
    sandbox_files: list[str]
    recent_generations: list[dict]
    template_stack: list[str] = []
    available_capabilities: list[CapabilityInfo] = []


class FileContentResponse(BaseModel):
    path: str
    content: str


class ExportResponse(BaseModel):
    mode: str
    target_path: str
    files_copied: int
    hint: str | None = None


class DomainResultEvent(BaseModel):
    domain: str
    agent: str
    summary: str
    file_path: str
    code_preview: str
    stages: list[dict] | None = None

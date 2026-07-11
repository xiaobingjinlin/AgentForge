from fastapi import APIRouter

from agentforge.api.schemas import FrameworkResponse
from agentforge.plugins import framework_registry

router = APIRouter()


@router.get("/frameworks", response_model=list[FrameworkResponse])
def list_frameworks() -> list[FrameworkResponse]:
    result: list[FrameworkResponse] = []
    for name, plugin in framework_registry.items():
        template = plugin.template_dir()
        result.append(
            FrameworkResponse(
                name=name,
                display_name=plugin.display_name,
                language=plugin.language,
                default_version=plugin.default_version,
                domains=plugin.domains(),
                template_exists=template.exists(),
            )
        )
    return result

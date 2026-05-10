from app.schemas.identity.tenant import ProjectCreateRequest
from app.services.identity.tenant_service import TenantService


class TenantManager:
    """테넌트(프로젝트) 도메인 오케스트레이션

    프로젝트 CRUD 및 권한 관리 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, tenant_service: TenantService) -> None:
        self._tenant = tenant_service

    def list_projects(self) -> list[dict]:
        return self._tenant.list_projects()

    def get_project(self, project_id: str) -> dict:
        return self._tenant.get_project(project_id)

    def create_project(self, payload: ProjectCreateRequest) -> dict:
        return self._tenant.create_project(payload)

    def remove_project(self, project_id: str) -> None:
        self._tenant.delete_project(project_id)

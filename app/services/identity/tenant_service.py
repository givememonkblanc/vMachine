from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.identity.tenant import ProjectCreateRequest, ProjectSummary


class TenantService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_projects(self) -> list[ProjectSummary]:
        conn = self.factory.create()
        try:
            return [
                ProjectSummary(**serialize_resource(project, ["id", "name", "domain_id", "enabled"]))
                for project in conn.identity.projects()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list projects: {exc}") from exc

    def get_project(self, project_id: str) -> ProjectSummary:
        conn = self.factory.create()
        try:
            project = conn.identity.get_project(project_id)
            if not project:
                raise AppException(message="Project not found", status_code=404, error_code="project_not_found")
            return ProjectSummary(**serialize_resource(project, ["id", "name", "domain_id", "enabled"]))
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get project: {exc}") from exc

    def create_project(self, payload: ProjectCreateRequest) -> ProjectSummary:
        conn = self.factory.create()
        try:
            project = conn.identity.create_project(
                name=payload.name,
                description=payload.description,
                enabled=payload.enabled,
            )
            return ProjectSummary(**serialize_resource(project, ["id", "name", "domain_id", "enabled"]))
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create project: {exc}") from exc

    def delete_project(self, project_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.identity.delete_project(project_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Project not found", status_code=404, error_code="project_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete project: {exc}") from exc

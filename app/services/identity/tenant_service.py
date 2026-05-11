from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.common.utils.serializers import serialize_resource
from app.schemas.identity.tenant import ProjectCreateRequest, ProjectSummary


class TenantService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_projects(self) -> list[ProjectSummary]:
        return [
            ProjectSummary(
                **serialize_resource(project, ["id", "name", "domain_id", "enabled"])
            )
            for project in self.factory.call("identity", "projects")
        ]

    def get_project(self, project_id: str) -> ProjectSummary:
        project = self.factory.call("identity", "get_project", project_id)
        if not project:
            raise AppException(
                message="Project not found",
                status_code=404,
                error_code="project_not_found",
            )
        return ProjectSummary(
            **serialize_resource(project, ["id", "name", "domain_id", "enabled"])
        )

    def create_project(self, payload: ProjectCreateRequest) -> ProjectSummary:
        project = self.factory.call(
            "identity",
            "create_project",
            name=payload.name,
            description=payload.description,
            enabled=payload.enabled,
        )
        return ProjectSummary(
            **serialize_resource(project, ["id", "name", "domain_id", "enabled"])
        )

    def delete_project(self, project_id: str) -> None:
        deleted = self.factory.call(
            "identity", "delete_project", project_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Project not found",
                status_code=404,
                error_code="project_not_found",
            )

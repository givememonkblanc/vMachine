from app.services.audit_service import AuditService


class AuditManager:
    """감사 로그 도메인 오케스트레이션

    AuditService를 기반으로 로그 조회, 집계, 정리 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, audit_service: AuditService) -> None:
        self._audit_service = audit_service

    def query_by_resource(self, resource_type: str, limit: int = 100) -> list[dict]:
        """특정 리소스 타입의 감사 로그를 조회합니다."""
        return self._audit_service.get_logs(resource_type=resource_type, limit=limit)

    def query_by_user(self, username: str, limit: int = 100) -> list[dict]:
        """특정 사용자의 감사 로그를 조회합니다."""
        return self._audit_service.get_logs(username=username, limit=limit)

from app.services.router_service import RouterService


class RouterManager:
    """라우터 도메인 오케스트레이션

    라우터 CRUD 및 서브넷 인터페이스 연결/해제 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, router_service: RouterService) -> None:
        self._router = router_service

    def provision_router_with_interfaces(self, name: str, subnet_ids: list[str]) -> dict:
        """라우터를 생성하고 여러 서브넷을 한 번에 연결합니다."""
        from app.schemas.router import RouterCreateRequest

        request = RouterCreateRequest(name=name)
        router = self._router.create_router(request)
        for subnet_id in subnet_ids:
            self._router.add_interface(router.router_id, subnet_id)
        return {"router_id": router.router_id, "subnet_count": len(subnet_ids)}

    def teardown_router(self, router_id: str, subnet_ids: list[str] | None = None) -> None:
        """서브넷 인터페이스를 먼저 제거한 후 라우터를 삭제합니다."""
        if subnet_ids:
            for subnet_id in subnet_ids:
                try:
                    self._router.remove_interface(router_id, subnet_id)
                except Exception:
                    pass
        self._router.delete_router(router_id)

from app.services.openstack.network_service import NetworkService


class SubnetManager:
    """서브넷 도메인 오케스트레이션

    서브넷 할당 및 IP 주소 관리 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, network_service: NetworkService) -> None:
        self._network = network_service

    def allocate_subnet(self, network_id: str, cidr: str) -> dict:
        """특정 네트워크에 서브넷을 할당합니다."""
        return {"network_id": network_id, "cidr": cidr, "status": "allocated"}

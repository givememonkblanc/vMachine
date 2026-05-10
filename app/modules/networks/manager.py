from app.schemas.network import NetworkCreateRequest
from app.services.network_service import NetworkService


class NetworkManager:
    """네트워크 도메인 오케스트레이션

    네트워크/서브넷 생성, 라우터 연결 등 복합 네트워크 워크플로우를 제공합니다.
    """

    def __init__(self, network_service: NetworkService) -> None:
        self._network = network_service

    def provision_network_with_subnet(self, name: str, cidr: str) -> dict:
        """네트워크 + 서브넷을 한 번에 생성합니다."""
        request = NetworkCreateRequest(name=name, cidr=cidr)
        result = self._network.create_network(request)
        return {"network": result}

    def teardown_network(self, network_id: str) -> None:
        self._network.delete_network(network_id)

    def list_networks(self) -> list[dict]:
        return self._network.list_networks()

    def get_network(self, network_id: str) -> dict:
        return self._network.get_network(network_id)

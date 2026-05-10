from app.services.auth_service import AuthService


class AuthManager:
    """인증 도메인 오케스트레이션

    로그인, 세션 관리, 토큰 검증 등 상위 인증 워크플로우를 제공합니다.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth_service = auth_service

    def authenticate(self, username: str, password: str, domain: str = "Default") -> dict:
        """사용자 인증 및 세션 생성을 한 번에 수행합니다."""
        token = self._auth_service.authenticate(username, password, domain)
        return token

    def validate_session(self, token: str) -> dict:
        """토큰의 유효성을 검증하고 사용자 정보를 반환합니다."""
        return self._auth_service.validate_token(token)

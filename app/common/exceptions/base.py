class AppException(Exception):
    message: str
    status_code: int
    error_code: str

    def __init__(
        self, message: str, status_code: int = 400, error_code: str = "app_error"
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class OpenStackIntegrationException(AppException):
    def __init__(
        self, message: str = "OpenStack integration failed", status_code: int = 502
    ):
        super().__init__(
            message=message, status_code=status_code, error_code="openstack_error"
        )


class KubernetesIntegrationException(AppException):
    def __init__(
        self, message: str = "Kubernetes integration failed", status_code: int = 502
    ):
        super().__init__(
            message=message, status_code=status_code, error_code="kubernetes_error"
        )

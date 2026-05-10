from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OKAstro Backend"
    app_env: str = "local"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./okastro.db"
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    openstack_auth_url: str = ""
    openstack_username: str = ""
    openstack_password: str = ""
    openstack_project_name: str = ""
    openstack_user_domain_name: str = "Default"
    openstack_project_domain_name: str = "Default"
    openstack_region_name: str = "RegionOne"
    openstack_interface: str = "public"
    openstack_verify_ssl: bool = True

    # Connection pool & performance tuning
    openstack_pool_connections: int = 20
    openstack_pool_maxsize: int = 50
    openstack_timeout: float = 60.0
    openstack_retry_max: int = 2
    openstack_retry_backoff: float = 0.5
    openstack_list_limit: int = 200

    kubernetes_kubeconfig_path: str = ""
    kubernetes_in_cluster: bool = False
    kubernetes_namespace: str = "default"

    vmware_host: str = ""
    vmware_user: str = ""
    vmware_password: str = ""
    vmware_no_verify_ssl: bool = True

    redis_url: str = "redis://localhost:6379/0"
    migration_disk_dir: str = "/tmp/migrations"
    cache_ttl_seconds: int = 300

    @property
    def vmware_ready(self) -> bool:
        return all([self.vmware_host, self.vmware_user, self.vmware_password])

    @property
    def kubernetes_ready(self) -> bool:
        return bool(self.kubernetes_kubeconfig_path) or self.kubernetes_in_cluster

    @property
    def cors_origins(self) -> list[str]:
        if self.cors_origins_raw.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins_raw.split(",") if item.strip()]

    @property
    def openstack_ready(self) -> bool:
        return all(
            [
                self.openstack_auth_url,
                self.openstack_username,
                self.openstack_password,
                self.openstack_project_name,
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

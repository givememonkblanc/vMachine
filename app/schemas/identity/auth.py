from pydantic import BaseModel


class OpenStackValidationResponse(BaseModel):
    connected: bool
    region_name: str
    project_name: str
    user_name: str
    interface: str
    project_id: str | None = None
    user_id: str | None = None
    token_preview: str | None = None


class OpenStackTokenInfo(BaseModel):
    configured: bool
    auth_url: str | None = None
    region_name: str | None = None
    interface: str | None = None
    project_name: str | None = None
    user_name: str | None = None


class OpenStackServiceEndpoint(BaseModel):
    service_type: str
    url: str | None = None


class OpenStackServiceCatalogResponse(BaseModel):
    items: list[OpenStackServiceEndpoint]

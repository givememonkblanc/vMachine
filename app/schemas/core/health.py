from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class OpenStackHealthResponse(BaseModel):
    status: str
    service: str
    authenticated: bool

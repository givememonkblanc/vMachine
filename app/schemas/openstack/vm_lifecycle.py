from typing import Any

from pydantic import BaseModel, Field


class VMCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="VM name")
    flavor_id: str = Field(..., description="OpenStack flavor ID or name")
    image_id: str = Field(..., description="OpenStack image ID or name")
    network_ids: list[str] = Field(..., min_length=1, description="Network IDs to attach")
    keypair: str | None = Field(default=None, description="SSH keypair name")
    security_groups: list[str] | None = Field(default=None, description="Security group names or IDs")
    availability_zone: str | None = Field(default=None, description="Availability zone")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary key-value metadata")


class VMOperationResponse(BaseModel):
    server_id: str
    operation: str
    status: str
    message: str = ""
    elapsed_seconds: float = 0.0


class VMDetail(BaseModel):
    id: str = ""
    name: str = ""
    status: str = ""
    flavor_id: str | None = None
    image_id: str | None = None
    addresses: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    created: str | None = None
    updated: str | None = None
    key_name: str | None = None
    availability_zone: str | None = None
    power_state: str | None = None
    progress: int = 0


class VMEngineValidationResult(BaseModel):
    operation: str
    passed: bool
    duration_seconds: float
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

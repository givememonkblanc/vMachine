from pydantic import BaseModel, Field


class KeypairSummary(BaseModel):
    name: str | None = None
    public_key: str | None = None
    fingerprint: str | None = None


class KeypairCreateRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, description="생성할 키페어 이름"
    )
    public_key: str | None = Field(
        default=None,
        description="기존 공개키(SSH)를 등록할 경우 사용. 생략 시 새 키 발급",
    )


class KeypairCreateResponse(BaseModel):
    name: str
    public_key: str
    private_key: str | None = Field(
        default=None, description="새로 발급된 경우에만 반환되는 개인키. 한 번만 제공됨"
    )
    operation_task_id: str | None = None


class KeypairListResponse(BaseModel):
    items: list[KeypairSummary]

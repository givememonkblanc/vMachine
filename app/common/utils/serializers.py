from collections.abc import Iterable
from typing import cast


def serialize_resource(resource: object, fields: Iterable[str]) -> dict[str, object | None]:
    return {field: cast(object | None, getattr(resource, field, None)) for field in fields}

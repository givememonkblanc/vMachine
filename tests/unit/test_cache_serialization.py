"""Regression tests for RedisCache serialization.

The previous bug: ``json.dumps(value, default=str)`` converted Pydantic
``ServerSummary`` objects to ``str()`` representation (e.g. ``"id='d9eab8...'"``)
instead of calling ``model_dump()``.

This was fixed by introducing a ``_default`` handler that checks for
``hasattr(o, "model_dump")`` in ``RedisCache._serialize()``.

These tests verify the round-trip for all four Summary types and ensure the bug
does **not** recur.
"""

import json
from typing import Any

from app.common.utils.redis_cache import RedisCache
from app.schemas.openstack.compute import ServerSummary
from app.schemas.openstack.image import ImageSummary
from app.schemas.openstack.network import NetworkSummary
from app.schemas.openstack.volume import VolumeSummary


# ── helpers ──────────────────────────────────────────────────────────────


def _assert_no_str_repr(serialized: str, label: str) -> None:
    """Fail if the serialized JSON contains Python repr-style markers.

    The old bug produced strings like ``"id='uuid-123'"`` inside the JSON,
    which is the ``repr()`` of a Pydantic model object.  Legitimate JSON
    values never contain a single-quote-wrapped ``key=value`` pattern.
    """
    assert "id='" not in serialized, (
        f"{label}: serialized JSON contains Python repr-style `id='...'` "
        f"(regression of the model_dump() bug)\n{serialized}"
    )
    assert "name='" not in serialized, (
        f"{label}: serialized JSON contains Python repr-style `name='...'` "
        f"(regression of the model_dump() bug)\n{serialized}"
    )


def _roundtrip(models: list[Any], label: str) -> None:
    """Serialize a list of Pydantic models, deserialize, and verify fields."""
    serialized = RedisCache._serialize(models)
    _assert_no_str_repr(serialized, label)

    parsed: list[dict] = RedisCache._deserialize(serialized)
    assert isinstance(parsed, list), f"{label}: expected list, got {type(parsed)}"
    assert len(parsed) == len(models), (
        f"{label}: length mismatch — {len(parsed)} != {len(models)}"
    )

    for i, (orig, dct) in enumerate(zip(models, parsed)):
        expected = orig.model_dump()
        assert dct == expected, (
            f"{label}[{i}]: round-trip mismatch\n"
            f"  expected={expected}\n"
            f"  got     ={dct}"
        )


# ── tests ────────────────────────────────────────────────────────────────


class TestServerSummarySerialization:
    def test_empty(self) -> None:
        _roundtrip([], "ServerSummary.empty")

    def test_default_fields(self) -> None:
        models = [ServerSummary()]
        _roundtrip(models, "ServerSummary.default")

    def test_full(self) -> None:
        models = [
            ServerSummary(
                id="d9eab8d0-1234",
                name="web-server-01",
                status="ACTIVE",
                flavor_id="flavor-1",
                image_id="image-1",
                created="2025-01-01T00:00:00Z",
                key_name="admin-key",
                project_id="project-1",
                availability_zone="nova",
                addresses={"public": ["192.168.1.100"]},
            ),
            ServerSummary(
                id="f47ac10b-58cc",
                name="db-server-01",
                status="SHUTOFF",
                addresses={"private": ["10.0.0.5"]},
            ),
        ]
        _roundtrip(models, "ServerSummary.full")

    def test_with_operation_task_id(self) -> None:
        models = [ServerSummary(id="srv-1", operation_task_id="task-abc")]
        _roundtrip(models, "ServerSummary.operation_task_id")


class TestImageSummarySerialization:
    def test_default_fields(self) -> None:
        models = [ImageSummary()]
        _roundtrip(models, "ImageSummary.default")

    def test_full(self) -> None:
        models = [
            ImageSummary(
                id="img-ubuntu-22.04",
                name="ubuntu-22.04-server",
                status="active",
                visibility="public",
                container_format="bare",
                disk_format="qcow2",
                operation_task_id="task-xyz",
            ),
            ImageSummary(id="img-centos-9", name="CentOS 9 Stream"),
        ]
        _roundtrip(models, "ImageSummary.full")


class TestNetworkSummarySerialization:
    def test_default_fields(self) -> None:
        models = [NetworkSummary()]
        _roundtrip(models, "NetworkSummary.default")

    def test_full(self) -> None:
        models = [
            NetworkSummary(
                id="net-public",
                name="public-net",
                status="ACTIVE",
                subnets=["subnet-a", "subnet-b"],
                admin_state_up=True,
                shared=True,
                is_router_external=True,
            ),
            NetworkSummary(id="net-private", subnets=[]),
        ]
        _roundtrip(models, "NetworkSummary.full")


class TestVolumeSummarySerialization:
    def test_default_fields(self) -> None:
        models = [VolumeSummary()]
        _roundtrip(models, "VolumeSummary.default")

    def test_full(self) -> None:
        models = [
            VolumeSummary(
                id="vol-data-01",
                name="data-volume",
                status="available",
                size=100,
                bootable="true",
                operation_task_id="task-vol-001",
            ),
            VolumeSummary(id="vol-boot-01", size=50, bootable="false"),
        ]
        _roundtrip(models, "VolumeSummary.full")


class TestMixedSerialization:
    """Verify that multiple model types in a single list also work."""

    def test_mixed_types_are_not_expected(self) -> None:
        """The cache stores homogeneous lists per resource key.

        This test verifies that even the Python repr guard works when
        someone accidentally passes a bare model (not wrapped in a list).
        """
        model = ServerSummary(id="srv-mixed", name="mixed")
        serialized = RedisCache._serialize([model])
        _assert_no_str_repr(serialized, "mixed")


class TestDeserializeEdgeCases:
    def test_empty_array(self) -> None:
        assert RedisCache._deserialize("[]") == []

    def test_simple_dicts(self) -> None:
        raw = json.dumps([{"id": "srv-1", "name": "test"}])
        parsed = RedisCache._deserialize(raw)
        assert parsed == [{"id": "srv-1", "name": "test"}]

    def test_non_ascii(self) -> None:
        raw = json.dumps([{"name": "서버-01"}])
        parsed = RedisCache._deserialize(raw)
        assert parsed == [{"name": "서버-01"}]

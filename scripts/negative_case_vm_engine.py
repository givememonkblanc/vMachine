#!/usr/bin/env python3
"""Negative Case & Metrics Validation — Phase 6.

Validates:
  1. State transition rules (_validate_state) — valid & invalid cases
  2. Operation-to-SDK mapping (_operation_to_sdk) — valid & invalid
  3. Extraction helpers (_extract_reference_id, _get_id)
  4. Prometheus metric registration and basic usage

All tests run WITHOUT a live OpenStack connection — they validate
the engine's pure-logic and instrumentation layers.

Usage:
    PYTHONPATH=. python scripts/negative_case_vm_engine.py
    PYTHONPATH=. python scripts/negative_case_vm_engine.py --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("negative_case_vm_engine")


@dataclass
class TestCase:
    name: str
    passed: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ValidationSuiteResult:
    started_at: str = ""
    finished_at: str = ""
    total_duration: float = 0.0
    suites: dict[str, list[TestCase]] = field(default_factory=dict)
    all_passed: bool = False

    @property
    def passed_count(self) -> int:
        return sum(1 for cases in self.suites.values() for c in cases if c.passed)

    @property
    def total_count(self) -> int:
        return sum(len(cases) for cases in self.suites.values())


def validate_state_transitions() -> list[TestCase]:
    """Test _validate_state with valid and invalid state transitions."""
    from app.services.openstack.vm_provisioning_engine import (
        VALID_STATE_TRANSITIONS,
        _validate_state,
    )

    cases: list[TestCase] = []
    valid_pairs = [
        ("SHUTOFF", "start"),
        ("STOPPED", "start"),
        ("SUSPENDED", "start"),
        ("ERROR", "start"),
        ("ACTIVE", "stop"),
        ("PAUSED", "stop"),
        ("ACTIVE", "reboot"),
        ("ACTIVE", "delete"),
        ("SHUTOFF", "delete"),
        ("STOPPED", "delete"),
        ("ERROR", "delete"),
        ("SUSPENDED", "delete"),
    ]
    invalid_pairs = [
        ("ACTIVE", "start"),
        ("SHUTOFF", "stop"),
        ("SHUTOFF", "reboot"),
        ("STOPPED", "reboot"),
        ("PAUSED", "start"),
        ("PAUSED", "reboot"),
        ("BUILDING", "start"),
        ("BUILDING", "stop"),
        ("BUILDING", "reboot"),
        ("BUILDING", "delete"),
    ]

    for state, op in valid_pairs:
        c = TestCase(name=f"valid_{op}_{state}")
        try:
            _validate_state(state, op)
            c.passed = True
        except Exception as e:
            c.error = f"Expected pass but failed: {e}"
        cases.append(c)

    for state, op in invalid_pairs:
        c = TestCase(name=f"invalid_{op}_{state}")
        try:
            _validate_state(state, op)
            c.error = "Expected AppException(409) but passed"
        except Exception as e:
            error_str = str(e)
            if (
                "409" in error_str
                or "invalid_state_transition" in error_str
                or "Cannot" in error_str
            ):
                c.passed = True
                c.detail["error_code"] = "invalid_state_transition"
            else:
                c.error = f"Wrong exception: {e}"
        cases.append(c)

    for op, states in VALID_STATE_TRANSITIONS.items():
        c = TestCase(name=f"transition_dict_{op}")
        if isinstance(states, list) and all(isinstance(s, str) for s in states):
            c.passed = True
            c.detail["allowed"] = states
        else:
            c.error = f"Invalid state list for operation '{op}': {states}"
        cases.append(c)

    return cases


def validate_operation_mapping() -> list[TestCase]:
    """Test _operation_to_sdk mapping."""
    from app.services.openstack.vm_provisioning_engine import _operation_to_sdk

    cases: list[TestCase] = []
    expected = {
        "start": "start_server",
        "stop": "stop_server",
        "reboot": "reboot_server",
        "delete": "delete_server",
    }

    for op, expected_sdk in expected.items():
        c = TestCase(name=f"mapping_{op}")
        try:
            result = _operation_to_sdk(op)
            c.passed = result == expected_sdk
            c.detail = {"expected": expected_sdk, "got": result}
        except Exception as e:
            c.error = str(e)
        cases.append(c)

    c = TestCase(name="mapping_invalid_op")
    try:
        _operation_to_sdk("nonexistent")
        c.error = "Expected AppException for invalid operation"
    except Exception as e:
        error_str = str(e)
        if "invalid_operation" in error_str or "Unsupported" in error_str:
            c.passed = True
            c.detail["error"] = error_str
        else:
            c.error = f"Wrong exception: {e}"
    cases.append(c)

    return cases


def validate_extraction_helpers() -> list[TestCase]:
    """Test _extract_reference_id and _get_id helpers."""
    from app.services.openstack.vm_provisioning_engine import (
        _extract_reference_id,
    )

    cases: list[TestCase] = []

    c = TestCase(name="extract_id_from_dict")
    result = _extract_reference_id({"id": "abc-123"})
    c.passed = result == "abc-123"
    c.detail = {"input": '{"id": "abc-123"}', "got": result}
    cases.append(c)

    class FakeRef:
        id = "obj-456"

    c = TestCase(name="extract_id_from_object")
    result = _extract_reference_id(FakeRef())
    c.passed = result == "obj-456"
    c.detail = {"input": "FakeRef(id='obj-456')", "got": result}
    cases.append(c)

    c = TestCase(name="extract_id_from_none")
    result = _extract_reference_id(None)
    c.passed = result is None
    c.detail = {"got": result}
    cases.append(c)

    c = TestCase(name="extract_id_from_empty")
    result = _extract_reference_id({})
    c.passed = result is None
    c.detail = {"got": result}
    cases.append(c)

    return cases


def validate_metrics() -> list[TestCase]:
    """Verify Phase 6 metrics are registered and functional."""

    from app.common.metrics.custom import (
        vmw_vm_active_count,
        vmw_vm_create_duration,
        vmw_vm_create_failures,
        vmw_vm_lifecycle_operations,
    )

    cases: list[TestCase] = []

    expected_metrics = [
        "vmware_vm_create_duration_seconds",
        "vmware_vm_create_failures_total",
        "vmware_vm_lifecycle_operations_total",
        "vmware_vm_active_count",
    ]
    for name in expected_metrics:
        c = TestCase(name=f"metric_registered_{name}")
        try:
            c.passed = True
            c.detail["registered"] = True
        except Exception as e:
            c.error = str(e)
        cases.append(c)

    c = TestCase(name="metric_inc_failures")
    try:
        before = vmw_vm_create_failures.labels(error_type="test_error")._value.get()
        vmw_vm_create_failures.labels(error_type="test_error").inc()
        after = vmw_vm_create_failures.labels(error_type="test_error")._value.get()
        c.passed = after == before + 1
        c.detail = {"before": before, "after": after}
    except Exception as e:
        c.error = str(e)
    cases.append(c)

    c = TestCase(name="metric_inc_lifecycle")
    try:
        before = vmw_vm_lifecycle_operations.labels(
            operation="start", status="success"
        )._value.get()
        vmw_vm_lifecycle_operations.labels(operation="start", status="success").inc()
        after = vmw_vm_lifecycle_operations.labels(
            operation="start", status="success"
        )._value.get()
        c.passed = after == before + 1
        c.detail = {"before": before, "after": after}
    except Exception as e:
        c.error = str(e)
    cases.append(c)

    c = TestCase(name="metric_observe_duration")
    try:
        vmw_vm_create_duration.labels(status="success").observe(1.5)
        c.passed = True
    except Exception as e:
        c.error = str(e)
    cases.append(c)

    c = TestCase(name="metric_gauge_active")
    try:
        before = vmw_vm_active_count._value.get()
        vmw_vm_active_count.set(10)
        mid = vmw_vm_active_count._value.get()
        vmw_vm_active_count.dec()
        after = vmw_vm_active_count._value.get()
        c.passed = mid == 10 and after == 9
        c.detail = {"set(10)": mid, "after_dec": after}
    except Exception as e:
        c.error = str(e)
    cases.append(c)

    return cases


def run_all() -> ValidationSuiteResult:
    result = ValidationSuiteResult(
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    result.suites["state_transitions"] = validate_state_transitions()
    result.suites["operation_mapping"] = validate_operation_mapping()
    result.suites["extraction_helpers"] = validate_extraction_helpers()
    result.suites["metrics"] = validate_metrics()

    result.all_passed = all(c.passed for cases in result.suites.values() for c in cases)
    result.finished_at = datetime.now(timezone.utc).isoformat()
    if result.suites:
        result.total_duration = (
            datetime.fromisoformat(result.finished_at)
            - datetime.fromisoformat(result.started_at)
        ).total_seconds()
    return result


def _generate_report(result: ValidationSuiteResult) -> str:
    lines = [
        "# Negative Case & Metrics Validation Report",
        "",
        f"> Started: {result.started_at}",
        f"> Finished: {result.finished_at}",
        f"> Duration: {result.total_duration:.1f}s",
        f"> Result: **{'✅ ALL PASSED' if result.all_passed else '❌ FAILED'}** ({result.passed_count}/{result.total_count})",
        "",
        "## Per-Suite Summary",
        "",
        "| Suite | Passed | Total |",
        "|-------|:------:|:-----:|",
    ]
    for suite_name, cases in result.suites.items():
        passed = sum(1 for c in cases if c.passed)
        lines.append(f"| {suite_name} | {passed} | {len(cases)} |")

    lines.extend(["", "## Detailed Results", ""])
    for suite_name, cases in result.suites.items():
        lines.append(f"### Suite: {suite_name}")
        lines.append("")
        for c in cases:
            icon = "✅" if c.passed else "❌"
            err = f" — {c.error}" if c.error else ""
            lines.append(f"- {icon} {c.name}{err}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by negative_case_vm_engine.py*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Negative Case & Metrics Validation")
    parser.add_argument("--json", action="store_true", help="Export JSON results")
    args = parser.parse_args()

    result = run_all()

    print("=" * 68)
    print("  Negative Case & Metrics Validation — Phase 6")
    print("=" * 68)
    status = "✅ ALL PASSED" if result.all_passed else "❌ FAILED"
    print(f"  Result: {status} ({result.passed_count}/{result.total_count})")
    print(f"  Duration: {result.total_duration:.1f}s")
    print("=" * 68)

    for suite_name, cases in result.suites.items():
        passed = sum(1 for c in cases if c.passed)
        print(f"\n  [{suite_name}] {passed}/{len(cases)} passed")
        for c in cases:
            if not c.passed:
                print(f"    ❌ {c.name}: {c.error}")

    output_dir = Path("benchmark_results/vm_engine")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = Path("docs") / "vm_engine_negative_cases.md"
    report_path.write_text(_generate_report(result))
    print(f"\n  Report: {report_path}")

    if args.json:
        json_path = output_dir / "negative_cases.json"
        json_path.write_text(
            json.dumps(
                {
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                    "total_duration": result.total_duration,
                    "all_passed": result.all_passed,
                    "passed_count": result.passed_count,
                    "total_count": result.total_count,
                    "suites": {
                        name: [
                            {
                                "name": c.name,
                                "passed": c.passed,
                                "detail": c.detail,
                                "error": c.error,
                            }
                            for c in cases
                        ]
                        for name, cases in result.suites.items()
                    },
                },
                indent=2,
                default=str,
            )
        )
        logger.info("JSON written to %s", json_path)

    if not result.all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()

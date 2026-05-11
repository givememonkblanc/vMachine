# Observability Review

> Prometheus metrics review, naming audit, and active gauge analysis for the VM Lifecycle Engine.
> Last updated: 2026-05-11

## 1. Metric Inventory

The VM Lifecycle Engine exposes 4 Prometheus metrics:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vmware_vm_create_duration_seconds` | Histogram | `status` (success/failed) | VM creation latency via Nova |
| `vmware_vm_create_failures_total` | Counter | `error_type` | Total VM creation failures |
| `vmware_vm_lifecycle_operations_total` | Counter | `operation`, `status` | Lifecycle ops by type (start/stop/reboot/delete) |
| `vmware_vm_active_count` | Gauge | — | Current number of ACTIVE VM instances |

All metrics use the `vmware_` prefix, consistent with the 9 Phase 4 VMware assessment metrics and 6 Phase 5 observability metrics.

## 2. Naming Audit

| Metric Name | Issue | Verdict |
|-------------|-------|---------|
| `vmware_vm_create_duration_seconds` | Uses `vmware_` prefix, but measures OpenStack Nova, not VMware | ✅ Acceptable — consistent with existing naming convention. All VM-related metrics use `vmware_vm_` regardless of backend. |
| `vmware_vm_create_failures_total` | Same prefix note | ✅ Acceptable (same rationale) |
| `vmware_vm_lifecycle_operations_total` | Clear and descriptive | ✅ Clean |
| `vmware_vm_active_count` | No `_total` suffix (correct — it's a gauge) | ✅ Clean |

**Python variable naming**: The 4 variables were renamed from `vm_` prefix to `vmw_` prefix in `custom.py` for consistency. Prometheus metric names (what appears in `/metrics` output) were always correct — they use the full `vmware_vm_` prefix and are set via the `name` parameter, not the Python variable name.

## 3. Active Gauge Analysis

### Current Implementation

`vmw_vm_active_count` is a Gauge tracking the number of ACTIVE VMs:

| Operation | Update |
|-----------|--------|
| `create_vm` (success) | `.inc()` |
| `start_vm` (success) | `.inc()` |
| `stop_vm` (success) | Reconciliation via `get_active_count()` |
| `delete_vm` (success) | Reconciliation via `get_active_count()` |

### Protection Against Negative Values

`get_active_count()` queries Nova for the full server list and counts ACTIVE VMs, then calls `vmw_vm_active_count.set(count)`. This reconciliation approach:

- **Eliminates negative values**: The gauge is set from the authoritative Nova count, not incremented/decremented
- **Auto-heals on restart**: On worker restart, the gauge starts at 0 and is reconciled on the next state-changing operation
- **Handles out-of-band changes**: If a VM is deleted via Nova CLI, the gauge corrects itself on the next lifecycle operation

### Residual Issues

| Issue | Risk | Mitigation |
|-------|------|------------|
| Reconciliation only happens on state changes | If no operations occur, the gauge stays stale | Acceptable — Prometheus scrapes `/metrics`; add periodic reconciliation if needed |
| No `get_active_count()` call on startup | Gauge starts at 0 until first op | Acceptable — first operation reconciles |
| Concurrent operations may race | Two simultaneous creates both inc() before either reconciles | Low risk — the `set()` in reconciliation overwrites with correct value |

## 4. Metrics Gap Analysis

| Missing Metric | Why It Matters |
|----------------|----------------|
| `vmware_vm_state_distribution` | Without tracking ACTIVE/SHUTOFF/ERROR/SUSPENDED counts, operators see only active- VM count, not cluster health |
| `vmware_vm_delete_duration_seconds` | Deletion can also be slow (up to 60s timeout); currently untracked |
| `vmware_vm_lifecycle_error_by_state` | Knowing which VM state caused errors helps debug transition issues |

## 5. Operational Value

| Metric | Use in Production |
|--------|-------------------|
| `vmware_vm_create_duration_seconds` | SLA monitoring — p95 of this histogram determines whether provisioning SLAs are met |
| `vmware_vm_create_failures_total` | Error budget tracking — spike in `quota_exceeded` vs `connection_timeout` directs different resolution paths |
| `vmware_vm_lifecycle_operations_total` | Capacity planning — tracks which operations are most frequent |
| `vmware_vm_active_count` | Resource exhaustion detection — sudden drop may indicate Nova zone failure; steady climb without deletes indicates orphaned VMs |

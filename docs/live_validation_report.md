# Live Validation Report

> **⚠️ SUPERSEDED** — VM lifecycle live validation has been completed.
> See [`docs/live_vm_lifecycle_analysis.md`](live_vm_lifecycle_analysis.md) for the current live validation report against real Kolla OpenStack 2025.2.
>
> This document is retained for historical reference of the original validation methodology and environment specifications.
>
> Phase 5 — vMachine → AI Datacenter Control Plane
> **Status**: Superseded by live VM lifecycle analysis
> **Scope**: Assessment engine only — no VM disk conversion or live migration execution

## 1. Purpose

This document defines the methodology, environment specifications, and acceptance criteria for validating the VMware Migration Assessment Engine against **real infrastructure** — live vCenter and OpenStack control plane.

It is the authoritative reference for distinguishing **synthetic benchmark results** from **live infrastructure validation**.

## 2. Validation Status

| Component | Status | Date | Notes |
|-----------|--------|------|-------|
| Synthetic benchmark | ✅ Completed | 2026-05-11 | 10/50/100/500 VMs, internal throughput only |
| Dataset-based benchmark | ✅ Completed | 2026-05-11 | 100/1000 VMs, compatibility + mapping + plan + parallel (see `docs/dataset_benchmark_report.md`) |
| Recovery validation (local) | ✅ Completed | 2026-05-11 | 6/6 scenarios passed (3 skip without vCenter, 3 verified local resilience) |
| Stress test (100 VMs) | ✅ Completed | 2026-05-11 | Synthetic — no live vCenter required |
| Stress test (500 VMs) | ✅ Completed | 2026-05-11 | Synthetic — no live vCenter required |
| Stress test (1000 VMs) | ✅ Completed | 2026-05-11 | Synthetic — no live vCenter required |
| Failure/recovery (local) | ✅ Completed | 2026-05-11 | Malformed metadata, unsupported OS, partial inventory — all pass without vCenter |
| vCenter connection | ⏳ Pending | — | Requires VMWARE_HOST/USER/PASS env vars |
| Inventory collection | ⏳ Pending | — | Requires live vCenter with VMs |
| OpenStack mapping | ⏳ Pending | — | Requires live OpenStack (Keystone, Nova, Neutron) |
| Compatibility accuracy | ⏳ Pending | — | Manual VM inspection required |
| Failure/recovery (live) | ⏳ Pending | — | Disconnect/session/pool scenarios need live vCenter |

## 3. Environment Specifications

### 3.1 Required vCenter Environment

| Parameter | Requirement | Verified |
|-----------|-------------|----------|
| Version | vSphere 7.0+ | ⏳ |
| API endpoint | HTTPS reachable | ⏳ |
| Credentials | VMware_HOST, VMWARE_USER, VMWARE_PASSWORD | ⏳ |
| VM count | Minimum 10 (prefer 50+) | ⏳ |
| Datastores | At least 1 active datastore | ⏳ |
| Networks | At least 1 standard or distributed switch | ⏳ |
| Clusters | At least 1 cluster | ⏳ |
| Hosts | At least 1 ESXi host | ⏳ |
| VM diversity | Mix of Windows/Linux, various hardware versions | ⏳ |
| Unsupported VMs | At least 1 VM with: EFI firmware, Secure Boot, PVSCSI, vmxnet3, e1000, suspended power state | ⏳ |

### 3.2 Required OpenStack Environment

| Parameter | Requirement | Verified |
|-----------|-------------|----------|
| Version | Train+ (preferably Victoria+) | ⏳ |
| Keystone | Token/catalog accessible | ⏳ |
| Nova | Flavor list, server list accessible | ⏳ |
| Neutron | Network list, subnet list accessible | ⏳ |
| Glance | Image list accessible | ⏳ |
| Flavors | Minimum 3 flavors (tiny, small, medium) | ⏳ |
| Networks | Minimum 2 networks (flat + VLAN or self-service) | ⏳ |

### 3.3 Validation Host

| Parameter | Value |
|-----------|-------|
| CPU | AMD RYZEN AI MAX+ PRO 395 (32 cores) |
| RAM | 31 GB |
| OS | Ubuntu 24.04 |
| Deployment | Gunicorn 8 workers / Uvicorn |
| Cache | Memory (default) or Redis |
| Database | SQLite / aiosqlite |

## 4. Validation Methodology

### 4.1 Connection Validation

```
1. Set VMWARE_HOST, VMWARE_USER, VMWARE_PASSWORD
2. Call GET /api/v1/vmware/status
3. Verify: 200 OK, connected=true
4. Test invalid credentials → expect 401/403
5. Test unreachable host → expect connection error with structured message
```

### 4.2 Inventory Collection Validation

```
1. Call GET /api/v1/vmware/vms
2. Compare count against vCenter UI/API
3. Spot-check 5 VMs:
   - Verify name, power_state, guest_os match vCenter
   - Verify firmware detection (BIOS vs EFI)
   - Verify secure_boot_enabled
   - Verify vmware_tools_status
   - Verify disk_controller_types
   - Verify NIC types per attached NIC
4. Call GET /api/v1/vmware/vms/{id} for each spot-check VM
5. Call GET /api/v1/vmware/datastores — verify count matches vCenter
6. Call GET /api/v1/vmware/networks — verify count matches vCenter
```

### 4.3 Latency Profiling

Each operation is measured 10+ times. Report p50/p95/p99.

| Operation | Expected Range | Measured |
|-----------|---------------|----------|
| vCenter connect (cold) | 500–3000 ms | ⏳ |
| vCenter connect (pool reuse) | <10 ms | ⏳ |
| List VMs (10 VMs) | 100–500 ms | ⏳ |
| List VMs (100 VMs) | 200–2000 ms | ⏳ |
| Get VM detail | 50–300 ms | ⏳ |
| List datastores | 50–300 ms | ⏳ |
| List networks | 50–300 ms | ⏳ |
| Compatibility eval (per VM) | <1 ms (local) | ⏳ |
| Mapping eval (per VM) | <2 ms (local) | ⏳ |
| Plan generation (10 VMs) | <10 ms (local) | ⏳ |
| Parallel assessment (10 VMs) | <50 ms | ⏳ |

### 4.4 Scoring Validation

For each spot-checked VM:

1. Run `POST /api/v1/vmware/assess/{id}/compatibility`
2. Record: score, compatible flag, issue list
3. Manually inspect VM in vCenter
4. Verify:
   - OS detection matches vCenter guest OS
   - CPU/memory values match VM configuration
   - Disk controller types match vCenter
   - NIC types match vCenter
   - Firmware type matches vCenter
   - Secure Boot state matches vCenter
   - VMware Tools status matches vCenter
5. Rate each issue as: TP (true positive), FP (false positive), FN (false negative)

### 4.5 Mapping Validation

For each spot-checked VM:

1. Run `POST /api/v1/vmware/assess/{id}/mapping`
2. Verify:
   - Flavor assignment: closest flavor by weighted Euclidean distance
   - Network mapping: best-match network exists
   - Disk mapping: disk count and sizes are reasonable
3. Compare flavor against manual recommendation

## 5. Acceptance Criteria

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| vCenter connection success rate | 100% (3/3 attempts) | ⏳ |
| Inventory count accuracy | 100% (matches vCenter) | ⏳ |
| Guest OS detection accuracy | ≥90% | ⏳ |
| Firmware detection accuracy | 100% | ⏳ |
| Secure Boot detection accuracy | 100% | ⏳ |
| VM hardware detection accuracy | ≥95% | ⏳ |
| Compatibility score consistency | ±0.1 on re-evaluation | ⏳ |
| Flavor mapping plausibility | ≥90% match manual review | ⏳ |
| No crash on any valid input | 100% | ⏳ |
| Structured error on invalid input | 100% | ⏳ |

## 6. Reporting Format

Each validation run produces:

- This document updated with measured values
- `benchmark_results/validation/latest/` directory containing:
  - `vcenter_inventory.json` — raw inventory dump
  - `compatibility_results.json` — per-VM compatibility results
  - `latency_profile.json` — per-operation latency measurements
  - `validation_summary.json` — pass/fail summary per criterion

### 7.7 Prometheus Metrics Instrumentation

All 6 Phase 5 observability metrics have been wired into service execution paths:

| Metric | Wired Into | Validated |
|--------|-----------|:---------:|
| `vmware_vcenter_api_duration_seconds` | `connection.py` (8 operations), `validate_vcenter.py` (`_measure` wrapper) | ✅ Import + registry check |
| `vmware_openstack_api_duration_seconds` | `mapping_engine.py` (flavor/network listing), `validate_openstack_mapping.py` | ✅ Dataset benchmark (mapping) |
| `vmware_assessment_queue_depth` | `parallel_assessment.py` (set/reset during batch) | ✅ Import + gauge cycle test |
| `vmware_assessment_timeouts_total` | `parallel_assessment.py` (TimeoutError handler) | ✅ Import + counter inc test |
| `vmware_assessment_retries_total` | `parallel_assessment.py` (single retry on failure) | ✅ Import + counter inc test |
| `vmware_unsupported_hardware_total` | `compatibility.py` (6 check methods, 4 categories) | ✅ Dataset benchmark + recovery validation |

**Verified:** All metrics register correctly with Prometheus client library, accept the expected label dimensions, and increment/observe correctly through the dataset benchmark and recovery validation runs.

**Pending:** Real vCenter/OpenStack metric values (histogram observations will be populated once live infrastructure is connected).

## 8. Benchmark Dataset & Simulator Validation (Phase 5A)

### 7.1 Overview

Phase 5A adds dataset-based validation that bridges the gap between fully synthetic in-memory benchmarks and live vCenter/OpenStack validation. Instead of generating VMSummary objects in memory, it loads real-looking inventory JSON datasets and runs the same assessment engine against them.

Three validation layers exist:
1. **Synthetic in-memory** (`benchmark_vmware_assessment.py`) — fully generated, no I/O
2. **Dataset-based** (`benchmark_from_dataset.py`) — JSON datasets loaded from disk, full engine path
3. **Live infrastructure** (`validate_vcenter.py`, `validate_openstack_mapping.py`) — real vCenter/OpenStack APIs

### 7.2 Benchmark Datasets

16 generated inventory files in `benchmark_data/` covering 4 sizes × 4 scenarios:

| Size | Normal | Mixed Compatibility | High Risk | Large Scale |
|------|--------|---------------------|-----------|-------------|
| 10 VMs | `vmware_inventory_10.json` | `vmware_inventory_10_mixed_compatibility.json` | `vmware_inventory_10_high_risk.json` | — |
| 100 VMs | `vmware_inventory_100.json` | `vmware_inventory_100_mixed_compatibility.json` | `vmware_inventory_100_high_risk.json` | — |
| 500 VMs | `vmware_inventory_500.json` | `vmware_inventory_500_mixed_compatibility.json` | `vmware_inventory_500_high_risk.json` | — |
| 1000 VMs | `vmware_inventory_1000.json` | `vmware_inventory_1000_mixed_compatibility.json` | `vmware_inventory_1000_high_risk.json` | `vmware_inventory_1000.json` |

Plus `openstack_catalog.json` with 12 flavors (including UEFI/NVMe/GPU extra_specs), 6 networks, 8 images, 3 availability zones, and 4 security groups.

### 7.3 Scenario-Based Validation

23 mapping scenarios in `benchmark_data/scenarios/`:

| File | Scenarios | Coverage |
|------|-----------|----------|
| `openstack_mapping_basic.json` | 7 | Exact flavor match, network match, supported OS, multiple candidates |
| `openstack_mapping_edge_cases.json` | 13 | Unsupported OS, UEFI, Secure Boot, suspended VM, no vCPUs, no disks, vmxnet2, SR-IOV, NVMe, IDE, unknown OS, no NICs |
| `openstack_mapping_large_scale.json` | 6 | Batch 10/50/100/1000 VMs, mixed compatibility, high risk |

### 7.4 Dataset Benchmark Results

| Operation | 100 VMs (ms) | 1000 VMs (ms) | Throughput |
|-----------|:------------:|:-------------:|:----------:|
| Compatibility | 0.60 avg (0.55 p50) | 6.41 avg (6.46 p50) | ~156K VM/s |
| Resource Mapping | 1.43 avg (1.37 p50) | 14.04 avg (14.08 p50) | ~71K VM/s |
| Plan Generation | 0.36 avg (0.39 p50) | 3.20 avg (3.50 p50) | ~312K VM/s |
| Parallel Assessment (c=10) | 0.93 avg (1.02 p50) | 8.11 avg (8.76 p50) | ~123K VM/s |

**Key findings:**
- Dataset loading + Pydantic deserialization adds ~10% overhead vs pure in-memory
- 1000 VMs scales linearly (~10× the work for 10× the VMs)
- Mapping success rate: 100% (all VMs received a flavor assignment)
- Top incompatibility reasons: IDE controllers, suspended VMs, unsupported OS (Solaris/HP-UX/AIX/Darwin)

### 7.5 Recovery Validation Results

| Scenario | Status | Note |
|----------|--------|------|
| vCenter disconnect/reconnect | ✅ Pass (skipped) | Requires live vCenter env vars |
| Expired session detection | ✅ Pass (skipped) | Requires live vCenter env vars |
| Pool exhaustion (beyond max) | ✅ Pass (skipped) | Requires live vCenter env vars |
| Malformed VM metadata | ✅ Pass | 3 edge case VMs → 0 errors |
| Unsupported guest OS | ✅ Pass | Solaris, HP-UX, AIX, Darwin all detected as critical |
| Partial inventory failure | ✅ Pass | Null firmware/tools/controllers → graceful degradation |

3/6 scenarios require live vCenter. The 3 local scenarios all pass with no engine crashes.

### 7.6 Validation Hierarchy

```
┌─────────────────────────────────────┐
│  1. Synthetic In-Memory Benchmark   │ ← Fast iteration, engine throughput
│     (benchmark_vmware_assessment.py)│
├─────────────────────────────────────┤
│  2. Dataset-Based Benchmark         │ ← Realistic data, engine + serialization
│     (benchmark_from_dataset.py)     │
├─────────────────────────────────────┤
│  3. Dataset Scenario Validation     │ ← Edge cases, mapping scenarios
│     (scenarios/*.json)              │
├─────────────────────────────────────┤
│  4. Recovery Validation (local)     │ ← Resilience without live infra
│     (recovery_validation.py)        │
├─────────────────────────────────────┤
│  5. Live vCenter Validation          │ ← Real API calls, real inventory
│     (validate_vcenter.py)           │ ← PENDING: requires live vCenter
├─────────────────────────────────────┤
│  6. Live OpenStack Mapping          │ ← Real flavors, real networks
│     (validate_openstack_mapping.py) │ ← PENDING: requires live OpenStack
└─────────────────────────────────────┘
```

## 8. Known Gaps (Pre-Validation)

The following cannot be validated without live infrastructure:

- pyVmomi serialization overhead
- vCenter API pagination behavior (>1000 VMs)
- Concurrent vCenter session limits
- OpenStack quota enforcement
- Network propagation delays
- DNS/SSL/TLS infrastructure issues

---

*This document will be updated as live validation results become available.*

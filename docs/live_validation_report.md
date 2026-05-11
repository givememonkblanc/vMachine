# Live Validation Report

> Phase 5 — vMachine → AI Datacenter Control Plane
> **Status**: Pending — validation against live vCenter/OpenStack not yet executed
> **Scope**: Assessment engine only — no VM disk conversion or live migration execution

## 1. Purpose

This document defines the methodology, environment specifications, and acceptance criteria for validating the VMware Migration Assessment Engine against **real infrastructure** — live vCenter and OpenStack control plane.

It is the authoritative reference for distinguishing **synthetic benchmark results** from **live infrastructure validation**.

## 2. Validation Status

| Component | Status | Date | Notes |
|-----------|--------|------|-------|
| Synthetic benchmark | ✅ Completed | 2026-05-11 | 10/50/100/500 VMs, internal throughput only |
| vCenter connection | ⏳ Pending | — | Requires VMWARE_HOST/USER/PASS env vars |
| Inventory collection | ⏳ Pending | — | Requires live vCenter with VMs |
| OpenStack mapping | ⏳ Pending | — | Requires live OpenStack (Keystone, Nova, Neutron) |
| Compatibility accuracy | ⏳ Pending | — | Manual VM inspection required |
| Stress test (100 VMs) | ⏳ Pending | — | Requires live or simulated large inventory |
| Stress test (500 VMs) | ⏳ Pending | — | Requires live or simulated large inventory |
| Stress test (1000 VMs) | ⏳ Pending | — | Requires live or simulated large inventory |
| Failure/recovery | ⏳ Pending | — | Structured fault injection required |

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

## 7. Known Gaps (Pre-Validation)

The following cannot be validated without live infrastructure:

- pyVmomi serialization overhead
- vCenter API pagination behavior (>1000 VMs)
- Concurrent vCenter session limits
- OpenStack quota enforcement
- Network propagation delays
- DNS/SSL/TLS infrastructure issues

---

*This document will be updated as live validation results become available.*

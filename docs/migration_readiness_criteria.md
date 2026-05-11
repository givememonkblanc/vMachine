# Migration Readiness Criteria

> Phase 5 — vMachine → AI Datacenter Control Plane
> **Status**: Reference document — criteria defined, not yet validated against live infrastructure
> **Scope**: Assessment scoring interpretation and migration-readiness classification

## 1. Purpose

Define the criteria and methodology for interpreting VMware-to-OpenStack migration readiness based on assessment engine output. This document establishes:

- How `ScoredCompatibilityResult.score` maps to operational readiness
- How issues are classified and prioritized
- When a VM is considered safe to migrate vs. requires remediation
- How to interpret benchmark boundaries

This is the authoritative guide for operators using the assessment engine.

## 2. Compatibility Score Interpretation

### 2.1 Score Ranges

| Score Range | Label | Meaning | Action |
|-------------|-------|---------|--------|
| 0.90 – 1.00 | **Ready** | No critical issues, all checks pass or have minor warnings | Safe to migrate |
| 0.70 – 0.89 | **Ready with caveats** | Minor compatibility issues, no critical blockers | Migrate after review |
| 0.50 – 0.69 | **Conditional** | Medium-severity issues present, may require remediation | Must review all issues |
| 0.00 – 0.49 | **Blocked** | Critical issues found or score below threshold | Do not migrate |

**Score threshold for `compatible = true`**: ≥ 0.50 AND no critical-severity incompatible issues.

### 2.2 Score Calibration

The base score is 1.0. Each incompatible issue deducts:

| Severity | Deduction | When Applied |
|----------|-----------|-------------|
| Critical | −0.30 | VM cannot function in OpenStack (e.g., suspended, unsupported OS, no vCPUs) |
| High | −0.20 | Significant migration risk (e.g., missing OS, IDE controllers, Secure Boot without UEFI) |
| Medium | −0.10 | Moderate risk (e.g., EFI firmware, VMware Tools missing, NVMe controller, SR-IOV NIC) |
| Low | −0.05 | Minor concern (e.g., large disk, large CPU, legacy NIC type) |
| Info | 0.00 | Informational only (no score impact) |

**Floor**: Score cannot go below 0.0.

**Critical blocker rule**: If any critical-severity issue exists, `compatible = false` regardless of score.

## 3. Issue Classification Guide

### 3.1 Critical Issues — Migration Blockers

| Issue | Detection | Remediation |
|-------|-----------|-------------|
| VM suspended | `power_state == "suspended"` | Power on VM before migration |
| Unsupported OS | Guest OS matches `UNSUPPORTED_OS_PREFIXES` (Solaris, HP-UX, AIX, etc.) | OS conversion or re-platform |
| No vCPUs | `hardware.cpu_count <= 0` | Check VM configuration |
| No memory | `hardware.memory_mb <= 0` | Check VM configuration |
| RDM/VMDK direct path | Manual detection (not yet automated) | Convert to VMDK or use nova |

### 3.2 High-Severity Issues — Significant Risk

| Issue | Detection | Remediation |
|-------|-----------|-------------|
| Guest OS not detected | `guest_os` is empty/None | Install VMware Tools or set guest OS manually |
| No disks attached | `hardware.disks` is empty | Add at least one disk |
| Secure Boot enabled | `secure_boot_enabled == true` | Disable Secure Boot or ensure OpenStack UEFI support |
| IDE disk controller | `disk_controller_types` contains "ide" | Convert to virtio-scsi |
| No VMware Tools | `vmware_tools_status` is "notInstalled" or "notRunning" | Install/start VMware Tools |

### 3.3 Medium-Severity Issues — Moderate Risk

| Issue | Detection | Remediation |
|-------|-----------|-------------|
| EFI/UEFI firmware | `firmware == "efi"` | Ensure OpenStack flavor has `hw_firmware_type=uefi` |
| VMware Tools not running | `vmware_tools_status` contains "notRunning" | Start VMware Tools |
| NVMe disk controller | `disk_controller_types` contains "nvme" | Ensure OpenStack supports NVMe emulation |
| vmxnet2 NIC | `nic_type == "vmxnet2"` | Convert to vmxnet3 or virtio |
| SR-IOV NIC | `nic_type == "sriov"` | Ensure OpenStack SR-IOV support |
| Unknown NIC type | `nic_type == "unknown"` | Investigate NIC type in vCenter |

### 3.4 Low-Severity Issues — Minor Concern

| Issue | Detection | Remediation |
|-------|-----------|-------------|
| Unknown guest OS | Guest OS not in supported or unsupported lists | Verify manually |
| >128 vCPUs | `hardware.cpu_count > 128` | May exceed OpenStack quota |
| >512 GB RAM | `hardware.memory_mb > 524288` | May exceed OpenStack quota |
| >2 TB total disk | Sum of disk sizes > 2000 GB | Large volume migration may be slow |
| No network adapters | `hardware.nics` is empty | VM will be isolated after migration |
| e1000 NIC | `nic_type == "e1000"` | Consider upgrading NIC type |
| LSI Logic controller | `disk_controller_types` contains "lsilogic" | Generally compatible, legacy |

## 4. Benchmark Interpretation Boundaries

### 4.1 Synthetic vs. Live Validation

| Aspect | Synthetic Benchmark | Live Validation |
|--------|-------------------|-----------------|
| VM data | Generated `VMSummary` objects | Real vCenter `VirtualMachine` objects |
| vCenter latency | Not included | Included (pyVmomi SDK calls) |
| OpenStack latency | Not included | Included (API calls to Nova/Neutron) |
| Network RTT | Localhost only | Real network latency |
| Database contention | None | Possible under concurrent load |
| Redis overhead | Not included | Included if Redis cache enabled |
| TLS handshake | Not included | Included if HTTPS enabled |

### 4.2 When to Trust Synthetic Results

Synthetic benchmarks are reliable predictors for:

- **Compatibility engine throughput**: Pure Python logic, no external deps → ~64K VM/s sustained
- **Mapping engine throughput**: Local computation, no I/O → ~24K VM/s
- **Plan generation throughput**: Local computation → ~45K VM/s
- **Memory baseline**: ~75 MB RSS for service layer + ~13 MB delta per 500 VMs evaluated

### 4.3 When NOT to Trust Synthetic Results

Synthetic benchmarks do NOT predict:

- End-to-end API response time (includes vCenter/OpenStack RTT)
- Concurrent session limits (vCenter has hard connection limits)
- Database write contention under parallel assessment
- pyVmomi serialization cost for large VM configurations
- Real-world network jitter and timeout behavior

### 4.4 Dataset-Based Benchmark Interpretation

Phase 5A introduced **dataset-based benchmarks** that bridge the gap between fully synthetic and live validation.

#### 4.4.1 What Dataset Benchmarks Add

| Factor | Synthetic | Dataset-Based | Live |
|--------|:---------:|:-------------:|:----:|
| Pydantic deserialization overhead | ❌ | ✅ | ✅ |
| Realistic VM data diversity | ❌ | ✅ | ✅ |
| JSON I/O for inventory loading | ❌ | ✅ | ✅ |
| OpenStack catalog parsing | ❌ | ✅ | ✅ |
| Flavor mapping from catalog | Mock only | ✅ Mock | ✅ Real |
| Disk/NIC hardware variety | ❌ | ✅ | ✅ |
| Edge case coverage | Manual | ✅ 23 scenarios | Limited |
| vCenter API latency | ❌ | ❌ | ✅ |
| OpenStack API latency | ❌ | ❌ | ✅ |
| Network RTT / TLS overhead | ❌ | ❌ | ✅ |

#### 4.4.2 Interpreting Dataset Benchmark Results

Dataset benchmarks are reliable for:

- **Engine correctness**: All engine paths exercised with realistic data shapes
- **Scalability estimation**: 100/500/1000 VM datasets provide throughput scaling data (linear up to 1000 VMs)
- **Mapping plausibility**: Flavor/network mapping results can be inspected for reasonableness
- **Incompatibility profiling**: Realistic distribution of OS, hardware, and configuration issues
- **Edge case handling**: 23 pre-defined scenarios verify correct behavior for unusual configurations

Dataset benchmarks are NOT reliable for:

- **End-to-end latency**: No network I/O, no pyVmomi SDK calls
- **Concurrency limits**: No real vCenter session pool contention
- **Database write throughput**: Assessment persistence not included
- **Timeout behavior**: No external API timeouts to trigger retry logic

#### 4.4.3 When to Use Each Layer

| Goal | Use |
|------|-----|
| Fast code iteration / regression check | `benchmark_vmware_assessment.py` (synthetic) |
| Validate with realistic VM data | `benchmark_from_dataset.py --all` |
| Test edge cases and OS/hardware diversity | Dataset scenarios in `benchmark_data/scenarios/` |
| Validate resilience without live infra | `recovery_validation.py` |
| Production readiness sign-off | `validate_vcenter.py` + `validate_openstack_mapping.py` (live) |

## 5. Migration Risk Classification

### 5.1 VM Risk Levels

| Risk Level | Score Range | Critical Issues | Recommended Action |
|------------|-------------|-----------------|-------------------|
| Low | ≥ 0.90 | 0 | Standard migration workflow |
| Medium | 0.50 – 0.89 | 0 | Review flagged issues before migration |
| High | any | 1+ | Resolve critical issues before migration |
| High | < 0.50 | 0+ | Comprehensive remediation required |

### 5.2 Migration Plan Priority

The `VMwarePlanService.generate_plan()` sorts VMs by:

1. **Risk (ascending)**: Low-risk VMs first (faster wins)
2. **Dependency**: VMs with no dependencies before those with dependencies
3. **Size (ascending)**: Smaller VMs first (quicker validation)

## 6. Operational Limits

| Parameter | Synthetic Limit | Live Expected Limit | Notes |
|-----------|----------------|---------------------|-------|
| Max concurrent assessments | Unlimited (local) | 10–50 (vCenter session pool) | Configurable via `max_concurrency` |
| Max VM inventory | 500+ (tested) | 1000+ (untested) | vCenter pagination may apply |
| Connection pool size | 5 (configurable) | 5 (configurable) | `max_pool_size` |
| Connection TTL | 300s | 300s | `session_ttl` |
| Per-VM timeout | 300s | 300s | Configurable per request |
| Assessment persistence | SQLite | SQLite/PostgreSQL | DB type affects write throughput |

## 7. Pre-Migration Checklist

Before executing any migration based on assessment output:

- [ ] Run assessment against target VM(s)
- [ ] Verify `compatible = true` for each VM
- [ ] Review all issues with severity ≥ medium
- [ ] Confirm flavor assignment is acceptable
- [ ] Confirm network mapping is correct
- [ ] Verify OpenStack has sufficient quota (CPU, RAM, disk, network)
- [ ] For UEFI VMs: confirm OpenStack supports `hw_firmware_type=uefi`
- [ ] For Secure Boot VMs: disable or confirm OpenStack support
- [ ] For large VMs (>2 TB disk): plan for extended migration window
- [ ] Document any known limitations for the target environment

---

*This document is a reference for migration-readiness interpretation. It will be updated as live validation results become available.*

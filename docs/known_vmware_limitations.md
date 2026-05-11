# Known VMware Limitations

> Phase 5 — vMachine → AI Datacenter Control Plane
> **Status**: Reference document — catalog of known limitations, unsupported configurations, and operational constraints

## 1. Purpose

This document catalogs:

- VMware configurations that the assessment engine does NOT support
- OpenStack configurations that may cause migration issues
- Known gaps in detection, mapping, or compatibility evaluation
- Operational constraints that affect validation accuracy

This is NOT a list of bugs. It is a design-limitation catalog for operators evaluating migration feasibility.

## 2. VMware Configurations — Not Assessed

### 2.1 Hardware Features

| Feature | Status | Reason |
|---------|--------|--------|
| vGPU / vSGA passthrough | ❌ Not detected | No pyVmomi property extracted |
| PCI passthrough (VVOL) | ❌ Not detected | No pyVmomi property extracted |
| NPIV / Fibre Channel | ❌ Not detected | No pyVmomi property extracted |
| VM encryption | ❌ Not detected | No pyVmomi property extracted |
| Fault Tolerance (FT) | ❌ Not detected | Not enumerated in inventory |
| vMotion in progress | ❌ Not detected | Not enumerated in inventory |
| Storage DRS | ❌ Not evaluated | No storage policy check |
| Content Library sync | ❌ Not evaluated | Out of scope |
| Cross-vCenter vMotion | ❌ Not evaluated | Out of scope |

### 2.2 Guest OS

| Category | Status | Notes |
|----------|--------|-------|
| Solaris (all versions) | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| HP-UX | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| AIX | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| macOS / Darwin | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| OS/2 | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| NetWare | ❌ Unsupported | Listed in `UNSUPPORTED_OS_PREFIXES` |
| Linux (CentOS, Debian, Ubuntu, RHEL, etc.) | ✅ Supported | 12+ distribution prefixes |
| Windows Server (2012–2022) | ✅ Supported | 8+ version prefixes |
| Windows 10/11 | ✅ Supported | Detection via prefix match |
| FreeBSD | ✅ Supported | Listed in `SUPPORTED_OS_PREFIXES` |
| Unknown OS | ⚠️ Low-severity issue | Compatible flag remains true; operator should verify |

### 2.3 Disk Controller Types

| Controller | Assessment | OpenStack Compatibility |
|------------|-----------|----------------------|
| PVSCSI | ⚠️ Not detected separately | Generally compatible (vmw_pvscsi driver in Linux) |
| LSI Logic SAS | ✅ Detected as `lsilogic` | Compatible, legacy |
| LSI Logic Parallel | ✅ Detected as `lsilogic` | Compatible, legacy |
| IDE | ✅ Detected as `ide` | ❌ High-severity — may not be supported |
| NVMe | ✅ Detected as `nvme` | ⚠️ Requires OpenStack NVMe emulation |
| VMware Paravirtual | ⚠️ Not detected separately | Treated as general SCSI controller |
| SATA | ⚠️ Not detected | No specific check implemented |
| BusLogic | ⚠️ Not detected | Very legacy — rare in practice |

### 2.4 NIC Types

| NIC Type | Assessment | OpenStack Compatibility |
|----------|-----------|----------------------|
| e1000 | ✅ Detected | Compatible, legacy — low-severity issue |
| e1000e | ✅ Detected | Compatible, no issue raised |
| vmxnet2 | ✅ Detected | ⚠️ Medium-severity — recommend conversion |
| vmxnet3 | ✅ Detected | ✅ No issue raised (modern, recommended) |
| SR-IOV | ✅ Detected | ⚠️ Medium-severity — requires SR-IOV support |
| Unknown | ✅ Detected as `unknown` | ⚠️ Medium-severity — investigate |
| Not specified | ⚠️ Treated as unknown | May indicate detection gap |

## 3. Detection Gaps

### 3.1 Extracted via pyVmomi (Implemented)

| Property | Extraction Method | Verified |
|----------|------------------|----------|
| VM name | `vm.name` | ⏳ Pending live test |
| Power state | `vm.runtime.powerState` | ⏳ Pending live test |
| Guest OS | `vm.config.guestFullName` | ⏳ Pending live test |
| CPU count | `vm.hardware.numCPU` | ⏳ Pending live test |
| Memory MB | `vm.hardware.memoryMB` | ⏳ Pending live test |
| Disk count & capacity | `vm.config.hardware.device` (filter disk type) | ⏳ Pending live test |
| NIC count & types | `vm.config.hardware.device` (filter nic type) | ⏳ Pending live test |
| Firmware type | `vm.config.firmware` | ⏳ Pending live test |
| Secure Boot | `vm.config.bootOptions.efiSecureBoot` | ⏳ Pending live test |
| VMware Tools | `vm.guest.toolsRunningStatus`, `vm.guest.toolsVersion` | ⏳ Pending live test |
| Disk controllers | `vm.config.hardware.device` (filter controller type) | ⏳ Pending live test |

### 3.2 NOT Extracted (Gaps)

| Property | Reason | Impact |
|----------|--------|--------|
| vGPU profile | Not extracted from `vm.config` | Cannot detect vGPU passthrough |
| DRS rules (VM-VM affinity) | Not extracted | Cannot assess placement constraints |
| Storage policies | Not extracted | Cannot assess storage compatibility |
| Resource pools | Not extracted | Cannot assess resource pool mapping |
| Tags / Categories | Not extracted | Cannot assess tag-based policies |
| VM snapshots | Not extracted | Cannot assess snapshot chain depth |
| vApp properties | Not extracted | Cannot assess vApp configuration |
| Guest OS customization | Not extracted | Cannot assess customization spec |
| CDROM / ISO mount | Not extracted | Cannot assess ISO boot dependency |
| Floppy drive | Not extracted | Legacy — rarely used |
| Parallel / serial ports | Not extracted | Rarely used |
| USB controllers | Not extracted | Cannot assess USB passthrough |

## 4. OpenStack Compatibility Gaps

### 4.1 Features Not Verified

| Feature | Status | Notes |
|---------|--------|-------|
| Quota sufficiency | ⚠️ Partial | CPU/RAM/disk checks only — no API call |
| Floating IP availability | ❌ Not checked | Requires Neutron API call |
| Volume type availability | ❌ Not checked | Requires Cinder API call |
| Image existence | ❌ Not checked | Glance lookup not implemented |
| Network MTU / segmentation | ❌ Not checked | Assumes OpenStack defaults |
| Security group rules | ❌ Not checked | Out of scope for assessment |
| DNS resolution | ❌ Not checked | Assumes OpenStack DNS works |
| Hypervisor type (KVM vs ESXi) | ❌ Not checked | Assumes KVM-based OpenStack |

### 4.2 OpenStack Version Requirements

| Feature | Minimum OpenStack Version | Notes |
|---------|--------------------------|-------|
| UEFI boot | Train+ (via `hw_firmware_type` flavor extra spec) | Verify in target environment |
| Secure Boot | Ussuri+ (via `hw_firmware_type` + Secure Boot) | Verify in target environment |
| SR-IOV | Mitaka+ (via `pci_passthrough` config) | May require neutron configuration |
| NVMe emulation | Wallaby+ (via `hw_disk_bus=nvme`) | Rare — verify availability |

## 5. Benchmark Limitations

### 5.1 Synthetic Benchmark Constraints

The synthetic benchmark (`scripts/benchmark_vmware_assessment.py`) has the following constraints:

| Constraint | Detail |
|------------|--------|
| VM data | Generated `VMSummary` objects — no real vCenter data |
| No I/O | All services run in-process — no network calls |
| No serialization | No pyVmomi object serialization overhead |
| No contention | Single-process, no concurrent database access |
| Cache state | Cold/warm cache both in-memory — no Redis RTT |
| Memory measurement | RSS of single process — no Gunicorn worker overhead |
| VM variety | 20 OS templates, 8 power states, 5 tools statuses — covers common cases but not all edge cases |

### 5.2 What Synthetic Tests Cannot Measure

- End-to-end API latency (includes vCenter + OpenStack RTT)
- Connection pool behavior under real vCenter load
- pyVmomi serialization cost for VMs with 10+ disks or 8+ NICs
- Database write throughput under concurrent assessment persistence
- vCenter session limits (hard limit of ~40 concurrent sessions per user)
- Network jitter, packet loss, TLS handshake cost
- Redis cache network RTT when deployed on separate host

## 6. Operational Constraints

| Constraint | Limit | Notes |
|------------|-------|-------|
| Max concurrent vCenter sessions | 5 (pool default) | Configurable via `max_pool_size` |
| Connection TTL | 300s | Sessions auto-reconnect after expiry |
| Health check interval | 60s | Stale connections detected and reconnected |
| Inventory cache TTL | 300s | In-memory per-worker cache |
| Parallel assessment timeout | 300s (per VM) | Configurable per-request |
| Max VM IDs per assessment request | Not enforced | Large lists may consume significant memory |
| Assessment persistence | SQLite (dev) / PostgreSQL (prod) | SQLite may bottleneck under high concurrent writes |

## 7. Resolution Roadmap

| Limitation | Priority | Planned Resolution |
|------------|----------|-------------------|
| vGPU / PCI passthrough detection | Low | Future extraction from pyVmomi `vm.config` |
| VM snapshot detection | Low | Future extraction |
| Floating IP availability check | Medium | Future Neutron API integration |
| Quota API check | Medium | Future Nova quota API call |
| Storage policy check | Low | Future vCenter storage API |
| OpenStack UEFI support verification | Medium | Requires flavor extra_spec lookup |

---

*This document will be updated as live validation identifies additional limitations or gaps.*

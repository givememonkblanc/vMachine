# VMware Migration Assessment Engine — Architecture

> Phase 4 of the vMachine → AI Datacenter Control Plane roadmap.
> **Scope**: Assessment only — no VM disk conversion or live migration execution.

## 1. Purpose & Scope

### 1.1 Goal

Build a **Migration Assessment Engine** that enables datacenter operators to evaluate
VMware vCenter inventory, map VMs to OpenStack equivalents, detect compatibility
issues, and generate migration plans — **before** any actual data movement occurs.

### 1.2 Non-Goals (explicitly excluded from Phase 4)

- VM disk export / conversion (existing `MigrationManager.execute_vmware_migration`)
- Glance image upload
- OpenStack server creation
- Live migration orchestration
- GPU telemetry or observability
- DCIM integration
- Multi-region orchestration

### 1.3 Existing Code Preserved

The existing `app/modules/migration/manager.py` (`MigrationManager`) and
`app/worker.py` (`execute_vmware_migration_task`) are **kept intact** but are
**not called** from the Phase 4 assessment flow. They remain available for
future actual migration execution.

---

## 2. System Context

```
+------------------+          +----------------------+
|   vCenter        |          |   OpenStack           |
|   (pyVmomi)      |          |   (openstacksdk)     |
+--------+---------+          +----------+-----------+
         |                               |
         v                               v
+--------+---------+          +----------+-----------+
| VMware Client    |          | OpenStack Client     |
| Factory          |          | Factory              |
+--------+---------+          +----------+-----------+
         |                               |
         v                               v
+--------+-----------------------------------------------+------------------+
|                   Assessment Engine                     |  API Layer       |
|                                                         |                  |
|  +------------------+  +-----------------------------+  |  GET /vms        |
|  | Inventory        |  | Mapping Engine              |  |  GET /vms/{id}   |
|  | Service          |  | - VM → Flavor mapping       |  |  POST /sync      |
|  | - VM list        |  | - Network mapping           |  |  GET /mapping    |
|  | - VM detail      |  | - Disk → Volume mapping     |  |  GET /compat     |
|  | - Datastore      |  +-----------------------------+  |  POST /plan      |
|  | - Cred validation|  +-----------------------------+  |  GET /plan/{id}  |
|  +------------------+  | Compatibility Analyzer      |  +------------------+
|                        | - Unsupported features      |
|  +------------------+  | - OS compatibility          |
|  | Migration Plan   |  | - Resource constraint check |
|  | Service          |  +-----------------------------+
|  | - Plan generation|
|  | - Resource est.  |
|  | - Task tracking  |
|  +------------------+ |
+------------------------------------------------------+
```

---

## 3. Component Architecture

### 3.1 Layer Mapping

```
┌──────────────────────────────────────────────────────┐
│  app/api/v1/endpoints/vmware/inventory.py            │  ← API Layer
│  app/api/v1/endpoints/vmware/assessment.py           │
├──────────────────────────────────────────────────────┤
│  app/services/vmware/                                │  ← Service Layer
│  ├── inventory_service.py                            │
│  ├── mapping_engine.py                               │
│  ├── compatibility.py                                │
│  └── plan_service.py                                 │
├──────────────────────────────────────────────────────┤
│  app/clients/vmware/connection.py                    │  ← Client Layer
├──────────────────────────────────────────────────────┤
│  app/schemas/vmware/                                 │  ← Schemas
│  ├── inventory.py                                    │
│  └── assessment.py                                   │
├──────────────────────────────────────────────────────┤
│  app/models/                                         │  ← DB Models
│  ├── resource_snapshot.py (existing, reused)         │
│  └── migration_task.py (existing, reused)            │
└──────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `VMwareClientFactory` (existing) | vCenter connection lifecycle, credential validation, inventory queries |
| `InventoryService` (new) | VM listing and detail collection, datastore query, sync orchestration |
| `MappingEngine` (new) | VM spec → OpenStack flavor, network, and volume mapping |
| `CompatibilityAnalyzer` (new) | Unsupported feature detection, OS compat, readiness scoring |
| `PlanService` (new) | Migration plan generation, resource estimation, task tracking |

---

## 4. Data Flow

### 4.1 Inventory Sync Flow

```
POST /api/v1/vmware/sync
  │
  ├─ 1. Validate credentials (VMwareClientFactory.connect())
  ├─ 2. List all datacenters
  ├─ 3. For each datacenter:
  │     ├─ List clusters
  │     ├─ List hosts
  │     └─ List VMs
  ├─ 4. For each VM:
  │     ├─ Collect: name, vCPU, RAM, disks, networks, OS, power state
  │     ├─ Collect: datastore paths, network labels, guest details
  │     └─ Store in ResourceSnapshot (raw_data=JSON)
  ├─ 5. Store datastore info in ResourceSnapshot
  └─ 6. Return InventorySummary
```

### 4.2 Assessment Flow

```
GET /api/v1/vmware/assessment/{vm_id}
  │
  ├─ 1. Load VM ResourceSnapshot from DB
  ├─ 2. MappingEngine:
  │     ├─ Map vCPU/RAM/disk → OpenStack flavor (nearest-match)
  │     ├─ Map network labels → OpenStack networks (by name/cidr)
  │     └─ Map disks → OpenStack volumes
  ├─ 3. CompatibilityAnalyzer:
  │     ├─ Check: DVS, PVSCSI, VMXNET3, vMotion requirements
  │     ├─ Check: OS support matrix
  │     ├─ Check: resource constraints (quota, limits)
  │     └─ Compute readiness score
  └─ 4. Return AssessmentReport
```

### 4.3 Migration Plan Flow

```
POST /api/v1/vmware/plan
  │
  ├─ 1. Accept VM list (or all VMs from inventory)
  ├─ 2. For each VM: run assessment
  ├─ 3. Group by:
  │     ├─ Target flavor (same flavor = same batch)
  │     ├─ Target network
  │     └─ Priority/workload type
  ├─ 4. Generate staged plan:
  │     ├─ Phase schedule
  │     ├─ Batched VM groups
  │     ├─ Estimated resource usage
  │     └─ Predicted duration
  └─ 5. Store as MigrationTask (migration_type="assessment_plan")
```

---

## 5. Key Design Decisions

### 5.1 Inventory Storage: ResourceSnapshot

- **Reusing** the existing `ResourceSnapshot` model (`app/models/resource_snapshot.py`)
- `resource_type` = `"vmware_vm"`, `"vmware_datastore"`, `"vmware_network"`
- `external_id` = VM UUID (from vCenter)
- `raw_data` = full VM JSON payload
- No new migration needed for Phase 4

### 5.2 Flavor Mapping Strategy

VMware VM specs → OpenStack Flavor matching:

| VMware Attribute | OpenStack Flavor | Match Strategy |
|-----------------|------------------|----------------|
| vCPU count | vcpus | Exact or ceiling |
| Memory (MB) | ram | Exact or ceiling (nearest 256 MB) |
| Disk (GB) | disk | Root disk = flavor disk, additional = volumes |
| | | Score = weighted Euclidean distance |

```
flavor_score = w_cpu * |vm_vcpu - flavor_vcpus| / max_vcpus
             + w_ram * |vm_ram_mb - flavor_ram| / max_ram
             + w_disk * |vm_disk_gb - flavor_disk| / max_disk

Default weights: w_cpu=0.4, w_ram=0.4, w_disk=0.2
```

### 5.3 Network Mapping Strategy

| VMware Port Group | OpenStack Network | Match Strategy |
|------------------|-------------------|----------------|
| Name | Network name | Exact match (case-insensitive) |
| VLAN ID | Network tag | Exact match |
| CIDR hint | Subnet CIDR | Closest prefix match |

### 5.4 Compatibility Criteria

| Category | Checks | Severity |
|----------|--------|----------|
| Network | DVS (vDS) → OpenStack equivalent | warning |
| Network | Port security rules | info |
| Storage | PVSCSI adapter → virtio-scsi | info |
| Storage | RDM/VMDK direct path | critical |
| Compute | vGPU/vSGA passthrough | critical |
| Compute | VMware Tools dependencies | warning |
| OS | End-of-life OS | warning |
| OS | Custom kernel modules | info |
| Resource | Quota insufficient (CPU/RAM/disk) | critical |
| Resource | Floating IP shortage | warning |

### 5.5 Thread Safety

vCenter connections in `VMwareClientFactory` are **not** thread-safe (pyVmomi
`SmartConnect`). The inventory service uses a simple **per-request connection**
pattern (connect → collect → disconnect) rather than a shared pool, because
assessment is an operational tool, not a high-throughput data path.

---

## 6. API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/vmware/status` | vCenter connection status & credential validation |
| `POST` | `/api/v1/vmware/sync` | Trigger full inventory sync from vCenter |
| `GET` | `/api/v1/vmware/vms` | List all discovered VMs (from local cache) |
| `GET` | `/api/v1/vmware/vms/{vm_id}` | VM detail with current power state |
| `GET` | `/api/v1/vmware/datastores` | List datastores |
| `GET` | `/api/v1/vmware/networks` | List VMware networks/port groups |
| `GET` | `/api/v1/vmware/mapping/{vm_id}` | VMware VM → OpenStack mapping result |
| `GET` | `/api/v1/vmware/assessment/{vm_id}` | Full compatibility assessment |
| `POST` | `/api/v1/vmware/plan` | Generate migration plan from VM selection |
| `GET` | `/api/v1/vmware/plan/{plan_id}` | Migration plan details |
| `GET` | `/api/v1/vmware/plans` | List all migration plans |

Detailed request/response schemas in `migration_assessment_api.md`.

> **⚠️ Breaking Schema Change**: The `/api/v1/vmware/assess/{vm_id}/compatibility`
> endpoint now returns `ScoredCompatibilityResult` (with `score: float`,
> `issues: list[IssueDetail]`, `summary: str`) instead of the previous
> `VMCompatibilityResult` (flat boolean fields `os_supported`, `cpu_compatible`,
> `memory_compatible`, `disk_compatible`, `network_compatible`, `power_state`).
> Old clients must migrate to the new `issues[]` + `score` format.
> `VMCompatibilityResult` is preserved in the schema module for backward-reference
> but no longer used by any endpoint.

---

## 7. Metrics

Defined in `app/common/metrics/custom.py`:

| Metric | Type | Labels |
|--------|------|--------|
| `vmachine_vmware_inventory_count` | Gauge | resource_type (vm/datastore/network) |
| `vmachine_vmware_sync_duration_seconds` | Histogram | - |
| `vmachine_vmware_sync_errors_total` | Counter | error_type |
| `vmachine_vmware_assessment_duration_seconds` | Histogram | - |
| `vmachine_vmware_compatibility_issues_total` | Counter | issue_severity (critical/warning/info) |
| `vmachine_vmware_migration_readiness` | Gauge | vm_id (0=draft, 1=ready, 2=blocked) |

---

## 8. Dependencies

- **pyVmomi** (existing dependency) — VMware vSphere SDK for Python
- No new external dependencies for Phase 4

---

## 9. File Layout Summary

```
New files (Phase 4):
  app/schemas/vmware/
  ├── __init__.py
  ├── inventory.py           # VM, Datastore, Network schemas
  └── assessment.py          # Mapping, Compatibility, Plan schemas

  app/services/vmware/
  ├── __init__.py
  ├── inventory_service.py   # VMware inventory collection & sync
  ├── mapping_engine.py      # OpenStack resource mapping
  ├── compatibility.py       # Compatibility analysis
  └── plan_service.py        # Migration plan generation

  app/api/v1/endpoints/vmware/
  ├── __init__.py
  ├── inventory.py           # Inventory & sync endpoints
  └── assessment.py          # Assessment & plan endpoints

Modified files:
  app/api/router.py          # Register vmware namespace
  app/api/deps/services.py   # Add VMware service dependencies
  app/common/metrics/custom.py  # Add assessment metrics
  docs/migration_assessment_api.md  # API reference (this doc's companion)
```

---

## 10. Migration from Current State

The existing codebase already contains:
- `app/clients/vmware/connection.py` — `VMwareClientFactory` (connect, get_vm_by_name, export_vm_disk)
- `app/modules/migration/manager.py` — `MigrationManager` (execute_vmware_migration)
- `app/worker.py` — ARQ worker for async migration execution

Phase 4 **extends** `VMwareClientFactory` with inventory-specific methods
(list_vms, get_vm_detail, list_datastores, list_networks, validate_credentials)
and builds a new service layer **on top** of it. The existing `MigrationManager`
is untouched and remains available for Phase 5 (actual migration execution).

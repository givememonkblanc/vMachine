# Migration Assessment API Reference

> Phase 4 — VMware → OpenStack Migration Assessment Engine.
> Base path: `/api/v1/vmware` (registered as `prefix="/vmware"`)

---

## 1. Connection & Credentials

### `GET /api/v1/vmware/status`

vCenter connection 상태와 credential 유효성을 확인합니다.

**Response `200 OK`:**

```json
{
  "connected": true,
  "host": "vcenter.example.com",
  "version": "8.0.3",
  "api_type": "VirtualCenter",
  "datacenter_count": 3,
  "cluster_count": 12,
  "host_count": 48
}
```

**Response `503 Service Unavailable`** (VMware settings not configured):

```json
{
  "detail": "VMware settings are incomplete"
}
```

**Response `503 Service Unavailable`** (connection failed):

```json
{
  "detail": "Failed to connect to VMware: ...",
  "error_code": "vmware_integration_error"
}
```

---

## 2. Inventory Sync

### `POST /api/v1/vmware/sync`

vCenter에서 전체 인벤토리를 수집하여 로컬 DB (`ResourceSnapshot`)에 저장합니다.

**Request Body:** none (credentials are read from environment variables)

**Response `200 OK`:**

```json
{
  "sync_id": "a1b2c3d4-...",
  "started_at": "2026-05-11T10:00:00Z",
  "finished_at": "2026-05-11T10:00:45Z",
  "duration_seconds": 45.3,
  "vms_discovered": 156,
  "datastores_discovered": 18,
  "networks_discovered": 24,
  "clusters_discovered": 12,
  "errors": []
}
```

**Behavior:**
1. Connects to vCenter via `VMwareClientFactory`
2. Iterates all datacenters → clusters → hosts → VMs
3. Stores each VM as `ResourceSnapshot(resource_type="vmware_vm", ...)`
4. Stores datastores as `ResourceSnapshot(resource_type="vmware_datastore", ...)`
5. Stores networks as `ResourceSnapshot(resource_type="vmware_network", ...)`
6. Replaces previous inventory (same `external_id` = upsert)

**Error Response `500`:**

```json
{
  "detail": "Inventory sync failed: ...",
  "error_code": "vmware_sync_error"
}
```

---

## 3. VM Inventory

### `GET /api/v1/vmware/vms`

로컬에 캐시된 VMware VM 목록을 반환합니다. 필터링 가능.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `power_state` | str | - | `poweredOn`, `poweredOff`, `suspended` |
| `cluster` | str | - | 클러스터 이름 필터 |
| `datacenter` | str | - | 데이터센터 이름 필터 |
| `guest_os` | str | - | 게스트 OS 필터 (prefix match) |
| `limit` | int | 100 | 최대 반환 개수 |
| `offset` | int | 0 | 페이지 오프셋 |

**Response `200 OK`:**

```json
{
  "items": [
    {
      "vm_id": "vm-1234",
      "name": "web-server-01",
      "uuid": "4208b3a0-...",
      "power_state": "poweredOn",
      "cpu_count": 4,
      "memory_mb": 8192,
      "guest_os": "ubuntu64Guest",
      "guest_os_full": "Ubuntu Linux (64-bit)",
      "cluster": "production-cluster",
      "datacenter": "datacenter-01",
      "datastores": ["datastore-01", "datastore-02"],
      "networks": ["VM Network", "Storage Network"],
      "disk_count": 2,
      "total_disk_gb": 120,
      "discovered_at": "2026-05-11T10:00:45Z",
      "compatibility_score": null
    }
  ],
  "total": 156,
  "limit": 100,
  "offset": 0
}
```

### `GET /api/v1/vmware/vms/{vm_id}`

특정 VM의 상세 정보를 반환합니다. `vm_id`는 vCenter의 VM UUID 또는 로컬 `external_id`입니다.

**Response `200 OK`:**

```json
{
  "vm_id": "vm-1234",
  "name": "web-server-01",
  "uuid": "4208b3a0-...",
  "power_state": "poweredOn",
  "cpu_count": 4,
  "cores_per_socket": 2,
  "memory_mb": 8192,
  "guest_os": "ubuntu64Guest",
  "guest_os_full": "Ubuntu Linux (64-bit)",
  "guest_id": "ubuntu64Guest",
  "host": "esxi-07.prod.example.com",
  "cluster": "production-cluster",
  "datacenter": "datacenter-01",
  "disks": [
    {
      "disk_id": 2000,
      "label": "Hard disk 1",
      "capacity_gb": 40,
      "thin_provisioned": true,
      "datastore": "datastore-01",
      "mode": "persistent",
      "adapter_type": "lsilogic"
    },
    {
      "disk_id": 2001,
      "label": "Hard disk 2",
      "capacity_gb": 80,
      "thin_provisioned": true,
      "datastore": "datastore-02",
      "mode": "persistent",
      "adapter_type": "lsilogic"
    }
  ],
  "networks": [
    {
      "label": "VM Network",
      "vlan_id": null,
      "connected": true,
      "mac_address": "00:50:56:ab:cd:ef",
      "ip_addresses": ["192.168.1.100"]
    },
    {
      "label": "Storage Network",
      "vlan_id": 100,
      "connected": true,
      "mac_address": "00:50:56:11:22:33",
      "ip_addresses": ["10.0.0.50"]
    }
  ],
  "datastores": ["datastore-01", "datastore-02"],
  "annotations": "Production web server",
  "vmware_tools": {
    "status": "toolsOk",
    "version": "12345"
  },
  "discovered_at": "2026-05-11T10:00:45Z"
}
```

**Response `404`:**

```json
{
  "detail": "VM 'vm-9999' not found in inventory"
}
```

---

## 4. Datastores & Networks

### `GET /api/v1/vmware/datastores`

로컬에 캐시된 데이터스토어 목록을 반환합니다.

**Response `200 OK`:**

```json
{
  "items": [
    {
      "name": "datastore-01",
      "type": "VMFS",
      "capacity_gb": 2048,
      "free_gb": 890,
      "accessible": true,
      "datacenter": "datacenter-01",
      "multiple_host_access": true
    }
  ],
  "total": 18
}
```

### `GET /api/v1/vmware/networks`

로컬에 캐시된 VMware 네트워크/포트 그룹 목록을 반환합니다.

**Response `200 OK`:**

```json
{
  "items": [
    {
      "name": "VM Network",
      "type": "DistributedVirtualPortgroup",
      "vlan_id": null,
      "vswitch": "dvSwitch-01",
      "datacenter": "datacenter-01",
      "accessible": true
    }
  ],
  "total": 24
}
```

---

## 5. Mapping

### `GET /api/v1/vmware/mapping/{vm_id}`

VMware VM → OpenStack 리소스 매핑 결과를 반환합니다.

**Response `200 OK`:**

```json
{
  "vm_id": "vm-1234",
  "vm_name": "web-server-01",
  "flavor_mapping": {
    "recommended_flavor": "m1.medium",
    "alternative_flavors": [
      {"flavor": "m1.small", "score": 0.65, "reason": "under-provisioned CPU"},
      {"flavor": "m1.large", "score": 0.70, "reason": "over-provisioned RAM"}
    ],
    "match_score": 0.92,
    "vm_spec": {"vcpus": 4, "ram_mb": 8192, "disk_gb": 40},
    "flavor_spec": {"vcpus": 4, "ram_mb": 8192, "disk_gb": 40}
  },
  "network_mappings": [
    {
      "vmware_network": "VM Network",
      "openstack_network": "provider-net-vlan100",
      "match_type": "name",
      "confidence": "high"
    },
    {
      "vmware_network": "Storage Network",
      "openstack_network": null,
      "match_type": null,
      "confidence": "none",
      "note": "No matching OpenStack network found"
    }
  ],
  "volume_mappings": [
    {
      "disk_label": "Hard disk 1",
      "capacity_gb": 40,
      "mapped_as": "root_disk",
      "openstack_volume_type": null
    },
    {
      "disk_label": "Hard disk 2",
      "capacity_gb": 80,
      "mapped_as": "volume",
      "openstack_volume_type": "ceph-ssd",
      "suggested_volume_name": "web-server-01-data"
    }
  ]
}
```

---

## 6. Compatibility Assessment

### `GET /api/v1/vmware/assessment/{vm_id}`

특정 VM의 마이그레이션 호환성 평가 보고서를 반환합니다.

**Response `200 OK`:**

```json
{
  "vm_id": "vm-1234",
  "vm_name": "web-server-01",
  "overall_readiness": "ready",
  "readiness_score": 85,
  "summary": {
    "total_issues": 3,
    "critical": 0,
    "warning": 2,
    "info": 1
  },
  "issues": [
    {
      "category": "network",
      "severity": "warning",
      "title": "Distributed Virtual Switch detected",
      "description": "VM is connected to a DVS port group. OpenStack networking must be configured with equivalent provider networks.",
      "affected_object": "VM Network",
      "recommendation": "Create equivalent OpenStack provider network with matching VLAN ID"
    },
    {
      "category": "storage",
      "severity": "warning",
      "title": "Thin-provisioned disk detected",
      "description": "Disk 'Hard disk 1' is thin-provisioned. Ensure sufficient capacity in OpenStack back-end.",
      "affected_object": "Hard disk 1 (40 GB)",
      "recommendation": "Verify Ceph/RBD pool has sufficient overcommit ratio"
    },
    {
      "category": "os",
      "severity": "info",
      "title": "VMware Tools installed",
      "description": "VMware Tools version 12345 detected. OpenStack expects cloud-init for guest customization.",
      "affected_object": "VMware Tools v12345",
      "recommendation": "Install cloud-init package in guest OS after migration"
    }
  ],
  "recommended_flavor": "m1.medium",
  "estimated_openstack_resource": {
    "vcpus": 4,
    "ram_mb": 8192,
    "root_disk_gb": 40,
    "additional_volumes_gb": 80,
    "networks_required": 2
  }
}
```

**Readiness Levels:**

| Score | Level | Description |
|-------|-------|-------------|
| 80-100 | `ready` | Migration 가능. 권장사항만 있음 |
| 50-79 | `conditional` | 일부 이슈 해결 후 migration 가능 |
| 0-49 | `blocked` | Critical 이슈로 migration 불가 |

---

## 7. Migration Plan

### `POST /api/v1/vmware/plan`

선택한 VM 리스트에 대한 마이그레이션 계획을 생성합니다.

**Request Body:**

```json
{
  "name": "Q2 Production Migration Wave 1",
  "description": "First wave of production workload migration",
  "vm_ids": ["vm-1234", "vm-1235", "vm-1236"],
  "include_all": false,
  "batch_size": 5,
  "parallel_batches": 2,
  "target_flavor_overrides": {
    "vm-1234": "m1.large"
  },
  "target_network_overrides": {}
}
```

**Response `201 Created`:**

```json
{
  "plan_id": "plan-001",
  "name": "Q2 Production Migration Wave 1",
  "status": "draft",
  "created_at": "2026-05-11T10:30:00Z",
  "summary": {
    "total_vms": 3,
    "ready": 2,
    "conditional": 1,
    "blocked": 0
  },
  "estimated_resources": {
    "total_vcpus": 12,
    "total_ram_mb": 24576,
    "total_root_disk_gb": 120,
    "total_additional_volumes_gb": 80,
    "networks_required": ["provider-net-vlan100"]
  },
  "batches": [
    {
      "batch_id": 1,
      "vms": ["vm-1234", "vm-1235"],
      "estimated_duration_minutes": 45,
      "dependencies": []
    },
    {
      "batch_id": 2,
      "vms": ["vm-1236"],
      "estimated_duration_minutes": 30,
      "dependencies": [1]
    }
  ],
  "issues_summary": {
    "critical": 0,
    "warning": 3,
    "info": 2
  }
}
```

### `GET /api/v1/vmware/plan/{plan_id}`

특정 마이그레이션 계획의 상세 정보를 조회합니다.

**Response `200 OK`:** (same schema as plan creation response)

### `GET /api/v1/vmware/plans`

모든 마이그레이션 계획 목록을 조회합니다.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | str | - | `draft`, `in_progress`, `completed`, `cancelled` |
| `limit` | int | 50 | 최대 반환 개수 |

**Response `200 OK`:**

```json
{
  "items": [
    {
      "plan_id": "plan-001",
      "name": "Q2 Production Migration Wave 1",
      "status": "draft",
      "vm_count": 3,
      "ready_count": 2,
      "blocked_count": 0,
      "created_at": "2026-05-11T10:30:00Z"
    }
  ],
  "total": 1
}
```

### `PATCH /api/v1/vmware/plan/{plan_id}`

마이그레이션 계획 상태를 업데이트합니다.

**Request Body:**

```json
{
  "status": "in_progress"
}
```

**Response `200 OK`:**

```json
{
  "plan_id": "plan-001",
  "name": "Q2 Production Migration Wave 1",
  "status": "in_progress",
  "updated_at": "2026-05-11T11:00:00Z"
}
```

---

## 8. Inventory Summary

### `GET /api/v1/vmware/summary`

전체 VMware 인벤토리 요약 정보를 반환합니다.

**Response `200 OK`:**

```json
{
  "discovered_at": "2026-05-11T10:00:45Z",
  "datacenters": 3,
  "clusters": 12,
  "hosts": 48,
  "vms": {
    "total": 156,
    "powered_on": 112,
    "powered_off": 44,
    "suspended": 0
  },
  "datastores": {
    "total": 18,
    "total_capacity_gb": 36864,
    "total_free_gb": 15360,
    "usage_percent": 58.3
  },
  "guest_os_breakdown": {
    "ubuntu64Guest": 45,
    "rhel7_64Guest": 38,
    "windows9Server64Guest": 32,
    "other": 41
  },
  "vcpus_total": 624,
  "memory_total_gb": 2496
}
```

---

## 9. Router Registration

The VMware namespace is registered in `app/api/router.py`:

```python
from app.api.v1.endpoints.vmware import inventory, assessment

api_router.include_router(inventory.router, prefix="/vmware", tags=["vmware"])
api_router.include_router(assessment.router, prefix="/vmware", tags=["vmware"])
```

---

## 10. Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 404 | `vmware_vm_not_found` | VM not found in local inventory |
| 404 | `vmware_plan_not_found` | Migration plan not found |
| 503 | `vmware_integration_error` | vCenter connection or sync failure |
| 503 | `vmware_not_configured` | VMware credentials not set |
| 400 | `vmware_sync_in_progress` | Sync already running |
| 400 | `vmware_invalid_plan_request` | Invalid plan parameters |
| 500 | `vmware_sync_error` | Unexpected sync error |

---

## 11. Example Workflows

### Full Assessment Workflow

```bash
# 1. Check connection status
curl -s /api/v1/vmware/status | jq .

# 2. Sync inventory from vCenter
curl -s -X POST /api/v1/vmware/sync | jq .

# 3. List discovered VMs
curl -s /api/v1/vmware/vms?power_state=poweredOn | jq .

# 4. Get VM detail
curl -s /api/v1/vmware/vms/vm-1234 | jq .

# 5. Get mapping recommendation
curl -s /api/v1/vmware/mapping/vm-1234 | jq .

# 6. Get compatibility assessment
curl -s /api/v1/vmware/assessment/vm-1234 | jq .

# 7. Create migration plan
curl -s -X POST /api/v1/vmware/plan \
  -H 'Content-Type: application/json' \
  -d '{"name": "Wave 1", "vm_ids": ["vm-1234", "vm-1235"], "batch_size": 5}' | jq .

# 8. Get inventory summary
curl -s /api/v1/vmware/summary | jq .
```

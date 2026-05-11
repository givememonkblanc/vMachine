# Phase 4 — VMware Migration Assessment Engine

## Goal

Build a pre-migration assessment layer that evaluates VMware VM compatibility with OpenStack, maps resources, and generates migration plans — without executing the actual migration (disk export / Glance upload / server create).

## Deliverables

### Design Documents
- `docs/vmware_migration_architecture.md` — Architecture overview, data flow, component layout
- `docs/migration_assessment_api.md` — Full API reference (11 endpoints, request/response schemas, error codes)

### Code Implementation (13 files)

| Layer | File | Purpose |
|-------|------|---------|
| **Schemas** | `app/schemas/vmware/inventory.py` | VMSummary, VMHardware, VMDisk, VMNic, DatastoreSummary, NetworkSummary |
| | `app/schemas/vmware/assessment.py` | FlavorMatchResult, NetworkMappingResult, VMCompatibilityResult, AssessmentResponse, MigrationPlanResponse |
| **Client** | `app/clients/vmware/connection.py` | Extended with list_vms, list_datastores, list_networks, get_vm_detail, get_datastore_detail, get_network_detail, validate_credentials |
| **Services** | `app/services/vmware/inventory_service.py` | VMware inventory collection, caching, DB snapshot sync via ResourceSnapshot model |
| | `app/services/vmware/mapping_engine.py` | Flavor matching (weighted Euclidean distance: cpu=0.4, ram=0.4, disk=0.2), network matching (exact → case-insensitive), disk mapping |
| | `app/services/vmware/compatibility.py` | OS/CPU/memory/disk/network compatibility checks, known OS prefix catalog |
| | `app/services/vmware/plan_service.py` | Migration plan generation with priority sorting, step-by-step workflow |
| **Endpoints** | `app/api/v1/endpoints/vmware/inventory.py` | GET /vms, GET /vms/{id}, GET /datastores, GET /networks, POST /sync |
| | `app/api/v1/endpoints/vmware/assessment.py` | POST /assess, POST /assess/{id}/compatibility, POST /assess/{id}/mapping, POST /plan |
| **Integration** | `app/api/router.py` | vmware namespace registration |
| | `app/api/deps/services.py` | VMware factory + 4 service dependency providers |
| | `app/common/metrics/custom.py` | 4 Prometheus metrics (assessment counter, plan counter, sync duration, inventory gauge) |

### Key Design Decisions

1. **Assessment != Migration**: Phase 4 explicitly excludes `execute_vmware_migration` — the existing `MigrationManager` in `app/modules/migration/manager.py` remains untouched
2. **ResourceSnapshot reuse**: VMware inventory snapshots are stored via the existing `ResourceSnapshot` model (`resource_type`: `vmware_vm`, `vmware_datastore`, `vmware_network`)
3. **Flavor matching**: Weighted Euclidean distance with underprovision penalty (1.5x), normalized to 0-1 score
4. **In-memory cache**: TTLCache (5min TTL) for VMware inventory endpoints; DB snapshots for persistence across restarts
5. **Async DB writes**: Inventory sync uses `asyncio.create_task` for non-blocking snapshot upsert

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/vmware/vms` | List all VMs |
| GET | `/api/v1/vmware/vms/{id}` | Get VM detail |
| GET | `/api/v1/vmware/datastores` | List all datastores |
| GET | `/api/v1/vmware/networks` | List all networks |
| POST | `/api/v1/vmware/sync` | Sync inventory to DB |
| POST | `/api/v1/vmware/assess` | Assess multiple VMs |
| POST | `/api/v1/vmware/assess/{id}/compatibility` | Single VM compatibility |
| POST | `/api/v1/vmware/assess/{id}/mapping` | Single VM resource mapping |
| POST | `/api/v1/vmware/plan` | Generate migration plan |

### Out of Scope (explicitly excluded per roadmap)
- GPU Telemetry, GPU Observability, Grafana Dashboard
- DCIM integration
- Multi-region orchestration
- Unified portal UI
- Actual VM disk export / Glance upload / server create

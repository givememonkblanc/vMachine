# API Reference

> vMachine API endpoint classification and reference.
> All endpoints are under the `/api/v1` prefix unless otherwise noted.

---

## Classification Legend

| Badge | Meaning |
|-------|---------|
| ✅ **Stable** | Production-ready, validated, breaking changes avoided |
| 🔧 **Internal** | Used by the platform internals, may change without notice |
| 🧪 **Experimental** | Incomplete, may be removed or redesigned |
| 🔒 **Auth Required** | X-API-Key header must match configured `API_KEY` |

---

## Core

### Health

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/health` | ✅ Stable | Application health check |

### Audit

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/audit` | ✅ Stable | Query audit log entries (filterable by resource_type, status) |

---

## Identity

### Auth

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/auth/info` | ✅ Stable | OpenStack connection configuration info |
| GET | `/auth/validate` | ✅ Stable | Validate OpenStack credentials |
| GET | `/auth/catalog` | ✅ Stable | OpenStack service catalog |

### Tenants

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/tenants` | ✅ Stable | List OpenStack projects |
| POST | `/tenants` | ✅ Stable | Create OpenStack project |
| GET | `/tenants/{id}` | ✅ Stable | Get tenant detail |
| PUT | `/tenants/{id}` | ✅ Stable | Update tenant |
| DELETE | `/tenants/{id}` | ✅ Stable | Delete tenant |

---

## OpenStack Infrastructure

### Compute (Nova)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/compute/servers` | ✅ Stable | List all Nova servers |
| GET | `/compute/servers/{id}` | ✅ Stable | Get server detail |
| POST | `/compute/servers` | ✅ Stable | Create server |
| DELETE | `/compute/servers/{id}` | ✅ Stable | Delete server |
| POST | `/compute/servers/{id}/action` | ✅ Stable | Server action (start/stop/reboot) |

### Flavors

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/flavors` | ✅ Stable | List OpenStack flavors |
| GET | `/flavors/{id}` | ✅ Stable | Get flavor detail |
| POST | `/flavors` | ✅ Stable | Create flavor |
| DELETE | `/flavors/{id}` | ✅ Stable | Delete flavor |

### Images (Glance)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/images` | ✅ Stable | List OpenStack images |
| GET | `/images/{id}` | ✅ Stable | Get image detail |
| POST | `/images` | ✅ Stable | Upload image |
| DELETE | `/images/{id}` | ✅ Stable | Delete image |

### Keypairs

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/keypairs` | ✅ Stable | List keypairs |
| POST | `/keypairs` | ✅ Stable | Create keypair |
| DELETE | `/keypairs/{id}` | ✅ Stable | Delete keypair |

### Networks (Neutron)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/networks` | ✅ Stable | List networks |
| GET | `/networks/{id}` | ✅ Stable | Get network detail |
| POST | `/networks` | ✅ Stable | Create network |
| DELETE | `/networks/{id}` | ✅ Stable | Delete network |

### Routers

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/routers` | ✅ Stable | List routers |
| POST | `/routers` | ✅ Stable | Create router |
| POST | `/routers/{id}/add-interface` | ✅ Stable | Add interface to router |
| POST | `/routers/{id}/remove-interface` | ✅ Stable | Remove interface from router |
| DELETE | `/routers/{id}` | ✅ Stable | Delete router |

### Security Groups

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/security-groups` | ✅ Stable | List security groups |
| GET | `/security-groups/{id}` | ✅ Stable | Get security group detail |
| POST | `/security-groups` | ✅ Stable | Create security group |
| POST | `/security-groups/{id}/rules` | ✅ Stable | Add rule to security group |
| DELETE | `/security-groups/{id}` | ✅ Stable | Delete security group |

### Storage (Cinder)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/volumes` | ✅ Stable | List volumes |
| GET | `/volumes/{id}` | ✅ Stable | Get volume detail |
| POST | `/volumes` | ✅ Stable | Create volume |
| DELETE | `/volumes/{id}` | ✅ Stable | Delete volume |
| POST | `/volumes/{id}/attach` | ✅ Stable | Attach volume to server |
| POST | `/volumes/{id}/detach` | ✅ Stable | Detach volume from server |

---

## VM Lifecycle Engine

### Servers (Nova, Auth Protected)

| Method | Path | Status | Auth | Description |
|--------|------|--------|------|-------------|
| POST | `/openstack/servers` | ✅ Stable | 🔒 | Create VM and wait for ACTIVE |
| GET | `/openstack/servers` | ✅ Stable | 🔒 | List all VMs |
| GET | `/openstack/servers/{id}` | ✅ Stable | 🔒 | Get VM detail |
| POST | `/openstack/servers/{id}/start` | ✅ Stable | 🔒 | Power on VM |
| POST | `/openstack/servers/{id}/stop` | ✅ Stable | 🔒 | Power off VM |
| POST | `/openstack/servers/{id}/reboot` | ✅ Stable | 🔒 | Soft reboot VM |
| DELETE | `/openstack/servers/{id}` | ✅ Stable | 🔒 | Delete VM |
| GET | `/openstack/servers/active/count` | ✅ Stable | 🔒 | Active VM count |

---

## VMware Assessment

### Inventory

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/vmware/vms` | ✅ Stable | List VMware VMs |
| GET | `/vmware/vms/{id}` | ✅ Stable | Get VM detail |
| GET | `/vmware/datastores` | ✅ Stable | List datastores |
| GET | `/vmware/networks` | ✅ Stable | List networks |
| POST | `/vmware/sync` | ✅ Stable | Sync VMware inventory to DB |

### Assessment

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | `/vmware/assess` | ✅ Stable | Assess multiple VMs |
| POST | `/vmware/assess/{id}/compatibility` | ✅ Stable | Single VM compatibility check |
| POST | `/vmware/assess/{id}/mapping` | ✅ Stable | Single VM resource mapping |
| POST | `/vmware/assess/parallel` | ✅ Stable | Parallel assessment of multiple VMs |
| GET | `/vmware/assess/parallel/{task_id}` | ✅ Stable | Get parallel assessment progress |
| POST | `/vmware/plan` | ✅ Stable | Generate migration plan |
| GET | `/vmware/assessments` | ✅ Stable | List persisted assessments |
| GET | `/vmware/assessment/{id}` | ✅ Stable | Get assessment detail + plans |
| GET | `/vmware/plans` | ✅ Stable | List persisted plans |
| GET | `/vmware/plan/{id}` | ✅ Stable | Get plan detail + assessment |

---

## Orchestration

### Clusters

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/clusters` | 🔧 Internal | List clusters |
| POST | `/clusters` | 🔧 Internal | Create cluster |
| GET | `/clusters/{id}` | 🔧 Internal | Get cluster detail |
| DELETE | `/clusters/{id}` | 🔧 Internal | Delete cluster |

### Migrations (Task Tracking Only)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/migrations` | 🔧 Internal | List migration tasks |
| GET | `/migrations/{id}` | 🔧 Internal | Get migration task detail |
| POST | `/migrations` | 🔧 Internal | Create migration task (tracking only — no execution) |
| POST | `/migrations/{id}/progress` | 🔧 Internal | Update migration progress |

> **Note**: The VMware-to-OpenStack migration execution pipeline has been removed.
> These endpoints track migration task state only.

### Operations

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/operations` | 🔧 Internal | List automation operations |
| POST | `/operations` | 🔧 Internal | Create operation |
| GET | `/operations/{id}` | 🔧 Internal | Get operation detail |
| POST | `/operations/{id}/execute` | 🔧 Internal | Execute operation |

---

## Kubernetes

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/k8s/info` | 🧪 Experimental | Cluster info |
| GET | `/k8s/namespaces` | 🧪 Experimental | List namespaces |
| GET | `/k8s/pods` | 🧪 Experimental | List pods |
| POST | `/k8s/deployments` | 🧪 Experimental | Create deployment |
| GET | `/k8s/deployments` | 🧪 Experimental | List deployments |
| DELETE | `/k8s/deployments/{id}` | 🧪 Experimental | Delete deployment |

---

## Monitoring

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/monitoring/metrics` | ✅ Stable | Query stored metrics |
| GET | `/monitoring/alerts` | ✅ Stable | List active alerts |

---

## Endpoint Summary

| Domain | Count | Stable | Internal | Experimental |
|--------|:-----:|:------:|:--------:|:------------:|
| Core | 2 | 2 | 0 | 0 |
| Identity | 7 | 7 | 0 | 0 |
| OpenStack Infra | ~30 | 30 | 0 | 0 |
| VM Lifecycle | 8 | 8 | 0 | 0 |
| VMware Assessment | 12 | 12 | 0 | 0 |
| Orchestration | ~10 | 0 | 10 | 0 |
| Kubernetes | 5 | 0 | 0 | 5 |
| Monitoring | 2 | 2 | 0 | 0 |
| **Total** | **~76** | **61** | **10** | **5** |

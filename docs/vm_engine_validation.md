# VM Engine Validation Report

> Phase 6 — OpenStack VM Lifecycle Validation

## Validation Flow

The validation script (`scripts/validate_vm_engine.py`) executes the following
lifecycle against a real OpenStack deployment:

```
 1. discover_resources  ──→ List flavors, images, networks
 2. create_vm           ──→ Create VM, wait for ACTIVE
 3. vm_reboot           ──→ Reboot active VM
 4. vm_stop             ──→ Stop (power off) VM
 5. vm_start            ──→ Start (power on) VM
 6. delete_vm           ──→ Delete VM
 7. verify_cleanup      ──→ Confirm 404 on deleted VM
```

### What Is Validated

| Aspect | How |
|--------|-----|
| OpenStack connectivity | Engine initializes, resources are listed |
| VM creation | Nova `create_server` + polling to ACTIVE |
| Reboot | Nova `reboot_server` with state=ACTIVE validation |
| Stop | Nova `stop_server` with state=ACTIVE validation |
| Start | Nova `start_server` with state=SHUTOFF validation |
| Deletion | Nova `delete_server` + 404 confirmation |
| State validation | Invalid transitions return 409 |
| Timeout handling | Stuck operations abort with `TimeoutError` |
| Cleanup on failure | Failed VMs are deleted before exit |

### What Is NOT Validated

- VMware migration (see `docs/vmware_migration_architecture.md`)
- Volume attach/detach
- Floating IP allocation
- Security group rule enforcement
- Multi-region provisioning
- UI/portal

---

## How to Run

```bash
# Full validation (auto-selects first flavor/image/network):
PYTHONPATH=. python scripts/validate_vm_engine.py

# With explicit resources:
PYTHONPATH=. python scripts/validate_vm_engine.py \
  --flavor m1.tiny \
  --image cirros-0.6.2 \
  --network private \
  --vm-name my-validation-vm \
  --keypair my-key \
  --security-group default \
  --az nova

# Export JSON results:
PYTHONPATH=. python scripts/validate_vm_engine.py --json
```

### Prerequisites

- OpenStack environment configured (`OPENSTACK_AUTH_URL`, `OPENSTACK_USERNAME`,
  `OPENSTACK_PASSWORD`, `OPENSTACK_PROJECT_NAME`, etc.)
- At least one flavor, image, and network available
- Sufficient quota to create one VM instance

### Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Report | `docs/vm_engine_validation.md` | Human-readable validation report |
| JSON | `benchmark_results/vm_engine_validation.json` | Machine-readable results |

---

## Validation Report Interpretation

When validation passes:

```
✅ ALL PASSED (7/7)
├── ✅ discover_resources       — 3 flavors, 5 images, 2 networks found
├── ✅ create_vm                — vm-xxx status=ACTIVE
├── ✅ vm_reboot                — success (1.2s)
├── ✅ vm_stop                  — success (2.1s)
├── ✅ vm_start                 — success (3.5s)
├── ✅ delete_vm                — success (0.8s)
└── ✅ verify_cleanup           — server no longer exists
```

When validation fails (e.g., no OpenStack configured):

```
❌ FAILED (0/1)
├── ❌ discover_resources       — OpenStack env vars not set
└── (engine not ready — remaining steps skipped)
```

---

## Architecture

```
┌─ validate_vm_engine.py ──────────────────────────────────────────┐
│  CLI args → VMProvisioningEngine → OpenStack Nova                │
│                                                                   │
│  ValidationResult                                                 │
│    ├── steps[]: ValidationStep (name, passed, duration, error)    │
│    ├── all_passed: bool                                           │
│    ├── server_cleaned_up: bool                                    │
│    └── engine_ready: bool                                         │
└───────────────────────────────────────────────────────────────────┘
```

See `docs/openstack_vm_lifecycle.md` for the full engine architecture.

---

*Document generated for Phase 6 — VM Engine Validation*

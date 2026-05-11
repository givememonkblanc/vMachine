# Repository Stabilization Plan

> Classification and action plan for the vMachine repository cleanup phase.
> Created: 2026-05-11

---

## 1. Overview

vMachine has reached a live-validated core state. This plan documents the classification of every file in the repository and the actions needed before SMF integration.

**Current positioning**: vMachine is a Virtual Infrastructure Execution Engine with OpenStack VM Lifecycle, VMware Readiness/Assessment, and SMF backend integration. It is NOT a standalone frontend, full migration execution platform, production cutover orchestrator, GPU orchestration engine, or storage platform.

---

## 2. File Classification

### 2.1 Application Code (`app/`)

| Path | Classification | Action | Rationale |
|------|---------------|--------|-----------|
| `app/api/` | Keep | Review endpoints | Core API layer |
| `app/clients/` | Keep | As-is | Integration clients (OpenStack, VMware, K8s) |
| `app/common/` | Keep | Minor cleanup | Shared utilities, metrics, exceptions |
| `app/core/` | Keep | As-is | Config, logging, auth |
| `app/db/` | Keep | As-is | Database session, models |
| `app/events/` | Keep | As-is | Event handlers |
| `app/models/` | Keep | As-is | ORM models |
| `app/modules/migration/` | **Archive** | Move to `app/modules/archive/migration/` | Implies full migration execution capability. Methods (`export_vm_disk`, `get_vm_by_name`) likely unimplemented in current VMware client. Code is superseded by the assessment engine. Archive for reference. |
| `app/schemas/` | Keep | Minor cleanup | Pydantic schemas |
| `app/services/` | Keep | Review migration service | Core services. `MigrationService` references archived module — needs update. |
| `app/worker.py` | Refactor | Remove migration task references | Arq worker references `MigrationManager` — needs update when module is archived. |

### 2.2 Documentation (`docs/`)

| Path | Size | Classification | Action | Rationale |
|------|------|---------------|--------|-----------|
| `README.md` | — | Keep | Minor update | Product positioning needs alignment with actual migration execution code |
| `docs/architecture.md` | 9.7K | **Archive** | Mark historical | Pre-dates current engine architecture. Replaced by individual component docs. |
| `docs/architecture/heterogeneous-ai-accelerator-platform.md` | 122K | **Archive** | Move to archive/ | AI datacenter reference architecture — outside vMachine scope. |
| `docs/performance_report.md` | 64K | Keep | As-is | Core performance reference updated in last session. |
| `docs/benchmark_interpretation.md` | 23K | Keep | As-is | Core architectural analysis, updated last session. |
| `docs/live_validation_report.md` | 15K | Keep | Already marked superseded | References `live_vm_lifecycle_analysis.md`. |
| `docs/migration_assessment_api.md` | 14K | Keep | Rename? | API docs for assessment endpoints. Useful for SMF integration. |
| `docs/vmware_migration_architecture.md` | 14K | Keep | As-is | Core architecture doc for VMware assessment engine. |
| `docs/migration_readiness_criteria.md` | 11K | Keep | As-is | Defines migration readiness — useful for SMF integration. |
| `docs/final_phase6_analysis.md` | 9.7K | Keep | As-is | Final analysis doc, updated last session. |
| `docs/known_vmware_limitations.md` | 9.2K | Keep | As-is | VMware integration limitations. |
| `docs/observability_analysis.md` | 7.9K | **Archive** | Mark superseded | Superseded by `docs/observability_review.md`. |
| `docs/live_vm_lifecycle_analysis.md` | 6.9K | Keep | As-is | Core live validation artifact. |
| `docs/final_phase5a_summary.md` | 6.8K | **Archive** | Move to archive/ | Stale Phase 5A reference. Content covered in benchmark_interpretation.md. |
| `docs/openstack_vm_lifecycle.md` | 6.7K | Keep | As-is | Core architecture doc for VM lifecycle engine. |
| `docs/scaling_benchmark_report.md` | 6.5K | **Archive** | Move to archive/ | Duplicate of `benchmark_interpretation.md` Section 1. |
| `docs/recovery_benchmark_report.md` | 5.3K | **Archive** | Move to archive/ | Duplicate of `benchmark_interpretation.md` Section 3. |
| `docs/vmware_benchmark_results.md` | 5.2K | **Archive** | Move to archive/ | Superseded by dataset benchmarks and Phase 5B results. |
| `docs/migration_quality_report.md` | 5.2K | **Archive** | Move to archive/ | Duplicate of `benchmark_interpretation.md` Section 4. |
| `docs/connection_lifecycle.md` | 5.1K | Keep | As-is | Created last session — operations doc. |
| `docs/vm_engine_validation.md` | 4.7K | **Archive** | Move to archive/ | Superseded by `openstack_vm_lifecycle.md` + `live_vm_lifecycle_analysis.md`. |
| `docs/security_hardening_report.md` | 4.5K | Keep | As-is | Created last session — operations doc. |
| `docs/phase4_report.md` | 4.4K | **Archive** | Move to archive/ | Stale Phase 4 report. Content covered in performance_report.md. |
| `docs/observability_review.md` | 4.3K | Keep | As-is | Created last session — operations doc. |
| `docs/repository_cleanup_report.md` | 4.2K | **Archive** | Move to archive/ | Previous cleanup report. Superseded by this plan. |
| `docs/dataset_benchmark_report.md` | 4.1K | **Archive** | Move to archive/ | Duplicate of `benchmark_interpretation.md` Section 1.1. |
| `docs/stress_validation_report.md` | 2.3K | **Archive** | Move to archive/ | Duplicate of `benchmark_interpretation.md` Section 3.3. |
| `docs/vm_engine_negative_cases.md` | 1.8K | **Archive** | Move to archive/ | Negative case results. Content covered in validation scripts. |
| `docs/vm_engine_benchmark_report.md` | 967 | **Archive** | Move to archive/ | Stale benchmark report. Content covered in performance_report.md. |
| `docs/repository_stabilization_plan.md` | — | Keep | This file | This plan. |

### 2.3 Scripts (`scripts/`)

| Path | Classification | Action | Rationale |
|------|---------------|--------|-----------|
| `scripts/validate_vm_engine.py` | Keep | As-is | Core live VM lifecycle validation script. |
| `scripts/negative_case_vm_engine.py` | Keep | As-is | State transition + metrics negative case validation. |
| `scripts/benchmark_vm_engine.py` | Keep | As-is | VM engine benchmark harness. |
| `scripts/validate_openstack_mapping.py` | Keep | As-is | OpenStack flavor/network mapping validation. |
| `scripts/validate_vcenter.py` | Keep | As-is | vCenter connectivity validation. |
| `scripts/benchmark_from_dataset.py` | Keep | As-is | Dataset-based benchmark runner. |
| `scripts/benchmark_vmware_assessment.py` | Keep | As-is | Synthetic VMware assessment benchmark. |
| `scripts/concurrency_sweep.py` | Keep | As-is | Concurrency scaling analysis. |
| `scripts/generate_benchmark_inventory.py` | Keep | As-is | Deterministic dataset generator (seed 42). |
| `scripts/recovery_validation.py` | Keep | As-is | Failure scenario validation. |
| `scripts/stress_benchmark_assessment.py` | Keep | As-is | Stress test validation. |
| `scripts/run_dev.sh` | Keep | As-is | Dev startup script. |

### 2.4 Benchmark Data (`benchmark_data/`)

| Path | Classification | Action | Rationale |
|------|---------------|--------|-----------|
| `benchmark_data/openstack_catalog.json` | Keep | As-is | Required by benchmark scripts. |
| `benchmark_data/scenarios/*.json` | Keep | As-is | Required by scenario validation. |
| `benchmark_data/vmware_inventory_*.json` | Keep | As-is | Required by benchmark scripts. **Keep but git-lfs candidates** — some are 6.8MB. |
| `benchmark_data/vmware_inventory_5000.json` | Keep | Add to `.gitignore`? | 6.8MB file. Consider git-lfs or `.gitignore` with generation note. |

### 2.5 Benchmark Results (`benchmark_results/`)

| Path | Classification | Action | Rationale |
|------|---------------|--------|-----------|
| `benchmark_results/vm_engine/live_lifecycle_timing.json` | Keep | As-is | Reference live validation artifact. |
| `benchmark_results/vm_engine/negative_cases.json` | Keep | As-is | Negative case output. |
| `benchmark_results/vm_engine/benchmark.json` | Keep | Move to `vm_engine/` | Already in correct dir. |
| `benchmark_results/vm_engine_validation.json` | **Archive** | Move to `archive/` | Redundant top-level file. |
| `benchmark_results/vmware_assessment.json` | **Archive** | Move to `archive/` | Redundant top-level file. |
| `benchmark_results/dataset_benchmark.json` | Keep | Move to `dataset/` | Should be in dataset directory. |
| `benchmark_results/scaling/concurrency_sweep.json` | Keep | As-is | In correct directory. |
| `benchmark_results/stress/stress_assessment.json` | Keep | As-is | In correct directory. |
| `benchmark_results/validation/recovery_validation.json` | Keep | As-is | In correct directory. |
| `benchmark_results/validation/recovery_validation_report.md` | **Archive** | Move to `archive/` | Redundant doc in results dir. Content in benchmark_interpretation.md. |

### 2.6 Tests (`tests/`)

| Path | Classification | Action | Rationale |
|------|---------------|--------|-----------|
| `tests/unit/` | Keep | As-is | Unit tests. Pre-existing failures documented. |

---

## 3. Execution Plan

### Step 1: Archive obsolete docs
- Create `docs/archive/` directory
- Move 15 docs to archive
- Update consolidated docs with cross-references

### Step 2: Archive migration execution module
- Move `app/modules/migration/` → `app/modules/archive/migration/`
- Update `app/worker.py` to remove migration task references
- Update `app/services/orchestration/migration_service.py` to handle archived module gracefully

### Step 3: Reorganize benchmark results
- Move top-level JSON files into appropriate subdirectories
- Move redundant results to `benchmark_results/archive/`

### Step 4: Update API boundary documentation
- Create/update `docs/api_reference.md`

### Step 5: Metrics review
- Update `docs/observability_review.md`

### Step 6: Code cleanup
- Run `ruff format` and `ruff check --fix`
- Remove stale code references

### Step 7: Final validation
- Run all validation commands
- Create `docs/repository_stabilization_report.md`

### Step 8: Commit

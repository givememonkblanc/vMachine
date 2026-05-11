# vMachine — Virtualization Operations Platform

**VM Lifecycle & Readiness Engine**

vMachine은 OpenStack 기반의 서버 가상화 자원과 Kubernetes 컨테이너 워크로드, VMware 마이그레이션 평가 및 VM 라이프사이클 운영을 통합적으로 관리하기 위한 **Virtualization Operations Platform**입니다. FastAPI 기반의 비동기 처리 구조를 가지고 있으며, 확장성과 모듈화가 용이하도록 설계되었습니다.

> **Product positioning**: vMachine is a **Virtualization Operations Platform** and **VM Lifecycle & Readiness Engine**. It is **not** a full migration execution platform — it provides pre-migration assessment, compatibility validation, and VM lifecycle operations, but does not execute end-to-end disk export/upload/provisioning flows.

**Phase 6 Validation Status: Dry-Run Validated** (see `docs/vm_engine_validation.md`)

| Validation | Status | Details |
|-----------|:------:|---------|
| Static compilation | ✅ Pass | All imports, metrics registry clean |
| API endpoints (8 routes) | ✅ Pass | All `/api/v1/openstack/servers` routes registered |
| Dry-run validation | ✅ Pass (4/4) | Engine construction, payload, state transitions, cleanup plan |
| Negative case + metrics | ✅ Pass (43/43) | State transitions, mapping, helpers, Prometheus metrics |
| Live VM lifecycle (create → ACTIVE → reboot → stop → start → delete → verify) | ⏸️ Skipped | OpenStack endpoint placeholder — configure real `OPENSTACK_AUTH_URL` |
| Benchmark (1 VM, 3 VMs, lifecycle) | ⏸️ Skipped | OpenStack endpoint placeholder — configure real `OPENSTACK_AUTH_URL` |

## 주요 기능 (Core Features)

1. **OpenStack 인프라 관리 (IaaS)**
   - 컴퓨팅 (Nova): 인스턴스(VM) CRUD, 상태 제어, Flavor/Image 관리
   - 네트워크 (Neutron): 네트워크, 서브넷, 라우터, 보안 그룹 관리
   - 스토리지 (Cinder): 볼륨 생성, 삭제, 인스턴스 연결

2. **VM Lifecycle Engine**
   - VM 생성 (create_vm) — async-safe, timeout, structured exceptions
   - VM 전원 제어 (start/stop/reboot) — state transition validation
   - VM 삭제 (delete) — 자동 cleanup 보장
   - Prometheus 메트릭: 생성 지연 시간, 실패율, 라이프사이클 작업 수, 활성 VM 수

3. **컨테이너 워크로드 제어 (K8s)**
   - Kubernetes Pod, Deployment, Service 라이프사이클 관리
   - Deployment 스케일 업/다운
   - 클러스터 노드 및 리소스 모니터링

4. **마이그레이션 준비도 평가 (VMware to OpenStack)**
   - VMware vSphere 인프라(pyvmomi) 연결 및 인벤토리 수집
   - VM 호환성 평가 (규칙 기반, 0.0–1.0 점수)
   - 플레이버/네트워크 매핑 (유클리드 거리 기반)
   - 병렬 평가 (asyncio.Semaphore, 설정 가능한 동시성)
   - 마이그레이션 계획 생성 (우선순위 정렬)

5. **운영 자동화 및 모니터링**
   - AutoScaling 정책 관리
   - 예약 작업(Scheduled Tasks) 스케줄링
   - 메트릭 및 알람(Alerts) 수집 및 대시보드 데이터 제공

6. **비동기 백그라운드 큐 (Arq + Redis)**
   - 무거운 마이그레이션 작업이나 배치 배포 작업 등을 차질 없이 처리하기 위한 Redis 기반의 `arq` 워커 시스템 연동

## 기술 스택 (Tech Stack)

- **Framework**: FastAPI (Python 3.12+)
- **Database**: SQLite (기본값) + aiosqlite, SQLAlchemy (Async)
- **Integrations**: 
  - OpenStack (`openstacksdk`)
  - Kubernetes (`kubernetes`)
  - VMware (`pyvmomi`)
- **Background Queue**: Arq + Redis
- **Testing**: Pytest, Mocking

## 시작하기 (Getting Started)

### 1. 환경 설정

`cp .env.example .env` 명령어를 통해 환경변수를 설정합니다.
주요 환경변수:
- `DATABASE_URL`: DB 접속 정보
- `OPENSTACK_*`: OpenStack 접속 정보 (auth_url, username, password 등)
- `KUBERNETES_KUBECONFIG_PATH`: Kubernetes 설정 파일 경로
- `REDIS_URL`: Redis 접속 정보 (백그라운드 워커 및 캐시 공유)
- `CACHE_BACKEND`: 캐시 백엔드 선택 (`memory` 또는 `redis`, 기본값: `memory`)

  - `memory`: 각 Gunicorn 워커가 독립적인 in-memory TTLCache 사용 (기본값)
  - `redis`: 모든 워커가 Redis를 통해 캐시 공유 (권장, worker 간 cache consistency 보장)

### 2. 패키지 설치

```bash
pip install -r requirements.txt
# 또는 패키지 매니저에 따라 적절히 설치
```

### 3. 데이터베이스 마이그레이션

```bash
alembic upgrade head
```

### 4. 서버 실행

#### 개발 모드 (단일 Uvicorn)
```bash
./scripts/run_dev.sh
# 또는
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 운영 모드 (Gunicorn 8 workers + Nginx)
```bash
# Gunicorn 직접 실행 (port 8002, 8 workers)
gunicorn app.main:app -c gunicorn.conf.py

# Nginx reverse proxy (port 8083)
# Nginx 설정: /etc/nginx/sites-available/vmachine-api
# listen 8083 → proxy_pass → 127.0.0.1:8002

# systemd service (/etc/systemd/system/okastro-backend.service)
sudo systemctl daemon-reload && sudo systemctl restart okastro-backend
```

Worker 수 변경 시 환경변수 설정:
```bash
GUNICORN_WORKERS=4 gunicorn app.main:app -c gunicorn.conf.py
```
Swagger UI는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

### 5. Prometheus Metrics

운영 모드에서는 `/metrics` 엔드포인트에서 Prometheus 메트릭을 제공합니다.

```bash
curl http://localhost:8083/metrics
```

**Gunicorn 다중 프로세스 환경**에서는 `MultiProcessCollector`를 통해 모든 워커의 메트릭을 집계합니다:
- 각 워커는 `/tmp/prometheus_multiproc/`에 메트릭 파일을 기록
- `/metrics` 요청 시 모든 워커의 데이터를 취합하여 반환
- `PID` 레이블로 개별 워커 식별 가능

**주요 메트릭:**

| 메트릭 | 타입 | 설명 |
|--------|------|------|
| `http_requests_total` | Counter | 전체 HTTP 요청 수 (method, status, handler) |
| `http_request_duration_seconds` | Histogram | 핸들러별 요청 지연 시간 |
| `vmachine_worker_count` | Gauge | 활성 Gunicorn 워커 수 |
| `vmachine_cache_hit_ratio` | Gauge | 리소스별 캐시 히트율 |
| `vmachine_openstack_api_duration_seconds` | Histogram | OpenStack SDK 호출 지연 시간 |

### 6. 시스템 아키텍처 (운영)

```
사용자 → Nginx (:8083) → Gunicorn (:8002) → FastAPI Workers (×8)
                              ├── Worker 1 ─┐
                              ├── Worker 2 ─┤
                              ├── …         ├─→ Redis Cache (선택 사항)
                              └── Worker 8 ─┘      └── CACHE_BACKEND=redis (기본: memory)

                     ┌── Memory Cache (per-worker, fallback)
                     │    └── CACHE_BACKEND=memory (각 워커 독립 캐시)
                     │
                     └── Redis Cache (cross-worker, 권장)
                          └── CACHE_BACKEND=redis (모든 워커 공유 캐시)

Prometheus → /metrics → Nginx → Gunicorn → MultiProcessCollector
```

성능 및 운영에 대한 자세한 내용은 `docs/performance_report.md`를 참고하세요.

### 7. 백그라운드 워커 실행 (선택)

마이그레이션 등 무거운 비동기 처리를 위해 Redis 서버와 워커를 실행해야 합니다.

```bash
arq app.worker.WorkerSettings
```

## Performance Evaluation

This project includes benchmark scripts for evaluating API latency, concurrent request throughput, background worker processing time, and system resource usage.

Benchmark tools are located in the `benchmarks/` directory.

```bash
# API Latency Benchmark (Gunicorn direct)
python benchmarks/api_benchmark.py --base-url http://127.0.0.1:8002

# API Latency Benchmark (via Nginx)
python benchmarks/api_benchmark.py --base-url http://127.0.0.1:8083

# Locust Load Testing (Concurrency)
locust -f benchmarks/load_test_locust.py --host http://127.0.0.1:8083

# System Resource Monitoring
python benchmarks/system_monitor.py --duration 300
```

### Architecture Performance Evolution

| Phase | Deployment | Workers | Cache | Status |
|-------|-----------|---------|-------|--------|
| Baseline | Single Uvicorn (:8000) | 1 | In-memory (per-worker) | Legacy |
| Phase 0 | Gunicorn + Nginx (:8083→:8002) | **8** (recommended) | In-memory (per-worker) | ✅ Active |
| Phase 1 | Prometheus /metrics | 8 | In-memory (per-worker) | ✅ Active |
| Phase 2 | Redis Distributed Cache | 8 | **Redis (cross-worker)** | ✅ **Active** |

### Worker Count Recommendation

Benchmarked 4, 8, and 16 workers. **8 workers recommended** for this server:

| Factor | Value | Assessment |
|--------|-------|------------|
| CPU cores | 32 | 8 workers = 4 cores/worker — ample for I/O-bound ASGI |
| Memory (8 workers) | ~680 MB (2.1% of 31 GB) | Negligible overhead |
| Cache efficiency | Fewer workers = warmer caches | Each worker handles more requests vs 16 workers |
| OpenStack throttling | Remote API is bottleneck | 8 concurrent clients sufficient |
| Headroom | Leaves room for Redis + PostgreSQL | Non-disruptive future upgrades |
| Success rate | 100% at 4/8/16 | All configurations reliable |

Full analysis in `docs/performance_report.md` (Worker Count Analysis section).

Detailed benchmark methodology, bottleneck analysis, and architecture improvements are available in:
`docs/performance_report.md`

## 프로젝트 구조

- `app/api`: 라우터 및 API 엔드포인트
- `app/clients`: 외부 인프라(OpenStack, K8s, VMware) 클라이언트 연결 패키지
- `app/models`: SQLAlchemy ORM 모델
- `app/schemas`: Pydantic 기반 Request/Response 스키마
- `app/services`: 핵심 비즈니스 로직 및 통합
- `app/modules`: 도메인별 매니저 및 비동기 Tasks
- `app/worker.py`: Arq 워커 설정

추가적인 아키텍처 및 상세 문서는 `docs/` 디렉토리를 참고해 주세요.

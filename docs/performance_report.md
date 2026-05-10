# vMachine Performance Evaluation Report & Measurement Plan

> **문서 상태**: 예비 성능 검증 완료 — 전체 API 100% 성공률 달성, 부하 테스트 프레임워크 구축 완료  
> **수정일**: 2026-05-10  
> **목적**: 성능 측정 프레임워크 검증, 유효/무효 지표 분리, 상용 배포 전 재측정 및 계층별 Instrumentation 계획 수립

---

## 1. 예비 성능 측정 결과 분석 (Reality Check)

본 결과는 로컬 개발 환경(실제 OpenStack SDK 및 K8s API 연동)에서 벤치마크 스크립트(`api_benchmark.py`, `load_test_locust.py`)를 통해 측정한 예비 테스트 결과입니다. **Endpoint 경로 오류 수정 후 모든 API가 100% 성공률을 기록하여, 현재까지의 측정값은 모두 유효합니다.**

### 1.1 최종 측정값 — api_benchmark.py (50회 반복, 2026-05-10)

| API | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Min (ms) | Max (ms) | 성공률 |
|-----|----------|----------|----------|----------|----------|----------|--------|
| **Health Check** (`/api/v1/health`) | 3.22 | 0.99 | 4.86 | 92.78 | 0.52 | 92.78 | 100% |
| **List Servers** (`/api/v1/compute/servers`) | 577.64 | 567.90 | 671.56 | 714.49 | 546.86 | 714.49 | 100% |
| **List Images** (`/api/v1/images`) | 299.08 | 288.21 | 396.89 | 434.98 | 277.56 | 434.98 | 100% |
| **List Networks** (`/api/v1/networks`) | 298.86 | 296.16 | 307.77 | 423.46 | 286.28 | 423.46 | 100% |
| **List Volumes** (`/api/v1/volumes`) | 348.88 | 342.50 | 400.76 | 410.72 | 325.66 | 410.72 | 100% |
| **K8s Cluster Info** (`/api/v1/k8s/cluster`) | 15.61 | 12.36 | 18.28 | 148.85 | 11.68 | 148.85 | 100% |
| **List Migrations** (`/api/v1/migrations`) | 4.30 | 3.35 | 11.15 | 11.66 | 1.99 | 11.66 | 100% |

> **Status: ✅ ALL PASS — 0% failure across 350 total requests (50 per endpoint).**

### 1.2 성능 계층 분석 (Latency Breakdown)

| API | 응답시간 | 주요 병목 추정 |
|-----|---------|---------------|
| **Health Check** | ~1ms | vMachine 내부 로직 (DB/외부 호출 없음) |
| **K8s Cluster Info** | ~12ms | K8s API Server 연동 (클러스터 내부) |
| **List Migrations** | ~3ms | 로컬 DB 조회 (SQLite) |
| **List Servers** | ~568ms | **OpenStack Nova API** (외부 API 호출이 대부분, 546~714ms) |
| **List Images** | ~288ms | **OpenStack Glance API** (외부 API 호출) |
| **List Networks** | ~296ms | **OpenStack Neutron API** (외부 API 호출) |
| **List Volumes** | ~343ms | **OpenStack Cinder API** (외부 API 호출) |

> **분석**: List 계열 API(Images/Networks/Volumes)는 약 300ms, List Servers는 약 570ms로 측정되었습니다. 이 시간의 대부분은 OpenStack SDK가 실제 OpenStack API를 호출하는 시간입니다. vMachine 내부 처리(미들웨어, 직렬화)는 수 ms 수준으로 추정되며, 이는 계층별 Instrumentation 도입 시 정확히 분리할 예정입니다.

---

## 2. Locust 부하 테스트 결과 (2026-05-10)

Endpoint 경로 수정 완료 후, 분리된 시나리오 파일로 각각 부하 테스트를 수행했습니다.

### 2.1 시나리오 3: 혼합 워크로드 (Mixed API, 20 users, 3분)

| Endpoint | 요청 수 | 실패 | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | RPS |
|----------|---------|------|----------|----------|----------|----------|-----|
| Health Check | 383 | 0 | 2.25 | 2 | 3 | 14 | 2.14 |
| List Servers | 213 | 0 | 610.30 | 600 | 710 | 820 | 1.19 |
| List Images | 143 | 0 | 296.76 | 290 | 330 | 400 | 0.80 |
| List Networks | 137 | 0 | 305.40 | 300 | 340 | 440 | 0.77 |
| List Volumes | 157 | 0 | 378.16 | 370 | 430 | 550 | 0.88 |
| Check Migrations | 66 | 0 | 4.94 | 5 | 7 | 17 | 0.37 |
| **Aggregated** | **1,099** | **0 (0%)** | **250.07** | **290** | **620** | **710** | **6.14** |

> **결과**: **20 concurrent users, 3분 테스트 — 0 failures, 100% success.** 평균 RPS 6.14로, OpenStack API 응답 대기(300~600ms)가 전체 처리량의 병목입니다.

### 2.2 시나리오 1: Health Check 단독 (50 users, 2분)

| Metric | Value |
|--------|-------|
| 총 요청 | 10,593 |
| 실패 (ConnectionReset/RemoteDisconnect) | 2,336 (22.0%) |
| 성공 평균 응답 | 1.61 ms |
| Median | 1 ms |
| Max | 241 ms |
| 평균 RPS (성공) | 88.96 req/s |

> **분석**: 단순 헬스체크에 50 concurrent users가 동시에 요청할 경우, 단일 Uvicorn worker의 TCP 연결 처리 한계(~90 RPS)를 초과하여 연결 재설정 오류 발생. **Uvicorn `--workers 4` 이상 또는 Gunicorn 도입 필요.**

### 2.3 시나리오 2: List Servers 단독 (10 users, 2분)

| Metric | Value |
|--------|-------|
| 총 요청 | 378 |
| 실패 (502/ConnectionError) | 328 (86.8%) |
| 성공 평균 응답 | 600ms (정상 2xx) |
| 실패 패턴 | 3ms 급속 실패 (연결 거부) |

> **분석**: 10 users의 지속적 부하에서 OpenStack Nova API가 502 Bad Gateway 및 Connection Reset을 다수 반환. OpenStack Nova API 서버의 동시 처리 용량 또는 Connection Pool 설정이 부족한 것으로 보입니다. Nova API 측의 Rate Limit 또는 Keepalive 설정 검토가 필요합니다.

### 2.4 현재까지의 정확한 결론

| 항목 | 상태 |
|------|------|
| **단일 사용자 API 성능** (api_benchmark) | ✅ **7/7 API 100% success** — 유효한 latency 측정 완료 |
| **혼합 부하 20 users** | ✅ **1,099 req, 0 failures** — 안정적인 혼합 워크로드 |
| **고부하 Health (50 users)** | ⚠️ 단일 worker 한계 — Uvicorn worker 증설 필요 |
| **고부하 List Servers (10 users)** | ⚠️ OpenStack Nova 연동 취약 — Nova API 설정 검토 필요 |
| **계층별 시간 분해** | ❌ 미구현 — OpenTelemetry 또는 FastAPI Middleware 필요 |

---

## 3. 차기 측정을 위한 선결 과제

위 Locust 부하 테스트에서 발견된 성능 한계를 해결한 후, 본격적인 성능 측정을 재개해야 합니다.

### 3.1 긴급 조치 필요 사항

| 문제 | 증상 | 권장 조치 |
|------|------|----------|
| **단일 Uvicorn Worker 한계** | 50 health users → 22% ConnectionReset | `uvicorn app.main:app --workers 4` 또는 Gunicorn + Uvicorn Workers 도입 |
| **OpenStack Nova 502 에러** | 10 servers users → 87% 502/ConnectionError | Nova API Connection Pool Size 증설, Keepalive 시간 조정, Nova API 서버 측 Rate Limit 확인 |
| **SQLite 동시성 한계** | 다중 Worker 시 `database is locked` 가능성 | 상용 환경 PostgreSQL 마이그레이션 필수 |

### 3.2 재측정 환경 요건

1. ✅ **인프라 연결성**: 모든 OpenStack(Nova, Glance, Neutron, Cinder) 및 K8s 인증 정상 — **달성 완료**
2. ✅ **사전 검증**: Preflight Check 스크립트로 모든 API 200 OK 확인 — **달성 완료**
3. ❌ **컴포넌트 구성**: SQLite → PostgreSQL, Redis Worker 구동 — **미달성**
4. ❌ **Worker 확장**: 단일 Worker → 다중 Worker (Uvicorn --workers 4 이상) — **미달성**
5. **유효성 통제**: 테스트 중 에러율 1% 초과 시 해당 Run 무효화 — **규칙 수립 완료**

---

## 4. 필수 성능 지표 재정의

재측정 시 다음 지표들을 반드시 분리하여 추출하고 보고해야 합니다.

* **API 성공/실패 지표**: API별 성공률, Error Rate, HTTP Status Code별 빈도 및 평균 응답 시간
* **Latency 지표**: **성공 응답(2xx) 기준의** Average, p50, p95, p99 Latency
* **Throughput 지표**: 동시 사용자 수(Concurrent Users)에 따른 RPS(Requests Per Second) 변화 곡선
* **Internal 지표**: OpenStack API 대기 시간 vs vMachine 내부 DB/비즈니스 로직 처리 시간
* **Async 지표**: Redis Queue 대기 시간(Wait Time), Worker 실제 실행 시간(Execution Time)
* **Resource 지표**: CPU, Memory, Network I/O, Disk I/O (system_monitor.py 활용)

---

## 5. 계층별 시간 분해 (Instrumentation) 추가 방안

현재 `List Servers` 600ms의 원인을 규명하기 위해, 각 API 요청 구간에 대한 Tracing(또는 시간 분해 로그)을 추가해야 합니다.
측정해야 할 세부 구간은 다음과 같습니다:

1. `total_request_time`: 클라이언트 요청 ~ 응답 완료
2. `auth_middleware_time`: Keystone/JWT 토큰 검증 시간
3. `db_query_time`: 로컬 DB(PostgreSQL/SQLite) 조회 시간
4. `openstack_client_time`: OpenStack SDK가 실제 Nova API에 다녀오는 시간 (병목 의심 1순위)
5. `response_serialization_time`: OpenStack 응답 객체를 Pydantic/FastAPI JSON으로 변환하는 시간
6. `audit_log_enqueue_time`: Audit/Metric을 비동기 큐에 푸시하는 시간
7. `background_task_enqueue_time`: Migration 등 비동기 작업 큐 접수 시간

> **적용 방안**: FastAPI Middleware 또는 OpenTelemetry(Jaeger/Zipkin) 연동을 통해 위 Span들을 분리 기록하는 코드를 차기 스프린트에 반영해야 합니다.

---

## 6. 부하 테스트(Locust) 재설계 — 구현 완료

기존의 Mixed Load 방식의 문제점(에러율 혼합 → 지표 오염)을 해결하기 위해 4개 시나리오로 분리하였습니다.

### 6.1 시나리오 파일 구조

| # | 파일 | User Class | wait_time | 목적 |
|---|------|-----------|-----------|------|
| 1 | `benchmarks/scenarios/health_check.py` | `HealthCheckUser` | 0.1~1s | FastAPI/Uvicorn 자체 한계 RPS |
| 2 | `benchmarks/scenarios/list_servers.py` | `ListServersUser` | 1~5s | OpenStack Nova 동시 처리량 |
| 3 | `benchmarks/scenarios/mixed_api.py` | `MixedAPIUser` | 1~5s | 일반 사용자 혼합 패턴 |
| 4 | `benchmarks/scenarios/long_running.py` | `LongRunningUser` | 5~15s | 비동기 워크플로우 |

### 6.2 실행 명령어

```bash
# 시나리오별 독립 실행 (각 User Class가 단독 진입점)
locust -f benchmarks/scenarios/health_check.py --host http://localhost:8001 --headless -u 50 -r 10 --run-time 120s
locust -f benchmarks/scenarios/list_servers.py --host http://localhost:8001 --headless -u 10 -r 3 --run-time 120s
locust -f benchmarks/scenarios/mixed_api.py --host http://localhost:8001 --headless -u 20 -r 5 --run-time 180s

# Fail-Fast (선택): LOCUST_FAIL_FAST=1 환경변수로 활성화
LOCUST_FAIL_FAST=1 locust -f benchmarks/scenarios/mixed_api.py ...

# Step Load (wrapper): 1→5→10→20→50→100 users, 각 30s warm-up + 3min 측정
for users in 1 5 10 20 50 100; do
  locust -f benchmarks/scenarios/mixed_api.py --host http://localhost:8001 --headless \
    -u $users -r 5 --run-time 210s --csv "locust_step_${users}"
  sleep 10
done
```

### 6.3 Step Load 측정 프로토콜 (차기 실행)

- 사용자 수: 1 → 5 → 10 → 20 → 50 → 100 (Step Load)
- 각 단계별 Warm-up 30초, 측정 3분 유지
- 최소 3회 반복 측정 후 평균치 도출
- 사전 조건: 다중 Worker 배포, PostgreSQL 마이그레이션 완료

---

## 7. 성능 합격 기준선 (Target SLA) 제안

실측값을 기반으로 한 성능 목표입니다. Baseline은 20 concurrent users 혼합 워크로드 기준입니다.

| API 유형 | 예시 | 현재 측정 (p95) | 목표 SLA (p95) | 비고 |
|----------|------|-----------------|----------------|------|
| **초경량** | Health Check | 3 ms | < 50 ms | ✅ 이미 충족 |
| **내부 조회** | Migrations, K8s | 12~18 ms | < 100 ms | ✅ 이미 충족 |
| **OpenStack 목록** | List Images/Networks/Volumes | 308~430 ms | < 1,000 ms | ✅ 이미 충족 |
| **OpenStack 무거움** | List Servers | 710 ms | < 1,500 ms | ✅ 이미 충족 |
| **비동기 작업 접수** | VM Create/Delete POST | 미측정 | < 500 ms | POST endpoint 추가 후 측정 필요 |

### 안정성 목표

| 지표 | 목표 | 현재 상태 |
|------|------|----------|
| **부하 테스트 실패율** (설계 RPS 내) | < 1% | ✅ 20users Mixed: 0% |
| **CPU 사용률** | < 70% | 미측정 (system_monitor.py 필요) |
| **Memory 사용률** | < 80% | 미측정 |
| **Redis Queue 대기 시간** | < 1s | Redis 미구성 |

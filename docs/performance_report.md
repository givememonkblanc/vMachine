# vMachine Performance Evaluation Report & Measurement Plan

> **문서 상태**: 예비 성능 검증 및 재측정 계획 (Draft)  
> **수정일**: 2026-05-10  
> **목적**: 성능 측정 프레임워크 검증, 유효/무효 지표 분리, 상용 배포 전 재측정 및 계층별 Instrumentation 계획 수립

---

## 1. 예비 성능 측정 결과 분석 (Reality Check)

본 결과는 로컬 개발 환경(Mock 환경 일부 포함)에서 벤치마크 스크립트(`api_benchmark.py`, `load_test_locust.py`)의 동작을 검증하기 위해 수행된 예비 테스트입니다. 성능공학 관점에서 유효한 측정값과 환경 구성 누락으로 인한 무효(Error) 측정값을 엄격히 분리합니다.

### 1.1 유효 측정값 (성공률 100%)

다음 API는 내부 의존성 또는 연동된 Mock/로컬 환경을 통해 정상적인 HTTP 2xx 응답을 반환한 **유효한 성능 지표**입니다.

| API | 평균 응답시간 | p50 | p95 | p99 | 성공률 | 비고 |
|-----|---------------|-----|-----|-----|--------|------|
| **Health Check** (`/api/v1/health`) | 2.26 ms | 2.07 ms | 6.50 ms | 11.25 ms | 100% | 내부 로직 전용 |
| **List Servers** (`/api/v1/compute/servers`) | 597.90 ms | 565.65 ms | 929.93 ms | 1145.35 ms | 100% | OpenStack SDK 통신 |

> **분석**: `List Servers`의 약 600ms 응답 속도는 측정값 자체는 유효하나, 이 시간이 vMachine 내부 병목인지 타겟 OpenStack Nova API의 지연인지 분리되지 않은 통합 지표입니다. (재측정 계획의 '계층별 시간 분해' 참고)

### 1.2 무효 측정값 (오류 응답 시간)

다음 API는 인증 실패(401), 리소스 없음(404), 내부 오류(500) 등으로 인해 정상적인 비즈니스 로직을 수행하지 못하고 Early Return된 결과입니다. **이를 성능 수치로 해석해서는 안 됩니다.**

| API | 평균 **오류 반환** 시간 | HTTP Status | 실패율 | 원인 |
|-----|-------------------------|-------------|--------|------|
| **List Images** | 1.19 ms | 4xx/5xx | 100% | 인증/엔드포인트 설정 누락 |
| **List Networks** | 0.70 ms | 4xx/5xx | 100% | 인증/엔드포인트 설정 누락 |
| **List Volumes** | 2.99 ms | 4xx/5xx | 100% | 인증/엔드포인트 설정 누락 |
| **K8s Clusters** | 0.73 ms | 4xx/5xx | 100% | Kubeconfig 파일 부재 |
| **VMware Migrations** | 2.00 ms (Locust) | 404 Not Found | 100% | 경로/설정 불일치 |

> **분석**: 실패율 48.15%가 기록된 기존 Locust 부하 테스트 결과는 성능 결론에서 제외하며, "환경 미구성 상태의 무효 부하 테스트"로 분류합니다. 에러 응답(1~3ms)이 전체 평균 응답 시간을 인위적으로 낮춰(123ms) 마치 백엔드 성능이 우수한 것처럼 보이게 하는 통계적 착시를 유발했습니다.

---

## 2. 성능 결론 수정 및 삭제 대상 표현

이전 보고서에서 사용된 다음 표현들은 비교군(Baseline) 부재 및 분해 지표 부족으로 인해 **신뢰할 수 없으므로 모두 삭제/수정**되었습니다.

* ❌ "백엔드 병목 없음" → **수정**: "현재 지표로는 내부 병목과 외부 API 지연의 분리 판단 불가"
* ❌ "안정적으로 방어" → **수정**: "Error 반환이 섞여 통계적 유효성 없음"
* ❌ "원활히 요청을 소화" → **수정**: "단순 HTTP 에러 응답 처리는 경량화되어 있음"
* ❌ "Connection Pooling 효과 확인" → **수정**: "Before/After 대조군 테스트 진행 전까지 효과 입증 유보"

**현재의 정확한 결론**: 
- 현재 로컬 측정은 일부 API(`Health Check`, `List Servers`)만 유효한 벤치마크 프레임워크 검증 단계입니다.
- OpenStack/K8s 인증 실패로 다수 API의 측정은 무효입니다.
- 향후 실제 타겟 환경에서 성공률 99% 이상을 달성한 뒤 재측정해야 최종 SLA(Service Level Agreement) 산정이 가능합니다.

---

## 3. 재측정 기준 및 환경 요건

차기 성능 측정은 다음 조건이 모두 충족된 상태에서 수행해야 합니다.

1. **인프라 연결성**: 실제 OpenStack(Nova, Glance, Neutron, Cinder) 및 K8s 인증 정보 정상 주입.
2. **사전 검증(Health Check)**: 부하 테스트 시작 전 모든 대상 API 단일 호출 시 200 OK (성공률 100%) 확인.
3. **컴포넌트 구성**: SQLite 대신 상용 기준의 PostgreSQL 사용, Redis 기반 백그라운드 Worker 정상 구동 상태.
4. **유효성 통제**: 테스트 중 에러율이 1%를 초과할 경우 해당 테스트 Run은 무효화하고 원인 파악 후 재수행.

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

## 6. 부하 테스트(Locust) 재설계안

기존의 Mixed Load 방식은 에러율이 섞이면 지표가 오염됩니다. 차기 Locust 스크립트는 다음 시나리오별로 분리하여 실행합니다.

1. **Fail-Fast 로직**: 실패 응답(4xx/5xx) 발생 시 로깅 후 테스트 중단 처리 (옵션화)
2. **시나리오 1: 순수 백엔드 부하 (Health Check 단독)**
   - 목표: vMachine 자체 웹서버(Uvicorn/FastAPI)의 한계 RPS 파악.
3. **시나리오 2: 외부 의존성 부하 (List Servers 단독)**
   - 목표: OpenStack API + Connection Pool의 한계 동시 처리량 파악.
4. **시나리오 3: 혼합 워크로드 (Mixed API)**
   - 목표: 조회/상태 확인 등 일반적인 유저 사용 패턴 시뮬레이션 (모든 API 200 OK 보장 하에).
5. **시나리오 4: Long-running 비동기 작업**
   - 목표: VM 생성/삭제, Migration 요청 접수 속도와 Worker의 비동기 완료 시간 측정 (Polling 방식).

**측정 단계**:
- 사용자 수: 1명 → 5명 → 10명 → 20명 → 50명 → 100명 (Step Load)
- 각 단계별 Warm-up 30초, 측정 3분 유지. 최소 3회 반복 측정 후 평균치 도출.

---

## 7. 성능 합격 기준선 (Target SLA) 제안

상용 배포 전 다음의 성능 기준(SLA)을 달성하는 것을 목표로 합니다.

* **초경량 API (Health Check 등)**: p95 < 50ms
* **단순 캐시 API (DB Select Only)**: p95 < 100ms
* **OpenStack 목록/상세 조회 API (List/Get)**: p95 < 1,000ms
* **비동기 작업 접수 API (VM Create/Delete, Migration POST)**: p95 < 500ms
* **비동기 작업 실제 완료 시간**: 별도 Worker 메트릭으로 평가 (요청 대비 지연 추적)
* **안정성**: 
  - 부하 테스트(최대 설계 RPS 내) 실패율 < 1%
  - CPU 사용률 < 70%, Memory 사용률 < 80% (OOM 방지)
  - Redis Queue 대기 시간 < 1s (워커 스케일아웃 기준)

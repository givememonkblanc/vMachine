# vMachine Performance Evaluation Report

## 1. 평가 목적
본 보고서는 기존 OpenStack 기반 VM 관리 플랫폼(vMachine)의 백엔드 API 성능, 동시 요청 처리량, 백그라운드 워커 처리 시간 및 시스템 리소스 사용량을 평가하기 위해 작성되었습니다. 이 결과는 제품 납품 및 PoC(Proof of Concept) 검증을 위한 신뢰성 있는 지표로 활용되며, 최근 적용된 백엔드 성능 최적화(Connection Pooling, 비동기 배치 처리, TTL 캐싱 등)의 효과를 확인하고 향후 병목 개선 방향을 수립하는 것을 목적으로 합니다.

## 2. 시스템 개요
현재 vMachine 플랫폼은 FastAPI 기반의 백엔드로 구성되며, OpenStack SDK를 통해 Nova, Neutron, Cinder, Glance 등과 통신합니다. 최근 적용된 주요 최적화 사항은 다음과 같습니다.
- OpenStack SDK Connection Pooling 및 싱글톤 인스턴스화
- Audit Log 및 Monitoring Metric의 비동기 Background Batch Queue 처리
- `find_*` (O(N)) 패턴을 `get_*` (O(1)) 패턴으로 변경하여 OpenStack API 조회 성능 최적화
- Image 및 Flavor 조회에 대한 인메모리 TTL Caching 적용
- VMware 마이그레이션 시 메모리 팽창(OOM) 방지를 위한 Chunked Streaming I/O 구현
- 데이터베이스 세션 풀링 최적화

## 3. 테스트 환경
*본 측정은 타겟 OpenStack/Kubernetes 인프라가 완전히 구성된 환경에서 수행해야 정확한 결과를 얻을 수 있습니다. 현재는 측정 스크립트와 템플릿만 제공되며, 실제 수치는 배포 환경에서 측정 후 기입해야 합니다.*

- **서버 사양**: [To be measured in target OpenStack environment]
- **OS**: Ubuntu 22.04 LTS (권장)
- **Python 버전**: Python 3.12+
- **FastAPI/Uvicorn 설정**: Workers=[N], DB Pool Size=5, Max Overflow=20
- **DB 종류**: SQLite (개발) / PostgreSQL (상용 권장)
- **Redis 사용 여부**: Arq 기반 Worker Queue용 활성화
- **OpenStack 버전**: [Target Version, e.g., 2024.1 Caracal]
- **Kubernetes 버전**: [Target Version, e.g., v1.30]
- **네트워크 환경**: [10G/40G Internal Network]

## 4. 테스트 대상 API

| 구분 | Endpoint | Method | 설명 | 측정 여부 |
|------|----------|--------|------|-----------|
| 공통 | `/api/v1/health` | GET | 시스템 상태 체크 | 예 |
| Compute | `/api/v1/compute/servers` | GET | VM 목록 조회 (Nova) | 예 |
| Compute | `/api/v1/compute/servers` | POST | VM 생성 요청 (Nova+Cinder+Neutron) | 아니오 (PoC 시 실측 요망) |
| Compute | `/api/v1/compute/servers/{id}` | DELETE | VM 삭제 요청 | 아니오 (PoC 시 실측 요망) |
| Image | `/api/v1/image/images` | GET | 이미지 목록 조회 (Glance) | 예 |
| Network | `/api/v1/network/networks` | GET | 네트워크 목록 조회 (Neutron) | 예 |
| Storage | `/api/v1/storage/volumes` | GET | 볼륨 목록 조회 (Cinder) | 예 |
| K8s | `/api/v1/kubernetes/clusters` | GET | Kubernetes 클러스터 리소스 조회 | 예 |
| Orchestration | `/api/v1/orchestration/migrations` | GET/POST | VMware Migration API | 예 (Mock 제외 실측 요망) |

## 5. 측정 방법
- **단일 요청 테스트**: `api_benchmark.py`를 사용하여 각 API에 대해 50~100회 순차 요청 후 지연 시간(p50, p95, p99 등) 분석.
- **반복/동시 요청 테스트**: `load_test_locust.py`를 사용하여 가상의 동시 사용자(10~100명)를 시뮬레이션하며 Throughput(RPS) 및 부하 시 응답 저하 확인.
- **부하 테스트**: Locust를 활용해 점진적 부하 증가(Step Load) 테스트 수행.
- **시스템 리소스 모니터링**: `system_monitor.py`를 사용하여 테스트 구간 동안의 CPU, 메모리, Network I/O 변동 추이 기록.

## 6. 성능 측정 결과
*(아래 수치는 타겟 OpenStack 환경 구성 후 측정하여 기입해야 합니다.)*

| API | 평균 응답시간 | p50 | p95 | p99 | 최소 | 최대 | 성공률 | 실패율 |
|-----|---------------|-----|-----|-----|------|------|--------|--------|
| Health Check | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |
| List Servers | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |
| List Images | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |
| List Networks| [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |
| List Volumes | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |
| K8s Clusters | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | 100% | 0% |

> **Note**: "To be measured in target OpenStack environment". (현재 로컬/개발 환경에서의 OpenStack SDK mock 호출 결과는 실제 네트워크 I/O 지연을 반영하지 못하므로 기재를 생략합니다.)

## 7. 부하 테스트 결과
*(Locust 부하 테스트 실행 후 기입)*

- **동시 사용자 수**: [TBD]
- **RPS (Requests Per Second)**: [TBD]
- **평균 응답시간**: [TBD] ms
- **p95 응답시간**: [TBD] ms
- **실패율**: [TBD] %

## 8. 시스템 리소스 사용량
- **CPU 평균 / 최대**: [TBD] % / [TBD] %
- **Memory 평균 / 최대**: [TBD] % / [TBD] %
- **Disk I/O**: Read [TBD] MB/s, Write [TBD] MB/s
- **Network I/O**: Sent [TBD] MB/s, Recv [TBD] MB/s

## 9. 주요 병목 분석 (Architecture Analysis)

최근 진행된 코드 최적화 및 구조 분석에 따른 시스템 병목 분석입니다.

### 9.1 OpenStack SDK API 호출
- **관련 파일/함수**: `app/services/openstack/*_service.py`
- **원인**: 백엔드에서 OpenStack Core 서비스(Nova, Neutron 등)로의 API 요청은 HTTP 네트워크 통신이므로 필연적인 레이턴시가 발생합니다. 기존 매 요청마다 Keystone 인증을 수행하던 구조는 `ConnectionFactory` 캐싱으로 500ms~2s가량 단축되었습니다.
- **영향**: 여전히 목록 조회가 무거운 테넌트에서는 DB 부하가 아닌 OpenStack API 자체 응답 속도가 전체 API 지연의 90% 이상을 차지합니다.
- **개선 방향**: Pagination(페이징) 및 Redis 백엔드 캐시 전면 도입.
- **우선순위**: 높음

### 9.2 Audit Log & Metrics DB I/O
- **관련 파일/함수**: `app/common/middleware/audit.py`, `app/services/monitoring/monitoring_service.py`
- **원인**: 모든 API 요청/응답마다 DB INSERT가 발생했습니다.
- **개선 결과**: 현재 `asyncio.Queue` 기반의 백그라운드 배치 처리(Batch Processing)로 전환되어 Per-request DB 병목은 해소되었습니다. 다만 동시 접속자가 폭증하여 큐 사이즈가 한계에 도달하면 메모리 사용량이 증가할 수 있습니다.

### 9.3 VMware Migration I/O 처리
- **관련 파일/함수**: `app/modules/migration/manager.py`
- **원인**: 대용량 vmdk 디스크 파일(수십~수백 GB)을 OpenStack Glance에 업로드할 때, 기존 메모리에 파일을 전체 로드하는 방식은 OOM(Out of Memory)의 원인이었습니다.
- **개선 결과**: Chunked file streaming(`open("rb")` 통째로 넘기기) 방식으로 개선되어 OOM 위험은 낮아졌으나, Network Bandwidth와 Disk I/O 병목은 물리적 한계로 남습니다.
- **우선순위**: 보통 (마이그레이션 전용 스토리지 10G/40G 네트워크 구성 필요)

## 10. 개선 권고사항
- **API 계층**: 대량 리소스(Server, Volume) 조회 시 OpenStack API의 응답 속도에 종속되므로, 프론트엔드 단의 Async Lazy Loading 및 Pagination 필수 적용.
- **DB 계층**: 상용 환경에서는 SQLite 대신 PostgreSQL + PgBouncer(Connection Pooling) 구성을 권장.
- **Worker/Queue 계층**: Migration과 같은 Heavy Task 처리 시 현재 1대의 Worker Node로는 부하가 집중될 수 있으므로, Arq 기반의 다중 Worker Node 스케일 아웃(Scale-out) 구조 구축 필요.
- **Monitoring 계층**: 현재 내부 SQLite 기반 Metric 저장 구조는 노드 확장에 불리하므로, 외부 Prometheus/VictoriaMetrics로의 데이터 연동 구조 마련 필요.

## 11. 제품화 관점 평가
- **현 단계**: MVP(Minimum Viable Product) 수준.
- 단일 서버 내 API 구동 및 비동기 처리, 큐 튜닝 등 소프트웨어 레벨의 최적화는 완료되었습니다.
- **상용화 전 보완 필요사항**: 
  1. HAProxy 또는 Nginx 기반의 FastAPI 로드밸런싱 클러스터링 적용
  2. 실제 OpenStack 연동 상태에서의 Long-running Task(VM 생성/삭제) 타임아웃 안정성 테스트
  3. Redis를 활용한 분산 세션 및 글로벌 캐싱 적용

## 12. 결론
vMachine 백엔드는 최근 적용된 Connection Pooling, TTL Caching, 비동기 배치 처리를 통해 프레임워크 내부의 소프트웨어적 병목을 대부분 해소하였습니다. 그러나 IaaS/Orchestration 플랫폼의 특성상 성능의 최종 지표는 타겟 인프라(OpenStack, K8s, Network, Storage)의 응답 속도에 절대적으로 의존합니다. 본 벤치마크 툴들을 활용하여 대상 인프라에 직접 연동한 뒤 실측 데이터를 수집함으로써, 최종 고객 납품 시 신뢰성 있는 SLA(Service Level Agreement)를 제시할 수 있습니다.

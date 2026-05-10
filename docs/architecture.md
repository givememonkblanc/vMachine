# OKAstro Backend Architecture & Design

본 문서는 OKAstro 백엔드 프로젝트의 전반적인 시스템 아키텍처와 설계 철학, 주요 도메인 모델 및 인프라 통합 방식에 대해 상세하게 설명합니다.

---

## 1. System Architecture

OKAstro는 클린 아키텍처(Clean Architecture)와 헥사고널 아키텍처(Hexagonal Architecture)의 영향을 받아 계층 간 의존성을 명확하게 분리했습니다.

### 1.1. Directory Layer

- **`app/api/v1/endpoints/` (Presentation Layer)**:
  - FastAPI의 Router 함수들이 위치합니다.
  - HTTP 요청/응답 형식 검증(Pydantic)과 에러 핸들링을 수행하며, 핵심 로직은 `Service` 계층으로 위임합니다.
- **`app/services/` (Application Layer)**:
  - 도메인 비즈니스 로직과 워크플로우를 담당합니다.
  - 여러 Client나 DB 레포지토리를 조합하여 실질적인 로직(CRUD 및 인프라 프로비저닝)을 수행합니다.
- **`app/clients/` (Infrastructure Layer)**:
  - 외부 서비스(OpenStack, Kubernetes, VMware)와의 직접적인 API 통신을 담당하는 Client Factory 클래스들이 존재합니다.
- **`app/modules/` (Domain Orchestration Layer)**:
  - 여러 서비스 간의 복합적인 조율이나 특정 백그라운드 태스크(마이그레이션 매니저 등)를 수행하기 위한 모듈들입니다.
- **`app/models/` & `app/db/` (Data Access Layer)**:
  - 비동기 SQLAlchemy 기반의 ORM 모델과 데이터베이스 세션 관리를 수행합니다.

---

## 2. Core Domain Models

데이터베이스에 저장되는 핵심 리소스 상태 추적 모델들입니다. 외부 IaaS 자원들은 OpenStack/K8s가 Source of Truth를 가지지만, 비동기 작업 및 플랫폼 자체 운영 기능은 OKAstro DB에서 관리합니다.

- **`OperationTask`**: OpenStack 인스턴스 생성, 볼륨 부착 등 API의 즉각적인 반환이 불가능한 장기 실행 작업의 진행 상태를 추적합니다.
- **`MigrationTask`**: 이기종(VMware 등)에서 OpenStack으로 자원을 이동시킬 때의 단계별 진행률(Progress 0~100)과 에러 메시지를 관리합니다.
- **`ClusterDeployment`**: Kubernetes 클러스터나 여러 VM으로 이루어진 클러스터의 일괄 배포 상태를 저장합니다.
- **`MetricRecord` & `AlertRecord`**: 외부 인프라에서 수집된 모니터링 시계열 데이터(Metrics)와 이상 발생 시 생성되는 알람(Alerts) 내역입니다.
- **`AutoScalingPolicy` & `ScheduledTask`**: 플랫폼 내의 자동화 정책(임계치 기반 스케일링, 정해진 시간의 백업 스케줄 등)을 정의합니다.

---

## 3. Infrastructure Integrations

OKAstro의 가장 큰 목적은 다중 클라우드/가상화 인프라를 하나의 API로 통합 제어하는 것입니다.

### 3.1. OpenStack Integration (`app/clients/openstack`)
- `openstacksdk` 라이브러리를 활용합니다.
- `OpenStackConnectionFactory`는 `.env`에 정의된 인증 정보를 바탕으로 Connection 객체를 생성하여 Service Layer에 반환합니다.
- 컴퓨팅(Nova), 네트워크(Neutron), 블록 스토리지(Cinder), 이미지(Glance) API를 전방위적으로 지원합니다.

### 3.2. Kubernetes Integration (`app/clients/kubernetes`)
- 공식 `kubernetes` Python 클라이언트를 활용합니다.
- Pod, Deployment, Service의 조회, 생성, 삭제 및 스케일링을 지원합니다.
- in-cluster 구동 여부 또는 `~/.kube/config` 파일을 파싱하여 클러스터에 접속합니다.

### 3.3. VMware Migration (`app/clients/vmware` & `app/modules/migration`)
- `pyvmomi` (vSphere API) 클라이언트를 활용합니다.
- 사용자가 마이그레이션 작업을 요청하면, `MigrationManager`를 통해 다음 단계를 거칩니다:
  1. VMware 접속 및 원본 VM 확인
  2. 디스크 이미지(VMDK) 추출 (로컬 또는 원격 버퍼)
  3. OpenStack Glance에 추출된 디스크 업로드
  4. Nova를 통한 새 인스턴스 배포
- 이 작업은 매우 오래 걸리므로 `Arq` 백그라운드 큐를 이용해 비동기로 처리됩니다.

---

## 4. Background Job Processing (Arq)

단일 HTTP 요청의 라이프사이클 안에서 처리할 수 없는 무거운 작업은 Redis 기반의 `arq` 큐로 이관됩니다.

- **설정**: `settings.redis_url`을 통해 Redis에 연결됩니다.
- **Worker (`app/worker.py`)**: 큐에서 작업을 꺼내어 수행하는 독립적인 프로세스입니다.
- **사용처 예시**: `execute_vmware_migration_task` 함수는 VMware 마이그레이션의 전 과정을 백그라운드에서 안전하게 수행하며, 수행 중간중간 DB(`MigrationTask`)의 상태와 진행도를 업데이트합니다.

---

## 5. Security & Observability

- **Audit Middleware**: 사용자의 API 요청(경로, 메소드, 본문 등)은 `AuditLog` 테이블에 기록되어 추적 가능하게 합니다.
- **Exception Handling**: 도메인별 전용 예외 클래스(`OpenStackIntegrationException`, `KubernetesIntegrationException` 등)를 두어, 외부 연동 오류 시 클라이언트에게 적절한 503 또는 400 에러를 반환합니다.
- **CORS**: 프론트엔드 연동을 위해 환경 변수로 허용 도메인(`CORS_ORIGINS`)을 설정할 수 있습니다.

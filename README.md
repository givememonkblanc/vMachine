# OKAstro Backend

OKAstro Backend는 OpenStack 기반의 서버 가상화 자원과 Kubernetes 컨테이너 워크로드, VMware 마이그레이션 및 인프라 모니터링을 통합적으로 관리하기 위해 구축된 클라우드 플랫폼 백엔드입니다. FastAPI 기반의 비동기 처리 구조를 가지고 있으며, 확장성과 모듈화가 용이하도록 설계되었습니다.

## 주요 기능 (Core Features)

1. **OpenStack 인프라 관리 (IaaS)**
   - 컴퓨팅 (Nova): 인스턴스(VM) CRUD, 상태 제어, Flavor/Image 관리
   - 네트워크 (Neutron): 네트워크, 서브넷, 라우터, 보안 그룹 관리
   - 스토리지 (Cinder): 볼륨 생성, 삭제, 인스턴스 연결

2. **컨테이너 워크로드 제어 (K8s)**
   - Kubernetes Pod, Deployment, Service 라이프사이클 관리
   - Deployment 스케일 업/다운
   - 클러스터 노드 및 리소스 모니터링

3. **마이그레이션 (VMware to OpenStack)**
   - VMware vSphere 인프라(pyvmomi) 연결
   - VM 디스크 추출 및 OpenStack Glance 업로드
   - Nova를 통한 신규 인스턴스 프로비저닝 (비동기 백그라운드 처리)

4. **운영 자동화 및 모니터링**
   - AutoScaling 정책 관리
   - 예약 작업(Scheduled Tasks) 스케줄링
   - 메트릭 및 알람(Alerts) 수집 및 대시보드 데이터 제공

5. **비동기 백그라운드 큐 (Arq + Redis)**
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
- `REDIS_URL`: 백그라운드 워커를 위한 Redis 접속 정보

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

```bash
./scripts/run_dev.sh
# 또는
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Swagger UI는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

### 5. 백그라운드 워커 실행 (선택)

마이그레이션 등 무거운 비동기 처리를 위해 Redis 서버와 워커를 실행해야 합니다.

```bash
arq app.worker.WorkerSettings
```

## 프로젝트 구조

- `app/api`: 라우터 및 API 엔드포인트
- `app/clients`: 외부 인프라(OpenStack, K8s, VMware) 클라이언트 연결 패키지
- `app/models`: SQLAlchemy ORM 모델
- `app/schemas`: Pydantic 기반 Request/Response 스키마
- `app/services`: 핵심 비즈니스 로직 및 통합
- `app/modules`: 도메인별 매니저 및 비동기 Tasks
- `app/worker.py`: Arq 워커 설정

추가적인 아키텍처 및 상세 문서는 `docs/` 디렉토리를 참고해 주세요.

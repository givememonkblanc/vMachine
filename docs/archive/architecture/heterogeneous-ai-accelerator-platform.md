# 이기종 AI Accelerator Orchestration Platform — 아키텍처 설계 문서

> **버전**: v1.0  
> **작성일**: 2026-05-10  
> **대상 플랫폼**: vMachine / TSFLOW ONE → AI Accelerator Orchestration Platform  
> **기반 오픈소스**: Kubernetes, HAMi, KubeVirt, OpenStack Cyborg/Nova, VFIO, SR-IOV, mdev

---

## Ⅰ. 전체 플랫폼 목표 및 차별성

### 1.1 Vision
기존 vMachine/TSFLOW ONE 플랫폼을 **VM + Container 통합 이기종 AI Accelerator Orchestration Platform**으로 확장한다. 단순한 VM 관리에서 벗어나, **AI Datacenter Operating System** 수준의 제어 평면을 제공한다.

### 1.2 핵심 차별성

| 구분 | 기존 vMachine | 확장 플랫폼 |
|------|-------------|-------------|
| 관리 대상 | VM | VM + Container + Accelerator (GPU/NPU/FPGA) |
| Accelerator | 단순 PCI Passthrough | Fractional, MIG, mdev, SR-IOV, vNPU |
| Scheduling | VM 스케줄링 | Workload-aware + Topology-aware + Memory-aware |
| Vendor 종속 | NVIDIA only | Vendor-neutral (NVIDIA/AMD/Ascend/Habana) |
| Runtime | VM only | VM + Container + AI Runtime (Jupyter/LLM) |
| 제어 평면 | OpenStack | OpenStack + Kubernetes Dual Control Plane + 통합계층 |

### 1.3 목표 기능 매트릭스

```
MVP (3개월)       → NVIDIA GPU Passthrough + HAMi basic + KubeVirt
Phase 2 (6개월)   → AMD ROCm + Ascend NPU + Cyborg 연동 + Fractional GPU
Phase 3 (9개월)   → vNPU abstraction + Multi-vendor scheduling + Telemetry
Phase 4 (12개월)  → AI Datacenter OS + Unified Accelerator API
```

---

## Ⅱ. 기존 vMachine 구조 분석

### 2.1 현재 아키텍처

```
User
  │
  ├── OpenStack Dashboard (Horizon)
  ├── OKAstro Backend API (FastAPI)
  │     └── OpenStack SDK
  └── vMachine CLI
        │
        ▼  ┌─────────────────────┐
            │  OpenStack Nova     │── VM Lifecycle
            │  OpenStack Cinder   │── Block Storage
            │  OpenStack Neutron  │── Networking
            │  OpenStack Glance   │── Images
            └─────────┬───────────┘
                      │
              ┌───────┴───────┐
         ┌────▼────┐   ┌─────▼─────┐
         │ KVM     │   │ Ceph      │
         │ Compute │   │ Storage   │
         └─────────┘   └───────────┘
```

### 2.2 현재 한계

1. **GPU는 단순 PCI Passthrough만 지원** — vGPU, MIG, Fractional allocation 불가
2. **NVIDIA GPU에만 의존** — AMD/NPU/FPGA 대응 없음
3. **VM-only** — Container workload 지원 없음
4. **Accelerator metadata 부재** — 어떤 GPU가 어디에 있는지, 어떤 workload가 running 중인지 추적 불가
5. **No Unified Scheduling** — Nova가 GPU를 리소스로 인식하지 못함 (Cyborg 미연동)
6. **모니터링 부재** — GPU 온도, 메모리, Utilization, Power 추적 없음

---

## Ⅲ. 권장 전체 아키텍처

### 3.1 Logical Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          User / Portal / API                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │    Orchestration     │   │  Unified Scheduler │   │   Telemetry &   │  │
│  │       Layer          │   │       Layer        │   │   Monitoring    │  │
│  │                      │   │                    │   │                  │  │
│  │  ┌─────────────────┐ │   │  ┌──────────────┐  │   │  ┌────────────┐ │  │
│  │  │ VM Orchestrator  │ │   │  │ HAMi         │  │   │  │ Prometheus  │ │  │
│  │  │ (KubeVirt)       │ │   │  │ Scheduler    │  │   │  │ + DCGM     │ │  │
│  │  └─────────────────┘ │   │  │ Extender     │  │   │  └────────────┘ │  │
│  │  ┌─────────────────┐ │   │  └──────────────┘  │   │  ┌────────────┐ │  │
│  │  │ Container Orch.  │ │   │  ┌──────────────┐  │   │  │ AMDCell    │ │  │
│  │  │ (Kubernetes)     │ │   │  │ Volcano      │  │   │  │ Exporter   │ │  │
│  │  └─────────────────┘ │   │  │ Scheduler    │  │   │  └────────────┘ │  │
│  │  ┌─────────────────┐ │   │  └──────────────┘  │   │  ┌────────────┐ │  │
│  │  │ OpenStack        │ │   │  ┌──────────────┐  │   │  │ npu-smi   │ │  │
│  │  │ (Nova+Cyborg)   │ │   │  │ Topology     │  │   │  │ Exporter  │ │  │
│  │  └─────────────────┘ │   │  │ Aware Policy │  │   │  └────────────┘ │  │
│  └─────────────────────┘   └──┴───────────┬──────┘   └──────────────────┘  │
│                                           │                                 │
├───────────────────────────────────────────┼─────────────────────────────────┤
│                                           ▼                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              Accelerator Abstraction Layer (AAL)                       │  │
│  │                                                                        │  │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐  ┌─────────┐ │  │
│  │  │NVIDIA   │  │AMD       │  │Ascend   │  │Intel      │  │vNPU     │ │  │
│  │  │Adapter  │  │ROCm Adap │  │NPU Adap │  │Habana Adap│  │Virtual  │ │  │
│  │  └────┬────┘  └────┬─────┘  └────┬────┘  └─────┬─────┘  └────┬────┘ │  │
│  └───────┼────────────┼─────────────┼─────────────┼─────────────┼──────┘  │
│          ▼            ▼             ▼             ▼             ▼         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Device Plugin Layer                                 │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │ nvidia   │  │ amd      │  │ ascend   │  │ habana   │            │  │
│  │  │ DP       │  │ DP       │  │ DP       │  │ DP       │            │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────┬───────────────────┬──────────────────┐  │
│  │   KVM / Libvirt / QEMU     │   containerd /    │   SR-IOV / VFIO  │  │
│  │   (KubeVirt VMs)           │   runc (Pods)     │   / mdev         │  │
│  └────────────┬───────────────┴─────────┬─────────┴────────┬─────────┘  │
│               ▼                         ▼                  ▼             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     Physical Hardware Layer                           │  │
│  │  ┌──────┐ ┌──────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌────────┐        │  │
│  │  │NVIDIA│ │AMD   │ │Ascend  │ │Intel │ │FPGA  │ │Future  │        │  │
│  │  │GPU   │ │GPU   │ │NPU     │ │Gaudi │ │      │ │NPU     │        │  │
│  │  └──────┘ └──────┘ └────────┘ └──────┘ └──────┘ └────────┘        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Control Plane Dual-Track 구조

```
                    ┌──────────────────────────────────┐
                    │      Unified Control Plane        │
                    │  (OKAstro Orchestrator Operator)  │
                    └──────┬──────────────┬─────────────┘
                           │              │
              ┌────────────▼────┐  ┌──────▼──────────────┐
              │  Track A:       │  │  Track B:            │
              │  Kubernetes     │  │  OpenStack            │
              │  Native         │  │  (Nova + Cyborg)      │
              │                 │  │                       │
              │  - HAMi         │  │  - Nova Compute       │
              │  - KubeVirt     │  │  - Cyborg Agent       │
              │  - Volcano      │  │  - Placement API      │
              │  - Kueue        │  │  - Glance             │
              └────────────────┘  └───────────────────────┘
                           │              │
                           └──────┬───────┘
                                  ▼
                    ┌──────────────────────────┐
                    │    Shared Infrastructure  │
                    │    - Ceph / Rook          │
                    │    - Calico / Cilium      │
                    │    - Prometheus + Grafana │
                    │    - Keycloak / Dex       │
                    └──────────────────────────┘
```

**설계 원칙**: Kubernetes Track이 기본 제어 평면이고, OpenStack Track은 기존 vMachine 사용자와의 호환성을 위해 유지한다. OKAstro Orchestrator Operator가 두 트랙을 통합한다.

---

## Ⅳ. Kubernetes + HAMi 통합 구조

### 4.1 HAMi 아키텍처 개요

HAMi는 다음과 같은 컴포넌트로 구성된다:

```
┌─────────────────────────────────────────────────────────────┐
│                      Kubernetes Master                       │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ kube-sched │  │ HAMi         │  │ HAMi Mutating      │  │
│  │            │  │ Scheduler    │  │ Webhook            │  │
│  │ extender   │◄─┤ Extender     │  │                    │  │
│  │ interface  │  │ (filter/bind)│  │ injects env/volumes│  │
│  └────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│                     Kubernetes Worker                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  HAMi Device Plugin DaemonSet                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │  │
│  │  │ NVIDIA   │ │ AMD      │ │ Ascend   │  ...         │  │
│  │  │ Plugin   │ │ Plugin   │ │ Plugin   │             │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘             │  │
│  │       │            │            │                    │  │
│  │       ▼            ▼            ▼                    │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐                 │  │
│  │  │ HAMi-  │  │ HAMi-  │  │ HAMi-  │                 │  │
│  │  │ Core   │  │ Core   │  │ Core   │                 │  │
│  │  │(LD_PRE │  │(for AMD│  │(Ascend │                 │  │
│  │  │ -load) │  │  etc)  │  │ native)│                 │  │
│  │  └────────┘  └────────┘  └────────┘                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 HAMi Scheduler ConfigMap (실제 CRD 예시)

```yaml
# hami-scheduler-device ConfigMap
# HAMi가 각 노드의 GPU 리소스를 어떻게 인식하고 스케줄링할지 정의
apiVersion: v1
kind: ConfigMap
metadata:
  name: hami-scheduler-device
  namespace: kube-system
data:
  device-config.yaml: |
    nvidia:
      resourceCountName: nvidia.com/gpu
      resourceMemoryName: nvidia.com/gpumem
      resourceMemoryPercentageName: nvidia.com/gpumem-percentage
      resourceCoreName: nvidia.com/gpucores
      resourcePriorityName: nvidia.com/priority
      overwriteEnv: false
      defaultMemory: 0
      defaultCores: 0
      defaultGPUNum: 1
      deviceSplitCount: 10
      deviceMemoryScaling: 1.0
      deviceCoreScaling: 1.0

      # MIG geometry — GPU 모델별 지원 가능한 MIG 프로필
      knownMigGeometries:
        - models: ["A100-SXM4-80GB", "A100-80GB-PCIe"]
          allowedGeometries:
            - name: 1g.10gb
              memory: 10240
              count: 7
            - name: 2g.20gb
              memory: 20480
              count: 3
            - name: 3g.40gb
              memory: 40960
              count: 2
            - name: 7g.79gb
              memory: 80896
              count: 1
        - models: ["H100-PCIe-80GB", "H100-SXM-80GB"]
          allowedGeometries:
            - name: 1g.21gb
              memory: 21504
              count: 4
            - name: 2g.42gb
              memory: 43008
              count: 2
            - name: 3g.63gb
              memory: 64512
              count: 1

      # 노드별 operating mode 설정
      nodeconfig:
        - name: gpu-node-01
          operatingmode: hami-core  # HAMi-core 사용 (LD_PRELOAD 방식)
        - name: gpu-node-02
          operatingmode: mig         # MIG 모드 사용
        - name: gpu-node-03
          operatingmode: mixed       # MIG + hami-core 혼용

    # AMD GPU 설정
    amd:
      resourceCountName: amd.com/gpu
      resourceMemoryName: amd.com/gpumem
      resourceCoreName: amd.com/gpucores

    # Ascend NPU 설정
    ascend:
      resourceCountName: huawei.com/Ascend910
      resourceMemoryName: huawei.com/Ascend910-mem
```

### 4.3 HAMi Pod Scheduling 예시

```yaml
# GPU 1개 전체를 사용하는 Pod
apiVersion: v1
kind: Pod
metadata:
  name: gpu-full-pod
spec:
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.2-base
    resources:
      limits:
        nvidia.com/gpu: 1
---
# GPU 1개 중 3000MB 메모리만 할당받는 Pod (Fractional)
apiVersion: v1
kind: Pod
metadata:
  name: gpu-fractional-pod
spec:
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.2-base
    resources:
      limits:
        nvidia.com/gpu: 1
        nvidia.com/gpumem: 3000    # 3GB 메모리
        nvidia.com/gpucores: 30    # 30% core
---
# MIG 모드 사용 명시
apiVersion: v1
kind: Pod
metadata:
  name: gpu-mig-pod
  annotations:
    nvidia.com/vgpu-mode: "mig"    # hami-core 대신 MIG 사용
spec:
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.2-base
    resources:
      limits:
        nvidia.com/gpu: 1
        nvidia.com/gpumem: 10000   # 10GB MIG slice
---
# Node/GPU binpack scheduling 정책
apiVersion: v1
kind: Pod
metadata:
  name: gpu-binpack-pod
  annotations:
    hami.io/node-scheduler-policy: "binpack"   # 같은 노드에 몰아 배치
    hami.io/gpu-scheduler-policy: "binpack"    # 같은 GPU에 몰아 배치
spec:
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.2-base
    resources:
      limits:
        nvidia.com/gpu: 1
        nvidia.com/gpumem: 2000
---
# 특정 GPU UUID 지정 (디버깅/테스트 용도)
apiVersion: v1
kind: Pod
metadata:
  name: gpu-pinned-pod
  annotations:
    nvidia.com/use-gpuuuid: "GPU-12345678-aaaa-bbbb-cccc-dddd-eeeeeeee"
spec:
  containers:
  - name: gpu-container
    image: nvidia/cuda:12.2-base
    resources:
      limits:
        nvidia.com/gpu: 1
```

### 4.4 HAMi Scheduler Extender 동작 흐름

```
1. Pod 생성 요청
   │
2. HAMi Mutating Webhook이 Pod 가로챔
   ├── resource에 nvidia.com/gpu 등이 있으면
   ├── init container에 hami-core(LD_PRELOAD 라이브러리) 주입
   └── 환경변수, 볼륨 마운트 추가
   │
3. Kube-scheduler가 extender 호출
   ├── Filter 단계:
   │   ├── 노드의 annotation에서 GPU device 정보 읽기
   │   ├── nvidia.com/gpu, gpumem, gpucores 등 requested resource 체크
   │   └── 충분한 GPU를 가진 노드만 반환
   │
   ├── Score 단계:
   │   ├── Binpack 정책: ((request.core + used.core) / allocatable.core
   │   │                   + (request.mem + used.mem) / allocatable.mem) * 10
   │   └── Spread 정책: 위 점수의 역순
   │
   └── Bind 단계:
       ├── 선택된 GPU device를 Pod에 할당
       └── Node annotation 업데이트 (할당된 리소스 차감)
   │
4. Pod가 Worker Node에 배포됨
   ├── HAMi device plugin이 컨테이너의 GPU 접근 제어
   ├── hami-core.so가 LD_PRELOAD로 CUDA API 호출 가로챔
   └── GPU 메모리/코어 사용량 제한 enforced
```

### 4.5 KubeSchedulerConfiguration (HAMi Extender 등록)

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
leaderElection:
  leaderElect: false
profiles:
- schedulerName: default-scheduler
  extenders:
  - urlPrefix: "https://hami-scheduler.kube-system.svc:443"
    filterVerb: filter
    bindVerb: bind
    nodeCacheCapable: true
    weight: 1
    httpTimeout: 30s
    enableHTTPS: true
    tlsConfig:
      insecure: true
    managedResources:
    - name: nvidia.com/gpu
      ignoredByScheduler: true
    - name: amd.com/gpu
      ignoredByScheduler: true
    - name: huawei.com/Ascend910
      ignoredByScheduler: true
```

### 4.6 HAMi Device Plugin DaemonSet 구조

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: hami-device-plugin
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: hami-device-plugin
  template:
    metadata:
      labels:
        app: hami-device-plugin
    spec:
      hostPID: true
      hostNetwork: true
      nodeSelector:
        gpu: "on"                      # GPU 노드에만 배포
      containers:
      - name: hami-device-plugin-nvidia
        image: projecthami/hami-device-plugin:nvidia-latest
        securityContext:
          privileged: true
        volumeMounts:
        - name: device-plugin
          mountPath: /var/lib/kubelet/device-plugins
        - name: sysfs
          mountPath: /sys
        - name: dev
          mountPath: /dev
      - name: hami-device-plugin-amd
        image: projecthami/hami-device-plugin:amd-latest
        securityContext:
          privileged: true
        volumeMounts:
        - name: device-plugin
          mountPath: /var/lib/kubelet/device-plugins
        - name: sysfs
          mountPath: /sys
      volumes:
      - name: device-plugin
        hostPath:
          path: /var/lib/kubelet/device-plugins
      - name: sysfs
        hostPath:
          path: /sys
      - name: dev
        hostPath:
          path: /dev
```

---

## Ⅴ. KubeVirt 기반 VM Accelerator 구조

### 5.1 KubeVirt GPU Passthrough 전체 구성

```
┌─────────────────────────────────────────────────────────────┐
│                    KubeVirt Control Plane                     │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ virt-api   │  │ virt-controller│ │ virt-handler       │  │
│  │            │  │              │  │ (DaemonSet)         │  │
│  └────────────┘  └──────────────┘  └────────┬───────────┘  │
│                                              │              │
└──────────────────────────────────────────────┼──────────────┘
                                               │
┌──────────────────────────────────────────────┼──────────────┐
│                    Worker Node                │              │
│  ┌───────────────────────────────────────────▼───────────┐  │
│  │  virt-handler                                          │  │
│  │  ┌──────────────────┐  ┌──────────────────────────┐   │  │
│  │  │ KubeVirt Device   │  │ mdev Type Manager        │   │  │
│  │  │ Plugin (PCI)      │  │ (자동 mdev 생성/제거)     │   │  │
│  │  └──────────────────┘  └──────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────┐      ┌──────────────────────────────┐ │
│  │ libvirtd         │      │ NVIDIA vGPU Manager           │ │
│  │ + QEMU/KVM       │      │ (nvidia-vgpu-mgr.service)     │ │
│  │                  │      │ or AMD ROCm Driver            │ │
│  │ <domain>         │      │ or Ascend Driver              │ │
│  │   <devices>      │      └──────────────────────────────┘ │
│  │     <hostdev/>   │                                       │
│  │   </devices>     │      ┌──────────────────────────────┐ │
│  │ </domain>        │      │ vfio-pci driver (kernel)      │ │
│  └──────────────────┘      │ + IOMMU groups                │ │
│                            └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 KubeVirt CR 설정 (GPU Passthrough + vGPU)

```yaml
apiVersion: kubevirt.io/v1
kind: KubeVirt
metadata:
  name: kubevirt
  namespace: kubevirt
spec:
  configuration:
    developerConfiguration:
      featureGates:
      - GPU
      - HostDevices
      - DisableMDEVConfiguration   # 외부 device plugin 사용 시
    permittedHostDevices:
      # PCI Passthrough — 전체 GPU를 VM에 직통
      pciHostDevices:
      - externalResourceProvider: true
        pciVendorSelector: "10DE:2236"     # NVIDIA A10 GPU
        resourceName: nvidia.com/A10_PCI
      - externalResourceProvider: true
        pciVendorSelector: "10DE:1EB8"     # NVIDIA T4 GPU
        resourceName: nvidia.com/T4_PCI
      - externalResourceProvider: true
        pciVendorSelector: "1002:73BF"     # AMD MI250 GPU
        resourceName: amd.com/MI250_PCI

      # Mediated Devices (vGPU) — GPU를 쪼개서 여러 VM에 할당
      mediatedDevices:
      - externalResourceProvider: true
        mdevNameSelector: "GRID A10-8Q"    # NVIDIA A10 vGPU 8GB
        resourceName: nvidia.com/A10_8Q
      - externalResourceProvider: true
        mdevNameSelector: "GRID T4-1Q"     # NVIDIA T4 vGPU 1GB
        resourceName: nvidia.com/T4_1Q
      - externalResourceProvider: true
        mdevNameSelector: "GRID T4-2A"     # T4 vGPU 2GB (compute)
        resourceName: nvidia.com/T4_2A

    # 자동 mdev 생성 설정 (KubeVirt 0.40+)
    mediatedDevicesConfiguration:
      mediatedDeviceTypes:
      - nvidia-222    # GRID T4-1Q
      - nvidia-226    # GRID T4-2A
      - nvidia-299    # GRID A10-8Q
      nodeMediatedDeviceTypes:
      - nodeSelector:
          kubernetes.io/hostname: gpu-node-01
        mediatedDeviceTypes:
        - nvidia-299  # A10-8Q only
```

### 5.3 GPU를 가진 VirtualMachineInstance YAML

```yaml
# PCI Passthrough (전체 GPU)
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: vm-gpu-passthrough
spec:
  running: true
  template:
    spec:
      domain:
        cpu:
          cores: 8
          sockets: 1
          threads: 1
        memory:
          guest: 32Gi
        devices:
          disks:
          - disk:
              bus: virtio
            name: rootdisk
          gpus:
          - deviceName: nvidia.com/A10_PCI   # permittedHostDevices에 정의
            name: gpu1
          - deviceName: nvidia.com/T4_PCI
            name: gpu2
      volumes:
      - name: rootdisk
        containerDisk:
          image: quay.io/containerdisks/ubuntu:24.04
---
# vGPU (Fractional GPU - mdev)
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: vm-vgpu-fractional
spec:
  running: true
  template:
    spec:
      domain:
        cpu:
          cores: 4
          memory:
            guest: 16Gi
        devices:
          gpus:
          - deviceName: nvidia.com/A10_8Q    # A10 vGPU 8GB slice
            name: gpu1
      volumes:
      - name: rootdisk
        dataVolume:
          source:
            pvc: ubuntu-base
---
# AMD GPU Passthrough
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: vm-amd-passthrough
spec:
  running: true
  template:
    spec:
      domain:
        cpu:
          cores: 16
          memory:
            guest: 64Gi
        devices:
          gpus:
          - deviceName: amd.com/MI250_PCI
            name: gpu1
```

### 5.4 VFIO-PCI 바인딩 흐름 (Host 노드 초기화)

```bash
# ===== Step 1: IOMMU 활성화 확인 =====
# kernel cmdline: intel_iommu=on iommu=pt
dmesg | grep -i iommu

# ===== Step 2: GPU의 PCI 주소 확인 =====
lspci -nn | grep -i nvidia
# 17:00.0 3D controller [0302]: NVIDIA Corporation GA102GL [A10] [10de:2236] (rev a1)
# 17:00.1 Audio device [0403]: NVIDIA Corporation Device [10de:1aef] (rev a1)

# ===== Step 3: IOMMU Group 확인 (GPU가 격리되어 있는지) =====
find /sys/kernel/iommu_groups/ -type l | grep 17:00

# ===== Step 4: vfio-pci 드라이버 바인딩 =====
# 방법 A: kernel cmdline에 GPU vendor:product ID 지정
# GRUB_CMDLINE_LINUX="... vfio-pci.ids=10de:2236,10de:1aef ..."
#
# 방법 B: runtime driver override
echo "vfio-pci" > /sys/bus/pci/devices/0000:17:00.0/driver_override
echo "0000:17:00.0" > /sys/bus/pci/drivers_probe

# ===== Step 5: VFIO 모듈 initramfs에 포함 =====
# /etc/initramfs-tools/modules 에 다음 추가:
#   vfio
#   vfio_iommu_type1
#   vfio_pci
#   vfio_virqfd

# ===== Step 6: SR-IOV 활성화 (Ampere+ GPU) =====
/usr/lib/nvidia/sriov-manage -e 0000:17:00.0

# ===== Step 7: mdev 생성 (vGPU) =====
# 지원되는 mdev 타입 목록
ls /sys/bus/pci/devices/0000:17:00.0/mdev_supported_types/
# nvidia-299  nvidia-300  nvidia-301 ...

# mdev 생성 (UUID 할당)
echo "4f3b6e47-0baa-4900-b0b1-284c1ecc192f" > \
  /sys/bus/pci/devices/0000:17:00.0/mdev_supported_types/nvidia-299/create

# 생성된 mdev 확인
ls /sys/bus/mdev/devices/
```

### 5.5 NVIDIA GPU Operator + KubeVirt 통합

```bash
# GPU Operator로 KubeVirt GPU Passthrough 자동 구성
helm install --wait --generate-name \
  -n gpu-operator --create-namespace \
  nvidia/gpu-operator \
  --version=v25.10.1 \
  --set sandboxWorkloads.enabled=true

# 노드 레이블로 Workload Type 지정
kubectl label node gpu-node-01 \
  nvidia.com/gpu.workload.config=vm-passthrough

# vGPU Manager 사용 시
helm install --wait --generate-name \
  -n gpu-operator \
  nvidia/gpu-operator \
  --version=v25.10.1 \
  --set sandboxWorkloads.enabled=true \
  --set vgpuManager.enabled=true \
  --set vgpuManager.repository=my.registry/vgpu-manager \
  --set vgpuManager.image=vgpu-manager \
  --set vgpuManager.version=580.82.07

# vGPU config 커스터마이징
cat > vgpu-config.yaml << 'EOF'
version: v1
vgpu-configs:
  custom-A10-config:
    - devices: all
      vgpu-devices:
        "A10-8Q": 2
        "A10-6Q": 2
EOF
kubectl create configmap custom-vgpu-config \
  -n gpu-operator \
  --from-file=config.yaml=vgpu-config.yaml

# 노드에 vGPU config 적용
kubectl label node gpu-node-01 --overwrite \
  nvidia.com/vgpu.config=A10-8Q
```

---

## Ⅵ. OpenStack Cyborg/Nova 연계 구조

### 6.1 Cyborg Architecture 개요

```
                   ┌──────────────┐
                   │  Keystone    │
                   │  Auth        │
                   └──────┬───────┘
                          │
┌──────────┐  ┌──────────┴───────────┐  ┌──────────────┐
│  Nova    │  │      Cyborg API      │  │  Placement   │
│  API     │──┤  POST /v2/accel_req  │──│  API         │
│          │  │  PATCH /v2/accel_req │  │  /resource_  │
│          │  │  GET /v2/device_prof │  │  providers   │
└────┬─────┘  └──────────┬───────────┘  └──────────────┘
     │                   │
     │           ┌───────┴──────────┐
     │           │  Cyborg          │
     └──────────►│  Conductor       │
                 │  (coordinator)   │
                 └───────┬──────────┘
                         │
                 ┌───────▼──────────┐
                 │  Cyborg Agent     │
                 │  (per compute     │
                 │   node)           │
                 └───────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │  Vendor Drivers     │
              │ ┌────┐┌────┐┌────┐ │
              │ │GPU ││FPGA││NPU │ │
              │ └────┘└────┘└────┘ │
              └────────────────────┘
```

### 6.2 Cyborg Resource Model (실제 API Payload)

```json
// Device Profile 예시
// 사용자 요청: "A100 GPU 1개 달린 VM 생성"
GET /v2/device_profiles?name=gpu_a100_1x

Response:
{
  "device_profiles": [
    {
      "name": "gpu_a100_1x",
      "description": "Single A100 GPU for AI training",
      "groups": [
        {
          "resources:resources:CUSTOM_ACCELERATOR_GPU": "1",
          "trait:CUSTOM_GPU_TYPE_A100": "required",
          "trait:CUSTOM_GPU_MEMORY_80GB": "required",
          "num_accelerators": 1
        }
      ],
      "uuid": "dp-uuid-xxxx"
    }
  ]
}
```

```json
// Accelerator Request (ARQ) 생성
POST /v2/accelerator_requests
{
  "device_profile_name": "gpu_a100_1x"
}

Response:
{
  "arqs": [
    {
      "uuid": "arq-uuid-001",
      "device_profile_name": "gpu_a100_1x",
      "device_profile_group_id": 0,
      "state": "Unbound",
      "hostname": null,
      "device_rp_uuid": null,
      "instance_uuid": null,
      "attach_handle_type": null,
      "attach_handle_info": null
    }
  ]
}
```

```json
// ARQ 바인딩 (Nova → Cyborg)
PATCH /v2/accelerator_requests
{
  "arq-uuid-001": {
    "hostname": "compute-01",
    "device_rp_uuid": "rp-uuid-gpu-a100-01",
    "instance_uuid": "instance-uuid-vm-001"
  }
}

// 바인딩 완료 후 ARQ 상태
GET /v2/accelerator_requests?instance=instance-uuid-vm-001

Response:
{
  "arqs": [
    {
      "uuid": "arq-uuid-001",
      "state": "Bound",
      "hostname": "compute-01",
      "device_rp_uuid": "rp-uuid-gpu-a100-01",
      "instance_uuid": "instance-uuid-vm-001",
      "attach_handle_type": "PCI",
      "attach_handle_info": {
        "bus": "17",
        "device": "00",
        "domain": "0000",
        "function": "0"
      }
    }
  ]
}
```

### 6.3 Nova-Cyborg Interaction Flow

```
┌─────────┐    ┌────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│  User   │    │  Nova  │    │ Placement│    │  Cyborg  │    │  Compute   │
│         │    │  API   │    │  API     │    │  API     │    │  Node      │
└────┬────┘    └───┬────┘    └────┬─────┘    └────┬─────┘    └─────┬──────┘
     │             │              │               │                │
     │boot vm with │              │               │                │
     │gpu flavor   │              │               │                │
     │────────────►│              │               │                │
     │             │ GET device   │               │                │
     │             │ profile      │               │                │
     │             │──────────────┼──────────────►│                │
     │             │              │               │                │
     │             │ request      │               │                │
     │             │ spec에 병합  │               │                │
     │             ├──────────────┤               │                │
     │             │ get alloc    │               │                │
     │             │ candidates   │               │                │
     │             │─────────────►│               │                │
     │             │              │  return RPs   │                │
     │             │◄─────────────│               │                │
     │             │              │               │                │
     │             │ POST /v2/    │               │                │
     │             │ accelerator_ │               │                │
     │             │ requests     │               │                │
     │             │──────────────┼──────────────►│                │
     │             │              │  return ARQs  │                │
     │             │◄─────────────┼──────────────│                │
     │             │              │               │                │
     │             │ PATCH /v2/   │               │                │
     │             │ accelerator_ │               │                │
     │             │ requests     │               │                │
     │             │ (bind)       │               │                │
     │             │──────────────┼──────────────►│                │
     │             │              │               │ prepare device │
     │             │              │               │───────────────►│
     │             │              │               │  bind vfio-pci │
     │             │              │               │  create mdev   │
     │             │              │               │◄───────────────│
     │             │              │               │                │
     │             │ GET ARQs     │               │                │
     │             │ (resolved)   │               │                │
     │             │──────────────┼──────────────►│                │
     │             │◄─────────────┼──────────────│                │
     │             │              │               │                │
     │             │ libvirt      │               │                │
     │             │ attach PCI   │               │                │
     │             │──────────────┼──────────────┼────────────────►│
     │             │              │               │                │
     │  VM running │              │               │                │
     │  with GPU   │              │               │                │
     │◄────────────│              │               │                │
```

### 6.4 Cyborg-Nova 하이브리드 구조 (OKAstro 확장)

```yaml
# OKAstro Orchestrator가 Cyborg 호환 ARQ를 KubeVirt CRD로 변환
apiVersion: okastro.io/v1alpha1
kind: AcceleratorClaim
metadata:
  name: gpu-claim-training-01
spec:
  deviceProfile: gpu_a100_1x
  targetType: VM                    # VM 또는 Container
  owner: project-alpha
  # KubeVirt 변환 시 다음 필드로 매핑
  kubevirt:
    deviceName: nvidia.com/A10_PCI
  priority: high
status:
  phase: Bound                     # Unbound / Bound / Released
  arqUUID: arq-uuid-001
  attachHandle:
    type: PCI
    info:
      bus: "17"
      device: "00"
      domain: "0000"
      function: "0"
  instanceUUID: vm-uuid-001
  nodeName: compute-01
```

---

## Ⅶ. Accelerator Virtualization 계층 설계

### 7.1 가상화 전략 매트릭스

| 전략 | NVIDIA GPU | AMD GPU | Ascend NPU | 격리 수준 | 성능 | 사용 사례 |
|------|-----------|---------|------------|----------|------|---------|
| PCI Passthrough | 전체 GPU (≥A100) | 전체 GPU (≥MI250) | 전체 NPU | 100% HW | 100% | 대규모 학습 |
| SR-IOV VF | A30/A100/H100 | MI250/MI300 | - | VF 단위 | ~98% | Multi-tenant |
| mdev (vGPU) | T4/V100/A10 | - | - | mdev 단위 | ~90% | AI 추론/Desktop |
| MIG | A100/H100 | - | - | HW slice | 95-99% | 보안 중요 |
| HAMi-core | 모든 GPU | - | - | 프로세스 수준 | ~85% | Dev/Test |
| AMD MxGPU | - | MI250+ | - | VF 단위 | ~95% | ROCm 워크로드 |
| Time-slicing | 모든 GPU | 모든 GPU | 모든 NPU | 프로세스 수준 | ~50% | 경량 |

### 7.2 가상화 계층 구조

```
                    ┌─────────────────────────────────────────────┐
                    │        Unified Virtualization API           │
                    │  ┌─────────────┬──────────────┬──────────┐  │
                    │  │ PassThrough  │ MediatedDev  │ HAMi     │  │
                    │  │ Manager      │ Manager      │ Manager  │  │
                    │  └──────┬──────┴──────┬───────┴────┬─────┘  │
                    └─────────┼─────────────┼────────────┼────────┘
                              │             │            │
┌─────────────────────────────┼─────────────┼────────────┼────────┐
│  Vendor Adapters            │             │            │        │
│                              ▼             ▼            ▼        │
│  ┌────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ NVIDIA Adapter  │  │ AMD Adapter  │  │ Ascend Adapter     │  │
│  │                  │  │              │  │                    │  │
│  │ vfio-pci binding │  │ vfio-pci     │  │ dev/mmem 접근     │  │
│  │ nvidia-vgpu-mgr │  │ sriov-manage │  │ CANN API 호출     │  │
│  │ sriov-manage    │  │ rocm-smi     │  │ npu-smi 관리      │  │
│  │ nvidia-smi      │  │              │  │                    │  │
│  └────────────────┘  └──────────────┘  └────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 7.3 Linux Kernel 층별 구성

```
┌──────────────────────────────────────────────────────────────┐
│                     User Space                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────────────┐  │
│  │ libvirt     │ │ QEMU        │ │ HAMi-core (LD_PRELOAD) │  │
│  │ mdev plugin │ │ vfio-pci    │ │ CUDA API Intercept     │  │
│  └──────┬──────┘ └──────┬──────┘ └───────────┬────────────┘  │
├─────────┼───────────────┼────────────────────┼────────────────┤
│         │               │                    │  Kernel        │
│  ┌──────▼───────────────▼────────────────────▼──────────────┐ │
│  │                   VFIO / IOMMU API                        │ │
│  │  ┌──────────────────┐  ┌─────────────────────────────┐  │ │
│  │  │ vfio-pci driver   │  │ vfio-mdev driver             │  │ │
│  │  │ (physical dev)    │  │ (mediated device)            │  │ │
│  │  └────────┬─────────┘  └──────────┬──────────────────┘  │ │
│  │           │                       │                      │ │
│  │  ┌────────▼───────────────────────▼──────────────────┐  │ │
│  │  │           IOMMU (Intel VT-d / AMD-Vi)              │  │ │
│  │  └────────────────────────┬──────────────────────────┘  │ │
│  │                           │                              │ │
│  │  ┌────────────────────────▼──────────────────────────┐  │ │
│  │  │              PCI Express Root Complex              │  │ │
│  │  └────────────────────────┬──────────────────────────┘  │ │
│  └───────────────────────────┼──────────────────────────────┘ │
│                              ▼                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  ┌──────┐  ┌──────┐  ┌──────────┐  ┌──────┐           │ │
│  │  │GPU PF│  │GPU VF│  │GPU mdev  │  │NPU   │           │ │
│  │  │(full)│  │(SR-  │  │(vGPU    │  │      │           │ │
│  │  │      │  │IOV)  │  │ slice)  │  │      │           │ │
│  │  └──────┘  └──────┘  └──────────┘  └──────┘           │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 7.4 Fractional Allocation 흐름 (HAMi-core 동작)

```
┌──────────────────────────────────────────────────────────────┐
│  Container 내부: hami-core.so (LD_PRELOAD)                    │
│                                                              │
│  사용자 App (CUDA Program)                                    │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────────────────┐                                    │
│  │  cuMemAlloc()        │──── 할당 요청                        │
│  └────────┬─────────────┘                                    │
│           ▼                                                   │
│  ┌──────────────────────┐                                    │
│  │  hami-core.so        │──── CUDA API 가로챔                 │
│  │  (LD_PRELOAD)        │                                    │
│  │                      │                                    │
│  │  - 메모리 할당 체크   │──── 할당량 이내면 → 실제 CUDA 호출   │
│  │  - Core 사용량 트래킹 │──── 초과 시 → OOM 에러 반환         │
│  │  - GPU 시간 제한     │                                    │
│  └──────────────────────┘                                    │
│                                                              │
│  실제 할당 가능 메모리: 3000MB (설정값)                        │
│  현재 사용: 1200MB                                            │
│  잔여: 1800MB                                                │
└──────────────────────────────────────────────────────────────┘
```

---

## Ⅷ. Unified Accelerator Metadata 구조

### 8.1 Accelerator Metadata JSON Schema

```json
{
  "accelerator": {
    "id": "gpu-node-01-nvidia-0",
    "type": "GPU",
    "vendor": "NVIDIA",
    "model": "A100-SXM4-80GB",
    "architecture": "Ampere",
    "pci_address": "0000:17:00.0",
    "iommu_group": 42,
    "numa_node": 1,
    "uuid": "GPU-12345678-1234-1234-1234-123456789012",

    "capabilities": {
      "mig": {
        "supported": true,
        "enabled": true,
        "max_instances": 7,
        "profiles": ["1g.10gb", "2g.20gb", "3g.40gb", "7g.79gb"]
      },
      "sriov": {
        "supported": true,
        "max_vfs": 8,
        "enabled_vfs": 4
      },
      "mdev": {
        "supported": true,
        "types": [
          {"name": "nvidia-299", "profile": "GRID A10-8Q", "max_instances": 2, "available": 1},
          {"name": "nvidia-300", "profile": "GRID A10-6Q", "max_instances": 3, "available": 2}
        ]
      },
      "hami_core": {
        "supported": true,
        "max_split_count": 10,
        "current_splits": 3
      }
    },

    "resources": {
      "memory_mb": 81920,
      "memory_allocated_mb": 20480,
      "memory_free_mb": 61440,
      "cores_total": 100,
      "cores_allocated": 30,
      "cores_free": 70,
      "bandwidth_gbps": 600,
      "bandwidth_allocated_gbps": 150
    },

    "status": {
      "state": "online",
      "health": "healthy",              // healthy / degraded / unhealthy
      "temperature_c": 65,
      "power_w": 250,
      "utilization_percent": 45,
      "memory_used_percent": 30,
      "pcie_generation": 4,
      "pcie_link_width": 16,
      "pcie_throughput_gbps": 48
    },

    "topology": {
      "node": "gpu-node-01",
      "zone": "rack-03",
      "datacenter": "dc-seoul",
      "numa_node": 1,
      "cpu_cores_affinity": [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31],
      "nvlink": {
        "connected_gpus": ["gpu-node-01-nvidia-1", "gpu-node-01-nvidia-2", "gpu-node-01-nvidia-3"],
        "bandwidth_per_link_gbps": 600
      }
    },

    "assignments": [
      {
        "type": "VM",
        "name": "training-vm-01",
        "instance_uuid": "vm-uuid-001",
        "allocation_mode": "MIG",
        "mig_profile": "1g.10gb",
        "started_at": "2026-05-10T09:00:00Z",
        "owner": "project-alpha",
        "vGPU_type": null
      },
      {
        "type": "Container",
        "name": "inference-pod-05",
        "instance_uuid": "pod-uuid-005",
        "allocation_mode": "hami_core",
        "memory_mb": 3000,
        "cores_percent": 30,
        "started_at": "2026-05-10T09:05:00Z",
        "owner": "project-beta"
      }
    ],

    "historical_health": [
      {"timestamp": "2026-05-09T10:00:00Z", "event": "temperature_warning", "value": 82},
      {"timestamp": "2026-05-09T10:05:00Z", "event": "temperature_normal", "value": 70}
    ],

    "vendor_specific": {
      "nvidia": {
        "driver_version": "550.54.15",
        "cuda_version": "12.2",
        "vgpu_license": "valid",
        "persistence_mode": true,
        "compute_mode": "Default"
      },
      "amd": {
        "rocm_version": "6.0.0",
        "smi_version": "24.4.0"
      },
      "ascend": {
        "cann_version": "7.0.RC1",
        "npu_smi_version": "24.1.0"
      }
    }
  }
}
```

### 8.2 Accelerator CRD (OKAstro Custom Resource)

```yaml
apiVersion: okastro.io/v1alpha1
kind: Accelerator
metadata:
  name: gpu-node-01-nvidia-0
  labels:
    accelerator.vendor: nvidia
    accelerator.model: A100-SXM4-80GB
    accelerator.type: GPU
    accelerator.numa: "1"
    accelerator.mig: "true"
spec:
  # (위 JSON의 accelerator 필드와 동일)
  nodeName: gpu-node-01
  vendor: NVIDIA
  model: A100-SXM4-80GB
  pciAddress: "0000:17:00.0"
  iommuGroup: 42
  numaNode: 1
status:
  state: online
  health: healthy
  allocations:
  - instance: vm-uuid-001
    type: MIG
    profile: 1g.10gb
---
apiVersion: okastro.io/v1alpha1
kind: AcceleratorNode
metadata:
  name: gpu-node-01
spec:
  accelerators:
  - name: gpu-node-01-nvidia-0
    type: GPU
  - name: gpu-node-01-nvidia-1
    type: GPU
  - name: gpu-node-01-nvidia-2
    type: GPU
  - name: gpu-node-01-nvidia-3
    type: GPU
  nodeLabels:
    gpu: "on"
    nvidia.com/gpu: "true"
    nvidia.com/gpu.product: "A100-SXM4-80GB"
    nvidia.com/gpu.count: "4"
```

---

## Ⅸ. Scheduler 설계

### 9.1 Layered Scheduler Architecture

```
                          ┌─────────────────────────────────────┐
                          │     OKAstro Scheduler (Top-Level)    │
                          │     "어느 워크로드를 어느 유형의     │
                          │      Accelerator에 배치할지"         │
                          │                                     │
                          │  Workload Profile → Accelerator     │
                          │  Profile Mapping                    │
                          └──────────────┬──────────────────────┘
                                         │
           ┌─────────────────────────────┼────────────────────────┐
           │                             │                        │
           ▼                             ▼                        ▼
  ┌──────────────────┐   ┌────────────────────┐   ┌──────────────────┐
  │ K8s + HAMi        │   │ KubeVirt           │   │ OpenStack        │
  │ Scheduler         │   │ Scheduler          │   │ Nova Scheduler   │
  │                   │   │                    │   │                  │
  │ Pod → GPU/NPU     │   │ VM → PCI/mdev     │   │ Instance →       │
  │ Fractional/Binpack│   │ NUMA-aware         │   │ Accelerator+     │
  │ Topology-aware    │   │                    │   │ Placement API    │
  └──────────────────┘   └────────────────────┘   └──────────────────┘
```

### 9.2 Workload-Aware Scheduling 정책

```go
// pkg/scheduler/scoring/workload_profile.go
// 개념 코드 — Workload 특성에 따른 Accelerator 매칭

type WorkloadProfile struct {
    Type           WorkloadType  // Training, Inference, Development, Visualization
    MinMemoryMB    int
    MinCompute     float64       // 0.0 ~ 1.0 (GPU core fraction)
    RequiredPCIeGen int
    NVLinkRequired  bool
    MIGRequired     bool
    MaxLatencyMs    int
    IsolationLevel  IsolationType  // None, Process, MIG, Device
}

type AcceleratorScore struct {
    AcceleratorID string
    TotalScore    float64  // 0 ~ 100
    Breakdown     map[string]float64
}

// Scoring factors (가중치 합산)
const (
    WeightMemoryFit    = 0.30  // 메모리 적합성
    WeightComputeFit   = 0.25  // 연산 능력 적합성
    WeightTopologyFit  = 0.15  // NUMA/Topology 정합성
    WeightUtilization  = 0.10  // 현재 활용도 (Spread 선호)
    WeightAffinity     = 0.10  // 이전 할당 이력 (Cache 선호)
    WeightPowerEffic   = 0.05  // 전력 효율
    WeightLicenseCost  = 0.05  // 라이선스 비용 (vGPU)
)

func ScoreWorkloadForAccelerator(
    wl WorkloadProfile,
    acc Accelerator,
    allocations []Allocation,
) AcceleratorScore {
    score := AcceleratorScore{
        AcceleratorID: acc.ID,
        Breakdown:     make(map[string]float64),
    }

    // Memory fit check
    if acc.Resources.MemoryMB < wl.MinMemoryMB {
        return score // incompatible, score = 0
    }
    memRatio := float64(wl.MinMemoryMB) / float64(acc.Resources.MemoryMB)
    score.Breakdown["memory_fit"] = memRatio * WeightMemoryFit * 100

    // Isolation requirement
    switch wl.IsolationLevel {
    case IsolationMIG:
        if !acc.Capabilities.MIG.Enabled {
            return score
        }
    case IsolationDevice:
        // 전체 GPU 할당 필요 — 다른 할당이 없어야 함
        if len(allocations) > 0 {
            return score
        }
    }

    // Topology fit (NVLink connected = higher score)
    if wl.NVLinkRequired && len(acc.Topology.NVLink.ConnectedGPUs) > 0 {
        score.Breakdown["topology"] = WeightTopologyFit * 100
    }

    // Utilization — prefer less utilized for interactive workloads
    if wl.Type == WorkloadTypeInference || wl.Type == WorkloadTypeDevelopment {
        utilScore := 1.0 - acc.Status.UtilizationPercent/100.0
        score.Breakdown["utilization"] = utilScore * WeightUtilization * 100
    }

    score.TotalScore = sum(score.Breakdown)
    return score
}
```

### 9.3 Scheduler Policy 예시 (HAMI 통합)

```yaml
# hami-scheduler-policy ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: hami-scheduler-policy
  namespace: kube-system
data:
  policy.yaml: |
    defaultSchedulerPolicy:
      nodeSchedulerPolicy: binpack      # binpack / spread
      gpuSchedulerPolicy: spread        # binpack / spread

    workloadProfiles:
      - name: ai-training-large
        resources:
          minMemoryMB: 40000
          minCores: 80
          isolation: mig
        scheduling:
          nodePolicy: spread             # 노드 분산 (NVLink 필요)
          gpuPolicy: binpack             # 같은 GPU 카드에 집중

      - name: ai-inference-light
        resources:
          minMemoryMB: 2000
          minCores: 10
          isolation: none
        scheduling:
          nodePolicy: binpack            # 노드 집중
          gpuPolicy: spread              # GPU 분산 (HA)

      - name: ai-development
        resources:
          minMemoryMB: 4000
          minCores: 20
          isolation: process
        scheduling:
          nodePolicy: binpack
          gpuPolicy: binpack
```

---

## Ⅹ. Runtime Adapter 구조

### 10.1 Adapter Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Unified Runtime Adapter                        │
│                                                                  │
│  ┌──────────────┐ ┌────────────────┐ ┌────────────────────────┐ │
│  │ Container    │ │ VM (KubeVirt)  │ │ OpenStack (Nova)       │ │
│  │ Adapter      │ │ Adapter        │ │ Adapter                │ │
│  │              │ │                │ │                        │ │
│  │ HAMi-core    │ │ libvirt domain │ │ Nova virt driver       │ │
│  │ devicePlugin │ │ XML 생성       │ │ PCI attach             │ │
│  │ annotation   │ │ mdev attach    │ │ ARQ binding            │ │
│  │ injection    │ │ PCI passthrough│ │ Placement API          │ │
│  └──────┬───────┘ └───────┬────────┘ └───────────┬────────────┘ │
└─────────┼─────────────────┼──────────────────────┼──────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Accelerator Backend Drivers                     │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ NVIDIA   │ │ AMD      │ │ Ascend   │ │ Intel    │           │
│  │ Driver   │ │ ROCm     │ │ CANN     │ │ Habana   │           │
│  │          │ │ Driver   │ │ Driver   │ │ Driver   │           │
│  │ nvidia-  │ │ rocm-smi │ │ npu-smi  │ │ hl-smi   │           │
│  │ smi      │ │ kfd      │ │ devmm    │ │          │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### 10.2 Container Runtime Adapter — HAMi 통합

```go
// pkg/runtime/container/adapter.go
// Container의 GPU 요청을 HAMi 형식으로 변환

func (a *ContainerAdapter) InjectGPURequirements(
    pod *corev1.Pod,
    req *AcceleratorRequest,
) error {
    switch req.Vendor {
    case "nvidia":
        // HAMi resource limits 주입
        pod.Spec.Containers[0].Resources.Limits["nvidia.com/gpu"] = req.Count
        if req.MemoryMB > 0 {
            pod.Spec.Containers[0].Resources.Limits["nvidia.com/gpumem"] = req.MemoryMB
        }
        if req.CorePercent > 0 {
            pod.Spec.Containers[0].Resources.Limits["nvidia.com/gpucores"] = req.CorePercent
        }
        // vGPU mode annotation
        if req.MIGProfile != "" {
            pod.Annotations["nvidia.com/vgpu-mode"] = "mig"
        }
        // Node scheduling policy
        if req.NodePolicy == "binpack" {
            pod.Annotations["hami.io/node-scheduler-policy"] = "binpack"
        }

    case "amd":
        pod.Spec.Containers[0].Resources.Limits["amd.com/gpu"] = req.Count

    case "ascend":
        pod.Spec.Containers[0].Resources.Limits["huawei.com/Ascend910"] = req.Count
    }

    return nil
}
```

### 10.3 VM Runtime Adapter — KubeVirt 통합

```go
// pkg/runtime/vm/adapter.go
// VM의 GPU 요청을 KubeVirt VMI CRD로 변환

func (a *VMAdapter) BuildVMWithGPU(
    vmSpec *VirtualMachineSpec,
    gpuReq *AcceleratorRequest,
) (*kubevirtv1.VirtualMachine, error) {

    vmi := &kubevirtv1.VirtualMachine{
        Spec: kubevirtv1.VirtualMachineSpec{
            Template: &kubevirtv1.VirtualMachineInstanceTemplateSpec{
                Spec: kubevirtv1.VirtualMachineInstanceSpec{
                    Domain: kubevirtv1.DomainSpec{
                        CPU: &kubevirtv1.CPU{Sockets: 1, Cores: 8, Threads: 2},
                        Memory: &kubevirtv1.Memory{Guest: resource.MustParse("32Gi")},
                        Devices: kubevirtv1.Devices{},
                    },
                },
            },
        },
    }

    // GPU attachment mode에 따른 Device 설정
    switch gpuReq.AllocationMode {
    case "passthrough":
        // PCI Passthrough — 전체 GPU
        vmi.Spec.Template.Spec.Domain.Devices.GPUs = append(
            vmi.Spec.Template.Spec.Domain.Devices.GPUs,
            kubevirtv1.GPU{
                Name:       gpuReq.Name,
                DeviceName: fmt.Sprintf("%s.com/%s_PCI", gpuReq.Vendor, gpuReq.Model),
            },
        )

    case "mdev":
        // Mediated Device (vGPU)
        vmi.Spec.Template.Spec.Domain.Devices.GPUs = append(
            vmi.Spec.Template.Spec.Domain.Devices.GPUs,
            kubevirtv1.GPU{
                Name:       gpuReq.Name,
                DeviceName: fmt.Sprintf("%s.com/%s_%s", gpuReq.Vendor, gpuReq.Model, gpuReq.MDevProfile),
            },
        )

    case "mig":
        // MIG device — permittedHostDevices를 통해
        vmi.Spec.Template.Spec.Domain.Devices.GPUs = append(
            vmi.Spec.Template.Spec.Domain.Devices.GPUs,
            kubevirtv1.GPU{
                Name:       gpuReq.Name,
                DeviceName: fmt.Sprintf("nvidia.com/MIG-%s", gpuReq.MIGProfile),
            },
        )
    }

    return vmi, nil
}
```

### 10.4 OpenStack Runtime Adapter — Cyborg 통합

```python
# pkg/runtime/openstack/adapter.py
# OpenStack VM 생성 시 Cyborg ARQ 자동 바인딩

class OpenStackRuntimeAdapter:
    def __init__(self):
        self.cyborg = cyborg_client.Client()
        self.nova = nova_client.Client()

    async def create_server_with_accelerator(
        self,
        server_create_request: ServerCreateRequest,
        accelerator_request: AcceleratorRequest,
    ) -> ServerDetail:
        # 1. Device profile 조회
        device_profile = self.cyborg.device_profile.get(
            accelerator_request.device_profile_name,
        )

        # 2. Nova flavor에 accelerator 요청 추가
        flavor = self._create_accelerator_flavor(
            accelerator_request,
        )

        # 3. Server 생성 요청
        server = self.nova.servers.create(
            name=server_create_request.name,
            flavor=flavor.id,
            image=server_create_request.image_id,
            networks=server_create_request.networks,
            # Cyborg accelerator 요청을 scheduler_hints로 전달
            scheduler_hints={
                "accelerator": device_profile.uuid,
            },
        )

        # 4. ARQ 생성 (Cyborg API)
        arqs = self.cyborg.accelerator_request.create(
            device_profile_name=accelerator_request.device_profile_name,
        )

        # 5. ARQ 바인딩 (Nova compute manager가 자동 처리)
        #    Nova가 PATCH /v2/accelerator_requests 호출
        #    attach_handle_info로 libvirt domain XML 생성

        return server
```

---

## Ⅺ. Telemetry 및 Monitoring 구조

### 11.1 Telemetry Data Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Collector Layer                               │
│                                                                       │
│  ┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ DCGM       │  │ AMD Metrics  │  │ npu-smi    │  │ hl-smi       │  │
│  │ Exporter   │  │ Exporter     │  │ Exporter   │  │ Exporter     │  │
│  │ (NVIDIA)   │  │ (AMD)        │  │ (Ascend)   │  │ (Habana)     │  │
│  └─────┬──────┘  └──────┬───────┘  └─────┬──────┘  └──────┬───────┘  │
│        │                │                │               │           │
│        ▼                ▼                ▼               ▼           │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                  Unified Metrics Collector                       │ │
│  │  DaemonSet: okastro-metrics-collector                            │ │
│  │                                                                  │ │
│  │  - Pulls from all vendor exporters                               │ │
│  │  - Converts to unified metric format                             │ │
│  │  - Adds accelerator_id, node, owner labels                       │ │
│  │  - Exposes unified /metrics endpoint                             │ │
│  └──────────────────────────┬───────────────────────────────────────┘ │
└─────────────────────────────┼─────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Storage Layer                               │
│                                                                   │
│  ┌────────────────┐  ┌───────────────┐  ┌────────────────────┐   │
│  │  Prometheus     │  │  Thanos       │  │  VictoriaMetrics   │   │
│  │  (short-term)   │──▶│  (long-term)  │  │  (alternative)    │   │
│  └────────────────┘  └───────┬───────┘  └────────────────────┘   │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Grafana Dashboards                        │  │
│  │                                                             │  │
│  │  - GPU/NPU Resource Utilization                             │  │
│  │  - Per-tenant Accelerator Usage                             │  │
│  │  - Power/Temperature Heatmap                                │  │
│  │  - Allocation History                                       │  │
│  │  - Failure/Error Tracking                                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 11.2 Unified Metrics Format

```prometheus
# HELP okastro_accelerator_memory_total_bytes Total memory per accelerator
# TYPE okastro_accelerator_memory_total_bytes gauge
okastro_accelerator_memory_total_bytes{vendor="nvidia",model="A100-80GB",accelerator_id="gpu-0",node="gpu-node-01"} 85899345920
okastro_accelerator_memory_total_bytes{vendor="amd",model="MI250",accelerator_id="gpu-0",node="gpu-node-02"} 131941395333
okastro_accelerator_memory_total_bytes{vendor="ascend",model="Ascend910B",accelerator_id="npu-0",node="npu-node-01"} 34359738368

# HELP okastro_accelerator_memory_used_bytes Currently used memory
# TYPE okastro_accelerator_memory_used_bytes gauge
okastro_accelerator_memory_used_bytes{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01"} 21474836480

# HELP okastro_accelerator_utilization_percent GPU/NPU compute utilization
# TYPE okastro_accelerator_utilization_percent gauge
okastro_accelerator_utilization_percent{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01"} 45.2

# HELP okastro_accelerator_temperature_celsius Device temperature
# TYPE okastro_accelerator_temperature_celsius gauge
okastro_accelerator_temperature_celsius{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01"} 65

# HELP okastro_accelerator_power_watts Device power draw
# TYPE okastro_accelerator_power_watts gauge
okastro_accelerator_power_watts{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01"} 250

# HELP okastro_accelerator_pcie_throughput_bytes PCIe data throughput
# TYPE okastro_accelerator_pcie_throughput_bytes counter
okastro_accelerator_pcie_throughput_bytes{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",direction="rx"} 107374182400
okastro_accelerator_pcie_throughput_bytes{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",direction="tx"} 53687091200

# HELP okastro_accelerator_allocated_instances Count of allocated instances
# TYPE okastro_accelerator_allocated_instances gauge
okastro_accelerator_allocated_instances{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",mode="mig",profile="1g.10gb"} 2
okastro_accelerator_allocated_instances{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",mode="hami_core"} 3

# HELP okastro_accelerator_errors_total Accelerator error count by type
# TYPE okastro_accelerator_errors_total counter
okastro_accelerator_errors_total{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",error_type="xe"} 2
okastro_accelerator_errors_total{vendor="nvidia",accelerator_id="gpu-0",node="gpu-node-01",error_type="temperature_throttle"} 1
```

### 11.3 Fault Detection 및 복구 흐름

```
1. Metric 수집 (dcgm-exporter / amd-metrics-exporter / npu-smi-exporter)
   │
2. Prometheus alert rule 평가
   ├── accelerator_health == 0              → Critical
   ├── temperature > 85                     → Warning (throttle imminent)
   ├── memory_errors > threshold            → Warning (ECC errors)
   ├── pcie_link_width < expected           → Warning (link degradation)
   └── accelerator_unreachable > 5m         → Critical (node issue)
   │
3. AlertManager가 alert 전파
   ├── Slack/PagerDuty 알림
   └── OKAstro Operator Webhook 호출
       │
4. OKAstro Fault Recovery Operator
   ├── Critical alert:
   │   ├── 해당 Accelerator에 "faulty" 레이블 추가
   │   ├── Running workload을 다른 GPU로 live migration 시도
   │   │   ├── VM + vGPU: KubeVirt live migration
   │   │   ├── Container + GPU: Pod eviction → reschedule
   │   │   └── 실패 시: workload 중단 → 사용자 알림
   │   ├── HAMi scheduler가 faulty GPU 제외
   │   └── 지원 티켓 자동 생성
   │
   └── Warning alert:
       ├── 모니터링 대시보드 하이라이트
       └── 관리자 검토 요청

5. 복구 후 검증
   ├── Health check 재실행
   └── 정상 → "faulty" 레이블 제거, HAMi 스케줄러 재포함
```

---

## Ⅻ. Dashboard 및 API 구조

### 12.1 API Endpoints 설계

```
┌─────────────────────────────────────────────────────────────────────┐
│  OKAstro Accelerator API (FastAPI)                                   │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  Accelerator Management                                              │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  GET    /api/v1/accelerators                                        │
│    → 전체 Accelerator 목록 (필터: vendor, model, status, node)      │
│    Response: [{id, vendor, model, status, node, utilization, ...}]  │
│                                                                     │
│  GET    /api/v1/accelerators/{id}                                   │
│    → Accelerator 상세 + 현재 할당 정보                              │
│    Response: AcceleratorMetadata (JSON, see Section Ⅷ)             │
│                                                                     │
│  GET    /api/v1/accelerators/{id}/metrics                           │
│    → 실시간 Metrics (temperature, utilization, power, memory)       │
│    Response: {timestamp, metrics: [{name, value, unit}]}            │
│                                                                     │
│  PUT    /api/v1/accelerators/{id}/maintenance                       │
│    → 유지보수 모드 전환 (더 이상 할당하지 않음)                     │
│    Request: {maintenance: true, reason: "...", estimated_duration}  │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  Accelerator Allocation                                              │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  POST   /api/v1/allocations                                         │
│    → Accelerator 할당 요청 (VM/Container 통합)                      │
│    Request: {                                                        │
│      target_type: "vm" | "container",                               │
│      target_ref: "vm-uuid" | "pod-name",                            │
│      accelerator: {vendor, model, count, memory_mb, core_percent,   │
│                    allocation_mode: "passthrough"|"mdev"|"mig"|"hami"}│
│      owner: "project-alpha"                                         │
│    }                                                                 │
│    Response: {allocation_id, status: "pending"|"bound"|"failed"}    │
│                                                                     │
│  DELETE /api/v1/allocations/{id}                                    │
│    → 할당 해제 (GPUs/NPUs 반환)                                     │
│    Response: {status: "released"}                                   │
│                                                                     │
│  GET    /api/v1/allocations                                         │
│    → 할당 현황 (필터: owner, status, accelerator_id)               │
│    Response: [{id, target, accelerator, status, created_at, ...}]   │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  Accelerator Profiles                                               │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  GET    /api/v1/profiles                                            │
│    → Accelerator 프로필 목록 (사전 정의된 GPU 구성을 템플릿화)      │
│    Response: [{name: "gpu-small", resources: {vendor, memory, ...}}]│
│                                                                     │
│  POST   /api/v1/profiles                                            │
│    → 새 프로필 등록                                                  │
│    Request: {name, resources: {vendor, model, memory_mb, ...}}      │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  Usage & Quota                                                      │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  GET    /api/v1/usage/projects/{project_id}                         │
│    → 프로젝트별 Accelerator 사용량                                   │
│    Response: {total_gpu_hours, current_allocations, quota_limit}    │
│                                                                     │
│  GET    /api/v1/usage/users/{user_id}                               │
│    → 사용자별 Accelerator 사용량                                     │
│    Response: {total_gpu_hours, monthly_usage: [{date, hours}]}      │
│                                                                     │
│  PUT    /api/v1/quotas/projects/{project_id}                        │
│    → 프로젝트 Quota 설정                                             │
│    Request: {max_gpus, max_memory_gb, priority}                     │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  System Health                                                      │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  GET    /api/v1/health/accelerators                                 │
│    → Accelerator 클러스터 상태 요약                                  │
│    Response: {                                                      │
│      total: 48, online: 46, degraded: 1, offline: 1,               │
│      by_vendor: {nvidia: 32, amd: 8, ascend: 8},                   │
│      utilization_avg: 62.3%                                         │
│    }                                                                │
│                                                                     │
│  GET    /api/v1/health/alerts                                       │
│    → 활성 Alert 목록                                                │
│    Response: [{id, severity, message, accelerator_id, timestamp}]   │
│                                                                     │
│  ────────────────────────────────────────────────────────────────── │
│  AI Runtime                                                         │
│  ────────────────────────────────────────────────────────────────── │
│                                                                     │
│  POST   /api/v1/runtime/workspaces                                  │
│    → AI Workspace 생성 (Jupyter / VSCode / LLM Inference)          │
│    Request: {type, image, accelerator_profile, storage_gb, users[]} │
│    Response: {workspace_id, url, status: "creating"}                │
│                                                                     │
│  GET    /api/v1/runtime/workspaces/{id}                             │
│    → Workspace 상세                                                 │
│    Response: {id, type, status, url, accelerator, created_at}       │
│                                                                     │
│  DELETE /api/v1/runtime/workspaces/{id}                             │
│    → Workspace 삭제                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 12.2 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header: [OKAstro Accelerator Orchestrator]   [Project Alpha] [User] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│  │Overall│ │GPU   │ │NPU   │ │Alloc │ │AI    │ │Usage │ │Admin │  │
│  │Health │ │Clustr│ │Clustr│ │History│ │Runtim│ │&Quota│ │      │  │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Resource Overview                                             │  │
│  │                                                               │  │
│  │  [===== NVIDIA GPU ====]  32 / 48 used  (67%)                 │  │
│  │  [=== AMD GPU =====]      6 / 8  used  (75%)                 │  │
│  │  [=== Ascend NPU ===]     4 / 8  used  (50%)                 │  │
│  │  [                        ]  0 / 16 FPGA avail               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐  ┌────────────────────────────────────┐  │
│  │  Top Consuming       │  │  Cluster Utilization Heatmap       │  │
│  │  Projects            │  │                                    │  │
│  │                      │  │  ┌──────────────────────────┐     │  │
│  │  1. project-alpha    │  │  │ rack01: ████████░░ 80%   │     │  │
│  │     120 GPU-hours    │  │  │ rack02: ██████░░░░ 60%   │     │  │
│  │  2. project-beta     │  │  │ rack03: ████░░░░░░ 40%   │     │  │
│  │     85 GPU-hours     │  │  │ rack04: ██████████ 100%  │     │  │
│  │  3. ml-research      │  │  └──────────────────────────┘     │  │
│  │     42 GPU-hours     │  │                                    │  │
│  └──────────────────────┘  └────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Active Alerts (3)                                            │  │
│  │  ┌───────────────────────────────────────────────────────┐   │  │
│  │  │ ⚠ gpu-node-03/gpu-1: Temperature 87°C (Warning)      │   │  │
│  │  │ ⚠ npu-node-01/npu-2: Memory ECC errors (Warning)     │   │  │
│  │  │ ✗ gpu-node-05/gpu-0: Xid 48 (Critical - Restarting)  │   │  │
│  │  └───────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ⅩⅢ. CUDA/ROCm/NPU SDK Abstraction 구조

### 13.1 Abstraction Layer 설계

```
┌──────────────────────────────────────────────────────────────────────┐
│                    AI Workload (User Code)                            │
│  PyTorch / TensorFlow / JAX / vLLM / Custom App                     │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────────────┐
│              Unified Accelerator SDK Interface                        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  okastro-sdk (Python 패키지)                                   │  │
│  │                                                                │  │
│  │  from okastro.accelerator import get_accelerator_info          │  │
│  │  from okastro.accelerator import get_device_memory             │  │
│  │  from okastro.accelerator import synchronize                   │  │
│  │  from okastro.accelerator import get_peer_access               │  │
│  │                                                                │  │
│  │  # 내부 동작: vendor 감지 → 적절한 backend 호출              │  │
│  │  @singledispatch                                                     │
│  │  def alloc_memory(size):                                       │  │
│  │      ...                                                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ CUDA     │  │ ROCm     │  │ CANN     │
│ Backend  │  │ Backend  │  │ Backend  │
│          │  │          │  │          │
│ torch.   │  │ torch.   │  │ torch.   │
│ cuda     │  │ hip      │  │ npu      │
│          │  │          │  │          │
│ nvidia-  │  │ rocm-smi │  │ npu-smi  │
│ smi      │  │          │  │          │
└──────────┘  └──────────┘  └──────────┘
```

### 13.2 Python SDK 구현 예시

```python
# okastro/sdk/accelerator/__init__.py
# 통합 Accelerator SDK — vendor 차이를 추상화

import os
import platform
from typing import Any, Optional

class AcceleratorBackend:
    """각 vendor backend의 interface"""

    def get_device_count(self) -> int: ...
    def get_device_name(self, device: int) -> str: ...
    def get_memory_info(self, device: int) -> dict: ...
    def get_utilization(self, device: int) -> float: ...
    def get_temperature(self, device: int) -> float: ...

class NVIDIABackend(AcceleratorBackend):
    def __init__(self):
        import pynvml
        pynvml.nvmlInit()
        self.nvml = pynvml
        self.count = pynvml.nvmlDeviceGetCount()

    def get_device_count(self) -> int:
        return self.count

    def get_device_name(self, device: int) -> str:
        handle = self.nvml.nvmlDeviceGetHandleByIndex(device)
        return self.nvml.nvmlDeviceGetName(handle)

    def get_memory_info(self, device: int) -> dict:
        handle = self.nvml.nvmlDeviceGetHandleByIndex(device)
        mem = self.nvml.nvmlDeviceGetMemoryInfo(handle)
        return {"total": mem.total, "used": mem.used, "free": mem.free}

class ROCmBackend(AcceleratorBackend):
    def __init__(self):
        import amdsmi
        amdsmi.amdsmi_init()
        self.amdsmi = amdsmi
        self.sockets = amdsmi.amdsmi_get_processor_handles()

    def get_device_count(self) -> int:
        return len(self.sockets)

    def get_device_name(self, device: int) -> str:
        return self.amdsmi.amdsmi_get_processor_info(self.sockets[device])["name"]

    def get_memory_info(self, device: int) -> dict:
        mem = self.amdsmi.amdsmi_get_gpu_memory_total(
            self.sockets[device], self.amdsmi.MemoryType.VRAM
        )
        usage = self.amdsmi.amdsmi_get_gpu_memory_usage(
            self.sockets[device], self.amdsmi.MemoryType.VRAM
        )
        return {"total": mem, "used": usage, "free": mem - usage}

class CANNBackend(AcceleratorBackend):
    """Ascend NPU CANN backend"""
    def __init__(self):
        from mindspore import context
        import subprocess
        self._check_npu()

    def _check_npu(self):
        result = subprocess.run(["npu-smi", "info", "-t", "device"], capture_output=True)
        self.devices = self._parse_npu_smi(result.stdout)

    def get_device_count(self) -> int:
        return len(self.devices)

    def get_device_name(self, device: int) -> str:
        return self.devices[device]["name"]

    def get_memory_info(self, device: int) -> dict:
        d = self.devices[device]
        return {"total": d["memory_total"], "used": d["memory_used"], "free": d["memory_total"] - d["memory_used"]}

class UnsupportedBackend(AcceleratorBackend):
    def get_device_count(self) -> int:
        return 0

# Auto-detection of available backends
def detect_backend() -> AcceleratorBackend:
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count > 0:
            return NVIDIABackend()
    except Exception:
        pass

    try:
        import amdsmi
        amdsmi.amdsmi_init()
        sockets = amdsmi.amdsmi_get_processor_handles()
        if len(sockets) > 0:
            return ROCmBackend()
    except Exception:
        pass

    try:
        result = __import__("subprocess").run(
            ["npu-smi", "info", "-t", "device"], capture_output=True
        )
        if result.returncode == 0:
            return CANNBackend()
    except Exception:
        pass

    return UnsupportedBackend()


# Public API
_backend: Optional[AcceleratorBackend] = None

def _get_backend() -> AcceleratorBackend:
    global _backend
    if _backend is None:
        _backend = detect_backend()
    return _backend

def device_count() -> int:
    return _get_backend().get_device_count()

def device_name(device: int = 0) -> str:
    return _get_backend().get_device_name(device)

def memory_info(device: int = 0) -> dict:
    return _get_backend().get_memory_info(device)

def utilization(device: int = 0) -> float:
    return _get_backend().get_utilization(device)

def temperature(device: int = 0) -> float:
    return _get_backend().get_temperature(device)

def accelerator_info() -> dict:
    """전체 Accelerator 정보 반환 (API 응답용)"""
    backend = _get_backend()
    devices = []
    for i in range(backend.get_device_count()):
        devices.append({
            "index": i,
            "name": backend.device_name(i),
            "memory": backend.memory_info(i),
            "utilization": backend.utilization(i),
            "temperature": backend.temperature(i),
        })
    return {
        "type": type(backend).__name__.replace("Backend", ""),
        "count": len(devices),
        "devices": devices,
    }
```

### 13.3 NVIDIA 종속성 최소화 전략

```
계층              전략
─────────────────────────────────────────────────────────────
SDK 레벨        okastro-sdk가 vendor 감지 후 backend 자동 선택
                CUDA 코드는 nvidia backend에서만 동작
                ROCm/HIP, CANN은 각각 별도 backend

이미지 레벨     각 vendor별 container image 분리
                - okastro/ai-runtime:cuda12.2
                - okastro/ai-runtime:rocm6.0
                - okastro/ai-runtime:ascend-cann7.0
                공통 Jupyter/VSCode는 vendor 무관

Scheduling      HAMi가 vendor별 resource name으로 통합
                nvidia.com/gpu → amd.com/gpu → huawei.com/Ascend910
                Scheduler는 resource name으로만 판단

Metadata        Unified Accelerator Metadata에 vendor 필드
                API consumer가 vendor 필드로 분기 가능

Runtime         Device Plugin이 vendor별로 따로 배포
                공통 DaemonSet 내 multi-container로 구성
```

---

## ⅩⅣ. vNPU 및 차세대 Accelerator 확장 전략

### 14.1 vNPU (Virtual NPU) Abstraction

```
┌──────────────────────────────────────────────────────────────────┐
│                      vNPU Abstraction Layer                        │
│                                                                   │
│  "물리적 NPU의 차이를 추상화하여, 어떤 NPU든 동일한 가상 NPU 로   │
│    제공"                                                          │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  vNPU Resource Pool                                         │  │
│  │                                                             │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐            │  │
│  │  │Ascend│ │BMF   │ │Tesla │ │Dojo  │ │Gaudi │            │  │
│  │  │910B  │ │NPU   │ │NPU   │ │(future│ │2     │            │  │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘            │  │
│  │                                                             │  │
│  │  ┌────────────────────────────────────────────────────┐    │  │
│  │  │  vNPU Scheduler: 성능/용량/가격 기반 매칭           │    │  │
│  │  └────────────────────────────────────────────────────┘    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘

vNPU 특성 모델 (JSON 예시):

{
  "vNPU": {
    "id": "vNPU-001",
    "abstract_ops": "10 TFLOPS (FP16)",
    "abstract_memory": "32 GB HBM",
    "abstract_bandwidth": "1.2 TB/s",
    "actual_backend": {
      "vendor": "ascend",
      "model": "Ascend910B",
      "mapping": {
        "performance_factor": 1.0,
        "memory_factor": 1.0
      }
    },
    "capabilities": {
      "training": true,
      "inference": true,
      "fp16": true,
      "bf16": true,
      "fp8": true,
      "transformer_engine": true
    },
    "compatibility": {
      "torch_npu": true,
      "torch_cuda": false,
      "torch_hip": false
    }
  }
}
```

### 14.2 vNPU 확장 로드맵

```
Phase 3 (9개월)
├── vNPU CRD 정의
│   ├── Spec: abstract performance (TFLOPS, memory, bandwidth)
│   ├── Spec: capability requirements (fp16, bf16, fp8, etc.)
│   └── Status: actual backend mapping
├── vNPU Scheduler
│   ├── Request: "vNPU 1개, FP16 10TFLOPS 이상"
│   ├── Mapping: Ascend 910B (1개) → 실제 성능 12 TFLOPS → match
│   └── Fallback: Ascend 부족 시 Gaudi 2로 대체 가능 (성능 0.8x)
├── vNPU Operator
│   └── vNPU Claim → 실제 NPU 할당 → Adapter 매핑
└── vNPU Monitoring
    └── vNPU 레벨 메트릭 → 실제 NPU 메트릭 변환

Phase 4 (12개월)
├── Vendor-agnostic AI Runtime
│   ├── "okastro run --vNPU 4 --image pytorch:latest"
│   └── 내부적으로 적절한 backend 매핑
├── Cross-vendor Live Migration
│   └── Ascend → Gaudi migration (성능 차이를 compensator로 보정)
└── AI Datacenter OS
    └── vNPU를 기본 단위로 한 Accelerator Orchestration
```

---

## ⅩⅤ. 성능 병목 및 기술 리스크

### 15.1 주요 병목 포인트

| # | 병목 | 영향 | 해결 방안 |
|---|------|------|-----------|
| 1 | HAMi-core LD_PRELOAD 오버헤드 | CUDA call당 ~1-5μs | MIG/MDEV 사용 추천, hami-core는 dev/test 전용 |
| 2 | VFIO DMA 매핑 초기화 | VM 부팅 시 10-30초 | Pre-bind GPU to VFIO, hugepages pre-allocation |
| 3 | SR-IOV VF 메모리 단편화 | GPU 메모리 단편화로 최대 15% 손실 | Memory-aware scheduling으로 단편화 최소화 |
| 4 | mdev 타입 변경 불가 | 한 번 생성된 mdev 타입 변경 불가 | 적절한 사전 계획, 동적 재구성 불가 가정 |
| 5 | Nova-Cyborg 통합 지연 | VM 생성 시 ARQ 바인딩에 5-15초 추가 | Pre-ARQ allocation pool |
| 6 | KubeVirt live migration + GPU | vGPU migration은 QEMU/libvirt에 의존 | 제한적 지원, 계획된 migration만 허용 |
| 7 | Multi-vendor 모니터링 통일 | 각 vendor의 metric 의미/단위 상이 | 정규화 레이어 필요 |
| 8 | HAMi + KubeVirt GPU 충돌 | 둘 다 GPU device plugin 사용 시 충돌 | Node 레이블로 역할 분리 (container/VM 전용 노드) |

### 15.2 기술 리스크

| 리스크 | 심각도 | 확률 | 대응 |
|--------|--------|------|------|
| NVIDIA vGPU 라이선스 비용 | High | 100% | 오픈소스 대안(HAMi-core, AMD MxGPU) 우선 |
| MIG 지원 GPU 제한 (A100/H100+) | Medium | 80% | HAMi-core fallback, AMD 분산 |
| Ascend NPU K8s 통합 미성숙 | Medium | 60% | HAMi Ascend 지원 활용, vendor plugin 모니터링 |
| OpenStack Cyborg 프로덕션 미검증 | Medium | 50% | KubeVirt track 우선, Cyborg은 기존 호환용 |
| IOMMU group 공유 문제 | High | 40% | GPU + Audio function이 IOMMU group 공유 시 분리 불가 |
| KubeVirt mdev migration 미지원 | Medium | 70% | Migration 대신 재생성 전략 |

---

## ⅩⅥ. MVP 구현 우선순위

### Phase 1 (3개월): Core GPU Orchestration

```
Priority: P0 - Must Have
├── [P0] HAMi 설치 및 기본 GPU Sharing (NVIDIA)
│   ├── Helm 차트로 HAMi 배포
│   ├── GPU 노드 라벨링 (gpu=on)
│   ├── Fractional GPU 할당 (nvidia.com/gpumem, nvidia.com/gpucores)
│   └── 2개 Pod가 1개 GPU 공유하는 시나리오 검증
│
├── [P0] KubeVirt GPU Passthrough
│   ├── IOMMU/VFIO 설정
│   ├── KubeVirt CR에 permittedHostDevices 설정
│   └── VM에 GPU passthrough 검증 (nvidia-smi inside VM)
│
├── [P0] Accelerator Metadata CRD
│   ├── Accelerator CRD 배포
│   ├── AcceleratorNode CRD 배포
│   └── Device Plugin 데이터 → CRD 동기화
│
├── [P0] Unified Accelerator API (MVP)
│   ├── GET /accelerators
│   ├── POST /allocations
│   └── DELETE /allocations
│
└── [P1] 기본 모니터링 (DCGM Exporter + Prometheus)
    ├── DCGM Exporter DaemonSet
    └── Grafana 기본 Dashboard
```

### Phase 2 (3-6개월): Multi-Vendor & VM 통합

```
Priority: P1 - Should Have
├── [P1] AMD GPU 지원
│   ├── AMD ROCm k8s-device-plugin 배포
│   ├── AMD GPU Node Labeller
│   └── HAMi AMD plugin 통합
│
├── [P1] Ascend NPU 지원
│   ├── Ascend device plugin 배포
│   ├── HAMi Ascend plugin 확인
│   └── CANN 추론 테스트
│
├── [P1] OpenStack Cyborg 연동 (기본)
│   ├── Cyborg 서비스 배포 (API + Conductor + Agent)
│   ├── Device Profile 정의
│   ├── Nova-Cyborg 연동 설정
│   └── ARQ lifecycle 테스트
│
├── [P1] KubeVirt vGPU (mdev)
│   ├── NVIDIA vGPU Manager 설치
│   ├── KubeVirt mdev configuration
│   ├── mediatedDevicesConfiguration 설정
│   └── VM에 vGPU attach 테스트
│
└── [P2] 기본 Quota 시스템
    ├── Project별 GPU limit
    └── 사용량 트래킹
```

### Phase 3 (6-9개월): 고급 기능

```
Priority: P2 - Nice to Have
├── [P2] Workload-Aware Scheduling
│   ├── Workload profile 정의
│   ├── Accelerator scoring engine
│   └── HAMi policy 커스터마이징
│
├── [P2] vNPU Abstraction (알파)
│   ├── vNPU CRD
│   ├── vNPU → 실제 device 매핑
│   └── 기본 vNPU 스케줄링
│
├── [P2] AI Runtime
│   ├── JupyterHub + GPU 통합
│   ├── VSCode Server + GPU
│   └── LLM Inference (vLLM + GPU)
│
└── [P2] Fault Detection & Recovery
    ├── Accelerator health monitoring
    ├── Alert → Operator → Recovery pipeline
    └── Faulty accelerator 제외 flow
```

---

## ⅩⅦ. 추천 디렉토리 구조

```
okastro/
├── api/                              # Public REST API
│   ├── v1/
│   │   ├── accelerators.py
│   │   ├── allocations.py
│   │   ├── profiles.py
│   │   ├── usage.py
│   │   ├── health.py
│   │   └── runtime.py
│   ├── deps/
│   │   └── services.py
│   └── router.py
│
├── operators/                        # Kubernetes Operators
│   ├── accelerator-operator/         # Accelerator CRD lifecycle
│   │   ├── api/
│   │   │   └── v1alpha1/
│   │   │       ├── accelerator_types.go
│   │   │       └── acceleratornode_types.go
│   │   ├── controllers/
│   │   │   ├── accelerator_controller.go
│   │   │   └── acceleratornode_controller.go
│   │   ├── pkg/
│   │   │   ├── discovery/            # Device discovery logic
│   │   │   ├── allocation/           # Allocation management
│   │   │   └── metrics/              # Metrics collection
│   │   └── config/
│   │       ├── crd/
│   │       └── rbac/
│   │
│   ├── allocation-operator/          # Allocation lifecycle
│   │   ├── api/v1alpha1/
│   │   │   └── allocation_types.go
│   │   └── controllers/
│   │
│   └── fault-recovery-operator/      # Fault detection & recovery
│       └── controllers/
│
├── scheduler/                        # Scheduler Engine
│   ├── pkg/
│   │   ├── scoring/
│   │   │   ├── workload_profile.go
│   │   │   ├── memory_scorer.go
│   │   │   ├── topology_scorer.go
│   │   │   └── policy_scorer.go
│   │   ├── placement/
│   │   │   └── binpack.go
│   │   └── cache/
│   │       └── device_cache.go
│   └── config/
│       └── scheduler_policy.yaml
│
├── runtimes/                         # Runtime Adapters
│   ├── container/
│   │   └── adapter.go
│   ├── vm/
│   │   └── adapter.go
│   └── openstack/
│       └── adapter.py
│
├── sdk/                              # Python SDK
│   └── okastro/
│       ├── __init__.py
│       ├── accelerator/
│       │   ├── __init__.py
│       │   ├── backend.py
│       │   ├── nvidia_backend.py
│       │   ├── rocm_backend.py
│       │   └── cann_backend.py
│       ├── client/
│       │   └── api_client.py
│       └── models/
│           └── accelerator.py
│
├── telemetry/                        # Monitoring
│   ├── collectors/
│   │   ├── unified-collector/
│   │   │   └── main.go
│   │   └── vendor-exporters/
│   │       ├── dcgm-exporter-values.yaml
│   │       ├── amd-metrics-exporter-values.yaml
│   │       └── npu-exporter-values.yaml
│   ├── alerts/
│   │   ├── accelerator_alerts.yaml
│   │   └── node_alerts.yaml
│   └── dashboards/
│       ├── accelerator-overview.json
│       └── per-project-usage.json
│
├── deploy/                           # 배포 매니페스트
│   ├── helm/
│   │   ├── hami/                     # HAMi Helm values
│   │   ├── kubevirt/                 # KubeVirt operator
│   │   ├── gpu-operator/             # NVIDIA GPU Operator
│   │   └── okastro/
│   │       ├── charts/
│   │       │   ├── accelerator-operator/
│   │       │   ├── allocation-operator/
│   │       │   └── fault-recovery-operator/
│   │       └── values.yaml
│   ├── openstack/
│   │   ├── cyborg/
│   │   │   ├── cyborg-api.conf
│   │   │   ├── cyborg-conductor.conf
│   │   │   └── cyborg-agent.conf
│   │   └── nova/
│   │       └── nova-cyborg.conf
│   └── scripts/
│       ├── vfio-setup.sh
│       ├── sriov-enable.sh
│       ├── iommu-check.sh
│       └── mdev-create.sh
│
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── user-guide/
│   └── developer-guide/
│
├── tests/
│   ├── integration/
│   │   ├── test_hami_scheduling.py
│   │   ├── test_kubevirt_gpu.py
│   │   ├── test_cyborg_arq.py
│   │   └── test_runtime_adapters.py
│   ├── unit/
│   │   ├── test_sdk.py
│   │   └── test_scheduler.py
│   └── e2e/
│       └── test_full_pipeline.py
│
└── examples/
    ├── gpu-fractional-pod.yaml
    ├── gpu-mig-pod.yaml
    ├── vm-gpu-passthrough.yaml
    ├── vm-vgpu-fractional.yaml
    ├── hami-config.yaml
    ├── kubevirt-gpu-cr.yaml
    └── cyborg-device-profile.json
```

---

## ⅩⅧ. 추천 기술 스택

| 영역 | 기술 | 버전 | 비고 |
|------|------|------|------|
| **Container Orchestration** | Kubernetes | ≥ 1.29 | DRA 지원 필요 시 ≥ 1.34 |
| **GPU/NPU Scheduling** | HAMi | ≥ 2.8.0 | DRA 지원, Multi-vendor |
| **VM Orchestration** | KubeVirt | ≥ 1.3 | GPU passthrough 안정 |
| **Accelerator Management** | OpenStack Cyborg | 2025.2 | Nova-Cyborg 상호운용 |
| **VM Control** | OpenStack Nova | 2025.2 | 기존 vMachine 호환 |
| **PCI Virtualization** | VFIO (vfio-pci) | Kernel ≥ 6.2 | IOMMU + vfio-pci |
| **GPU Partitioning** | NVIDIA MIG | Driver ≥ 525 | A100/H100 only |
| **GPU Sharing (Container)** | HAMi-core / NVIDIA MPS | Bundled | LD_PRELOAD 방식 |
| **GPU Virtualization** | NVIDIA vGPU Manager | Driver ≥ 580 | Enterprise license 필요 |
| **AMD GPU** | ROCm k8s-device-plugin | ≥ 1.3.0 | AMD GPU Operator |
| **Ascend NPU** | Ascend CANN + Device Plugin | ≥ 7.0 | HAMi 통합 가능 |
| **Multi-vendor Scheduling** | Volcano / Kueue | ≥ 1.10 / ≥ 0.9 | HAMi 통합 |
| **Telemetry** | Prometheus + Thanos | ≥ 2.50 / ≥ 0.35 | Long-term storage |
| **GPU Metrics** | DCGM Exporter | ≥ 3.3 | NVIDIA 전용 |
| **Dashboard** | Grafana | ≥ 11.0 | Custom panels |
| **Ingress** | Traefik / Istio | ≥ 2.11 / ≥ 1.22 | |
| **Auth** | Keycloak / Dex | ≥ 24.0 / ≥ 2.40 | OIDC 기반 |
| **SDK Language** | Python (SDK) + Go (Operator) | ≥ 3.12 / ≥ 1.23 | |
| **Storage** | Rook/Ceph / Longhorn | ≥ 1.15 / ≥ 1.7 | VM 디스크, metrics |
| **Package** | Helm | ≥ 3.15 | 차트 배포 |

---

## ⅩⅨ. 추천 오픈소스 조합

### Core Stack
```
Kubernetes + KubeVirt + HAMi + Prometheus + Grafana

이 5개가 핵심 스택. OpenStack은 기존 vMachine 호환용.
```

### 조합별 시나리오

| 시나리오 | 추천 조합 | 이유 |
|----------|-----------|------|
| **NVIDIA GPU만 사용, Container 위주** | HAMi + Volcano + Kueue | 가장 가벼운 조합 |
| **NVIDIA GPU, VM + Container 혼합** | HAMi + KubeVirt + GPU Operator | VM에 GPU passthrough/vGPU |
| **Multi-vendor (NVIDIA + AMD + Ascend)** | HAMi + Volcano + GPU Operator | HAMi의 multi-vendor plugin |
| **기존 vMachine 사용자, 점진적 전환** | OpenStack Cyborg + KubeVirt + HAMi | Nova 호환 유지 |
| **AI Datacenter OS 지향** | HAMi + KubeVirt + Volcano + Kueue + OKAstro Operator | 통합 제어 평면 |

### HAMi가 지원하는 Device (확장성)

```
NVIDIA GPU      ✅ (최적화)
AMD GPU         ✅ (ROCm k8s-device-plugin 연동)
Ascend NPU      ✅ (huawei.com/Ascend910)
Cambricon MLU   ✅ (cambricon.com/mlu)
HYGON DCU       ✅ (hygon.com/dcu)
Iluvatar CoreX  ✅ (iluvatar.com/corex)
Moore Threads   ✅ (mthreads.com/gpu)
MetaX GPU       ✅ (metax.com/gpu)
Intel Habana    ⏳ (준비 중, device plugin은 별도)
FPGA            ❌ (계획 없음, 별도 전략 필요)
```

---

## ⅩⅩ. 제품화 및 논문화 가능 포인트

### 20.1 제품화 포인트

| # | 제품 기능 | 차별성 | Target |
|---|----------|--------|--------|
| 1 | **VM + Container 통합 GPU Pool** | 단일 제어 평면에서 VM과 Container가 GPU를 공유/경쟁 | AI/ML 플랫폼 사업자 |
| 2 | **Multi-vendor Accelerator Orchestrator** | Vendor lock-in 해소, 최적 가격/성능 선택 | CSP, MSP |
| 3 | **Fractional GPU for VM** | VM에서도 GPU 쪼개기 (mdev/HAMi-core) | 교육/개발 환경 |
| 4 | **Accelerator-Aware Scheduling** | Workload 특성에 맞는 GPU 자동 선택 | Enterprise AI |
| 5 | **AI Workspace (Jupyter+VSCode+GPU)** | 클릭 한 번으로 GPU 할당된 AI 개발 환경 | MLOps 플랫폼 |

### 20.2 논문화 포인트

| # | 주제 | 학회/저널 | 핵심 Contribution |
|---|------|-----------|-------------------|
| 1 | **Heterogeneous AI Accelerator Scheduling in Kubernetes** | SoCC / Middleware | Multi-vendor GPU/NPU를 통합 스케줄링하는 프레임워크 |
| 2 | **VM-Container Unified Accelerator Orchestration** | ATC / EuroSys | KubeVirt + HAMi 통합 설계 및 평가 |
| 3 | **vNPU: Vendor-Neutral NPU Abstraction for Cloud AI** | ASPLOS / HPCA | NPU 가상화 추상화 계층 설계 |
| 4 | **OpenStack Cyborg + Kubernetes: Dual Control Plane for Accelerators** | IC2E / CLOUD | 하이브리드 제어 평면 경험 보고 |
| 5 | **Production Experience: Operating Heterogeneous GPU Cluster at Scale** | OSDI / ATC (Experience) | 실제 운영 경험, 장애 사례, 성능 데이터 |

### 20.3 AI Datacenter OS 방향성

```
오늘 (vMachine)             6개월 후                     12개월 후
────────────────────────────────────────────────────────────────────
VM Orchestration        → VM + Container 통합       → AI Datacenter OS
수동 GPU 할당            → HAMi 자동 스케줄링       → Workload-aware
NVIDIA 전용              → Multi-vendor              → vNPU abstraction
단순 모니터링            → Telemetry + Alerting      → Self-healing
고정 리소스              → Fractional + Dynamic       → Predictive scaling
VM 단위 관리             → Accelerator 단위 관리     → vNPU 단위 관리

AI Datacenter OS = Kubernetes + HAMi + KubeVirt + OKAstro Operator
                  + Vendor-neutral Accelerator Abstraction
                  + Workload-aware Auto-scaling
                  + Self-healing Infrastructure
```

---

> **문서 버전**: v1.0  
> **다음 단계**: Phase 1 MVP 구현 (HAMi + KubeVirt + Accelerator CRD + API)

from app.schemas.vmware.assessment import VMCompatibilityResult
from app.schemas.vmware.inventory import VMSummary


class VMwareCompatibilityService:
    """VMware VM의 OpenStack 마이그레이션 호환성을 평가합니다.

    평가 기준
    ---------
    - 전원 상태: suspended VM은 마이그레이션 불가
    - 게스트 OS: 알려진 OS 목록 기반 지원 여부 확인
    - CPU: vCPU 0개는 비정상
    - 메모리: 0MB는 비정상
    - 디스크: 디스크가 없으면 경고
    - 네트워크: NIC가 없으면 경고
    """

    SUPPORTED_OS_PREFIXES: list[str] = [
        "centos",
        "debian",
        "ubuntu",
        "red hat",
        "rhel",
        "suse",
        "sles",
        "oracle linux",
        "rocky linux",
        "almalinux",
        "fedora",
        "freebsd",
        "windows server",
        "windows 10",
        "windows 11",
        "windows 8",
        "windows 2012",
        "windows 2016",
        "windows 2019",
        "windows 2022",
    ]

    UNSUPPORTED_OS_PREFIXES: list[str] = [
        "solaris",
        "hp-ux",
        "aix",
        "darwin",
        "mac os",
        "os/2",
        "netware",
    ]

    def evaluate(self, vm: VMSummary) -> VMCompatibilityResult:
        issues: list[str] = []
        warnings: list[str] = []

        power_state = vm.power_state.lower()
        if power_state == "suspended":
            issues.append("VM is suspended — must be powered on before migration")

        os_supported, os_msg = self._check_os(vm.guest_os or "")
        if not os_supported:
            issues.append(os_msg)
        elif os_msg:
            warnings.append(os_msg)

        cpu_ok = True
        if vm.hardware is None or vm.hardware.cpu_count <= 0:
            cpu_ok = False
            issues.append("VM has no vCPUs configured")
        elif vm.hardware.cpu_count > 128:
            warnings.append(f"VM has {vm.hardware.cpu_count} vCPUs — may exceed OpenStack quota limits")

        mem_ok = True
        if vm.hardware is None or vm.hardware.memory_mb <= 0:
            mem_ok = False
            issues.append("VM has no memory configured")
        elif vm.hardware.memory_mb > 524288:  # 512 GB
            warnings.append(f"VM has {vm.hardware.memory_mb} MB RAM — may exceed OpenStack limits")

        disk_ok = True
        if vm.hardware is None or not vm.hardware.disks:
            disk_ok = False
            issues.append("VM has no disks attached")
        else:
            total_disk_gb = sum(d.capacity_gb for d in vm.hardware.disks)
            if total_disk_gb > 2000:
                warnings.append(f"VM has {total_disk_gb} GB total disk — large volume migration may be slow")

        net_ok = True
        if vm.hardware is None or not vm.hardware.nics:
            net_ok = False
            warnings.append("VM has no network adapters — will be isolated after migration")

        compatible = (
            power_state != "suspended"
            and os_supported
            and cpu_ok
            and mem_ok
            and disk_ok
        )

        return VMCompatibilityResult(
            vm_id=vm.id,
            vm_name=vm.name,
            compatible=compatible,
            power_state=vm.power_state,
            os_supported=os_supported,
            cpu_compatible=cpu_ok,
            memory_compatible=mem_ok,
            disk_compatible=disk_ok,
            network_compatible=net_ok,
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def _check_os(guest_os: str) -> tuple[bool, str]:
        if not guest_os:
            return False, "Guest OS not detected — unable to verify compatibility"
        os_lower = guest_os.lower()
        for unsupported in VMwareCompatibilityService.UNSUPPORTED_OS_PREFIXES:
            if unsupported in os_lower:
                return False, f"Unsupported guest OS: {guest_os}"
        for supported in VMwareCompatibilityService.SUPPORTED_OS_PREFIXES:
            if supported in os_lower:
                return True, ""
        return True, f"Unknown guest OS '{guest_os}' — compatibility not guaranteed"

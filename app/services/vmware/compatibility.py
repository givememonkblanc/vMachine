from app.schemas.vmware.assessment import CompatibilityIssueDetail, ScoredCompatibilityResult
from app.schemas.vmware.inventory import VMSummary


class VMwareCompatibilityService:
    SUPPORTED_OS_PREFIXES: list[str] = [
        "centos", "debian", "ubuntu", "red hat", "rhel",
        "suse", "sles", "oracle linux", "rocky linux", "almalinux",
        "fedora", "freebsd",
        "windows server", "windows 10", "windows 11", "windows 8",
        "windows 2012", "windows 2016", "windows 2019", "windows 2022",
    ]

    UNSUPPORTED_OS_PREFIXES: list[str] = [
        "solaris", "hp-ux", "aix", "darwin", "mac os", "os/2", "netware",
    ]

    SCORE_WEIGHTS: dict[str, float] = {
        "critical": -0.3,
        "high": -0.2,
        "medium": -0.1,
        "low": -0.05,
        "info": 0.0,
    }

    def evaluate(self, vm: VMSummary) -> ScoredCompatibilityResult:
        issues: list[CompatibilityIssueDetail] = []
        self._check_power_state(vm, issues)
        self._check_os_compat(vm, issues)
        self._check_cpu(vm, issues)
        self._check_memory(vm, issues)
        self._check_disk(vm, issues)
        self._check_network(vm, issues)
        self._check_firmware(vm, issues)
        self._check_secure_boot(vm, issues)
        self._check_vmware_tools(vm, issues)
        self._check_disk_controllers(vm, issues)
        self._check_nic_types(vm, issues)

        score = 1.0
        for issue in issues:
            if not issue.compatible:
                weight = self.SCORE_WEIGHTS.get(issue.severity, -0.1)
                score = max(0.0, score + weight)

        has_critical = any(
            i.severity == "critical" and not i.compatible for i in issues
        )
        compatible = score >= 0.5 and not has_critical

        if compatible:
            summary_text = f"Compatible (score: {score:.2f})"
        else:
            critical_count = sum(
                1 for i in issues if i.severity == "critical" and not i.compatible
            )
            summary_text = f"Incompatible — {critical_count} critical issues (score: {score:.2f})"

        return ScoredCompatibilityResult(
            vm_id=vm.id,
            vm_name=vm.name,
            compatible=compatible,
            score=round(score, 2),
            issues=issues,
            summary=summary_text,
        )

    @staticmethod
    def _add_issue(
        issues: list[CompatibilityIssueDetail],
        severity: str,
        category: str,
        message: str,
        compatible: bool = False,
    ) -> None:
        issues.append(
            CompatibilityIssueDetail(
                severity=severity,
                category=category,
                message=message,
                compatible=compatible,
            )
        )

    @staticmethod
    def _check_power_state(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        power = vm.power_state.lower()
        if power == "suspended":
            VMwareCompatibilityService._add_issue(
                issues, "critical", "os",
                "VM is suspended — must be powered on before migration",
            )

    @staticmethod
    def _check_os_compat(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        guest_os = vm.guest_os or ""
        if not guest_os:
            VMwareCompatibilityService._add_issue(
                issues, "high", "os",
                "Guest OS not detected — unable to verify compatibility",
            )
            return
        os_lower = guest_os.lower()
        for unsupported in VMwareCompatibilityService.UNSUPPORTED_OS_PREFIXES:
            if unsupported in os_lower:
                VMwareCompatibilityService._add_issue(
                    issues, "critical", "os",
                    f"Unsupported guest OS: {guest_os}",
                )
                return
        for supported in VMwareCompatibilityService.SUPPORTED_OS_PREFIXES:
            if supported in os_lower:
                return
        VMwareCompatibilityService._add_issue(
            issues, "low", "os",
            f"Unknown guest OS '{guest_os}' — compatibility not guaranteed",
            compatible=True,
        )

    @staticmethod
    def _check_cpu(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if vm.hardware is None or vm.hardware.cpu_count <= 0:
            VMwareCompatibilityService._add_issue(
                issues, "critical", "cpu",
                "VM has no vCPUs configured",
            )
        elif vm.hardware.cpu_count > 128:
            VMwareCompatibilityService._add_issue(
                issues, "low", "cpu",
                f"VM has {vm.hardware.cpu_count} vCPUs — may exceed OpenStack quota limits",
                compatible=True,
            )

    @staticmethod
    def _check_memory(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if vm.hardware is None or vm.hardware.memory_mb <= 0:
            VMwareCompatibilityService._add_issue(
                issues, "critical", "memory",
                "VM has no memory configured",
            )
        elif vm.hardware.memory_mb > 524288:
            VMwareCompatibilityService._add_issue(
                issues, "low", "memory",
                f"VM has {vm.hardware.memory_mb} MB RAM — may exceed OpenStack limits",
                compatible=True,
            )

    @staticmethod
    def _check_disk(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if vm.hardware is None or not vm.hardware.disks:
            VMwareCompatibilityService._add_issue(
                issues, "high", "disk",
                "VM has no disks attached",
            )
        else:
            total = sum(d.capacity_gb for d in vm.hardware.disks)
            if total > 2000:
                VMwareCompatibilityService._add_issue(
                    issues, "low", "disk",
                    f"VM has {total} GB total disk — large volume migration may be slow",
                    compatible=True,
                )

    @staticmethod
    def _check_network(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if vm.hardware is None or not vm.hardware.nics:
            VMwareCompatibilityService._add_issue(
                issues, "low", "network",
                "VM has no network adapters — will be isolated after migration",
                compatible=True,
            )

    @staticmethod
    def _check_firmware(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        fw = vm.firmware
        if fw and fw.lower() == "efi":
            VMwareCompatibilityService._add_issue(
                issues, "medium", "firmware",
                "VM uses EFI/UEFI firmware — requires OpenStack UEFI support (hw_firmware_type=uefi)",
                compatible=True,
            )

    @staticmethod
    def _check_secure_boot(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if vm.secure_boot_enabled:
            VMwareCompatibilityService._add_issue(
                issues, "high", "firmware",
                "Secure Boot is enabled — requires OpenStack with UEFI + hw_firmware_type=uefi + secure boot support",
            )

    @staticmethod
    def _check_vmware_tools(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        status = vm.vmware_tools_status
        if not status:
            return
        s_lower = status.lower()
        if "notinstalled" in s_lower or "notrunning" in s_lower:
            VMwareCompatibilityService._add_issue(
                issues, "medium", "vmware_tools",
                f"VMware Tools status: {status} — guest IP detection and clean shutdown may be affected",
                compatible=True,
            )

    @staticmethod
    def _check_disk_controllers(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        controllers = vm.disk_controller_types
        if not controllers:
            return
        seen: set[str] = set()
        for ctype in controllers:
            ctype_lower = ctype.lower()
            if ctype_lower in seen:
                continue
            seen.add(ctype_lower)
            if ctype_lower in ("ide",):
                VMwareCompatibilityService._add_issue(
                    issues, "high", "disk_controller",
                    f"Disk controller type '{ctype}' may not be supported in OpenStack — consider converting to virtio/scsi",
                )
            elif ctype_lower in ("lsilogic",):
                VMwareCompatibilityService._add_issue(
                    issues, "low", "disk_controller",
                    f"Disk controller type '{ctype}' is legacy but generally compatible",
                    compatible=True,
                )
            elif ctype_lower in ("nvme",):
                VMwareCompatibilityService._add_issue(
                    issues, "medium", "disk_controller",
                    f"Disk controller type '{ctype}' requires OpenStack with NVMe emulation support",
                    compatible=True,
                )

    @staticmethod
    def _check_nic_types(vm: VMSummary, issues: list[CompatibilityIssueDetail]) -> None:
        if not vm.hardware or not vm.hardware.nics:
            return
        seen: set[str] = set()
        for nic in vm.hardware.nics:
            ntype = nic.nic_type
            if not ntype or ntype in seen:
                continue
            seen.add(ntype)
            if ntype == "e1000":
                VMwareCompatibilityService._add_issue(
                    issues, "low", "nic",
                    "NIC type 'e1000' is legacy — consider upgrading to vmxnet3 or virtio",
                    compatible=True,
                )
            elif ntype == "vmxnet2":
                VMwareCompatibilityService._add_issue(
                    issues, "medium", "nic",
                    "NIC type 'vmxnet2' requires OpenStack with vmxnet3 support — consider converting to virtio",
                    compatible=True,
                )
            elif ntype == "sriov":
                VMwareCompatibilityService._add_issue(
                    issues, "medium", "nic",
                    "NIC type 'sriov' requires OpenStack SR-IOV support — passthrough configuration needed",
                    compatible=True,
                )
            elif ntype == "unknown":
                VMwareCompatibilityService._add_issue(
                    issues, "medium", "nic",
                    "Unknown NIC type detected — compatibility not guaranteed",
                    compatible=True,
                )


__all__ = ["VMwareCompatibilityService"]

"""Kubernetes Pod, Deployment, Service CRUD 서비스"""


from app.clients.kubernetes.connection import KubernetesClientFactory
from app.common.exceptions.base import AppException, KubernetesIntegrationException
from app.schemas.kubernetes import (
    ContainerSummary,
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentScaleRequest,
    DeploymentSummary,
    K8sClusterInfo,
    PodCreateRequest,
    PodListResponse,
    PodSummary,
    ServiceCreateRequest,
    ServiceListResponse,
    ServiceSummary,
)


class KubernetesService:
    """Kubernetes 리소스(Pod, Deployment, Service) CRUD를 제공하는 서비스"""

    def __init__(self, factory: KubernetesClientFactory) -> None:
        self.factory = factory

    def list_pods(self, namespace: str | None = None) -> PodListResponse:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            resp = core.list_namespaced_pod(namespace=ns)
            items = [self._serialize_pod(pod) for pod in resp.items]
            return PodListResponse(items=items)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to list pods: {exc}") from exc

    def get_pod(self, name: str, namespace: str | None = None) -> PodSummary:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            pod = core.read_namespaced_pod(name=name, namespace=ns)
            return self._serialize_pod(pod)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to get pod '{name}': {exc}") from exc

    def create_pod(self, payload: PodCreateRequest) -> PodSummary:
        ns = payload.namespace or self.factory.settings.kubernetes_namespace
        try:
            import kubernetes.client as k8s_client

            labels = payload.labels or {"app": payload.name}
            ports = [k8s_client.V1ContainerPort(container_port=payload.port)] if payload.port else None
            container = k8s_client.V1Container(
                name=payload.name,
                image=payload.image,
                ports=ports,
            )

            body = k8s_client.V1Pod(
                metadata=k8s_client.V1ObjectMeta(name=payload.name, namespace=ns, labels=labels),
                spec=k8s_client.V1PodSpec(containers=[container]),
            )

            core = self.factory.create_core_api()
            pod = core.create_namespaced_pod(namespace=ns, body=body)
            return self._serialize_pod(pod)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to create pod '{payload.name}': {exc}") from exc

    def delete_pod(self, name: str, namespace: str | None = None) -> None:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            core.delete_namespaced_pod(name=name, namespace=ns)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to delete pod '{name}': {exc}") from exc

    def list_deployments(self, namespace: str | None = None) -> DeploymentListResponse:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            apps = self.factory.create_apps_api()
            resp = apps.list_namespaced_deployment(namespace=ns)
            items = [self._serialize_deployment(dep) for dep in resp.items]
            return DeploymentListResponse(items=items)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to list deployments: {exc}") from exc

    def get_deployment(self, name: str, namespace: str | None = None) -> DeploymentSummary:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            apps = self.factory.create_apps_api()
            dep = apps.read_namespaced_deployment(name=name, namespace=ns)
            return self._serialize_deployment(dep)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to get deployment '{name}': {exc}") from exc

    def create_deployment(self, payload: DeploymentCreateRequest) -> DeploymentSummary:
        ns = payload.namespace or self.factory.settings.kubernetes_namespace
        try:
            import kubernetes.client as k8s_client

            labels = payload.labels or {"app": payload.name}
            ports = [k8s_client.V1ContainerPort(container_port=payload.port)] if payload.port else None
            container = k8s_client.V1Container(
                name=payload.name,
                image=payload.image,
                ports=ports,
            )

            body = k8s_client.V1Deployment(
                metadata=k8s_client.V1ObjectMeta(name=payload.name, namespace=ns, labels=labels),
                spec=k8s_client.V1DeploymentSpec(
                    replicas=payload.replicas,
                    selector=k8s_client.V1LabelSelector(match_labels=labels),
                    template=k8s_client.V1PodTemplateSpec(
                        metadata=k8s_client.V1ObjectMeta(labels=labels),
                        spec=k8s_client.V1PodSpec(containers=[container]),
                    ),
                ),
            )

            apps = self.factory.create_apps_api()
            dep = apps.create_namespaced_deployment(namespace=ns, body=body)
            return self._serialize_deployment(dep)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to create deployment '{payload.name}': {exc}") from exc

    def delete_deployment(self, name: str, namespace: str | None = None) -> None:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            apps = self.factory.create_apps_api()
            apps.delete_namespaced_deployment(name=name, namespace=ns)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to delete deployment '{name}': {exc}") from exc

    def scale_deployment(self, name: str, payload: DeploymentScaleRequest, namespace: str | None = None) -> DeploymentSummary:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            import kubernetes.client as k8s_client

            scale_body = k8s_client.V1Scale(spec=k8s_client.V1ScaleSpec(replicas=payload.replicas))
            apps = self.factory.create_apps_api()
            apps.patch_namespaced_deployment_scale(name=name, namespace=ns, body=scale_body)
            dep = apps.read_namespaced_deployment(name=name, namespace=ns)
            return self._serialize_deployment(dep)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to scale deployment '{name}': {exc}") from exc

    def list_services(self, namespace: str | None = None) -> ServiceListResponse:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            resp = core.list_namespaced_service(namespace=ns)
            items = [self._serialize_service(svc) for svc in resp.items]
            return ServiceListResponse(items=items)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to list services: {exc}") from exc

    def get_service(self, name: str, namespace: str | None = None) -> ServiceSummary:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            svc = core.read_namespaced_service(name=name, namespace=ns)
            return self._serialize_service(svc)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to get service '{name}': {exc}") from exc

    def create_service(self, payload: ServiceCreateRequest) -> ServiceSummary:
        ns = payload.namespace or self.factory.settings.kubernetes_namespace
        try:
            import kubernetes.client as k8s_client

            target_port = payload.target_port or payload.port
            body = k8s_client.V1Service(
                metadata=k8s_client.V1ObjectMeta(name=payload.name, namespace=ns),
                spec=k8s_client.V1ServiceSpec(
                    type=payload.type,
                    ports=[k8s_client.V1ServicePort(port=payload.port, target_port=target_port)],
                    selector=payload.selector or {"app": payload.name},
                ),
            )

            core = self.factory.create_core_api()
            svc = core.create_namespaced_service(namespace=ns, body=body)
            return self._serialize_service(svc)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to create service '{payload.name}': {exc}") from exc

    def delete_service(self, name: str, namespace: str | None = None) -> None:
        ns = namespace or self.factory.settings.kubernetes_namespace
        try:
            core = self.factory.create_core_api()
            core.delete_namespaced_service(name=name, namespace=ns)
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to delete service '{name}': {exc}") from exc

    def get_cluster_info(self) -> K8sClusterInfo:
        try:
            core = self.factory.create_core_api()
            nodes = core.list_node()
            namespaces = core.list_namespace()
            
            import kubernetes.client as k8s_client
            version_api = k8s_client.VersionApi()
            version_info = version_api.get_code()
            server_version = version_info.git_version

            return K8sClusterInfo(
                node_count=len(nodes.items),
                namespaces=[ns.metadata.name for ns in namespaces.items],
                version=server_version,
            )
        except AppException:
            raise
        except Exception as exc:
            raise KubernetesIntegrationException(f"Failed to get cluster info: {exc}") from exc

    @staticmethod
    def _serialize_pod(pod: object) -> PodSummary:
        metadata = getattr(pod, "metadata", None)
        spec = getattr(pod, "spec", None)
        status = getattr(pod, "status", None)

        name = getattr(metadata, "name", "")
        namespace = getattr(metadata, "namespace", "")
        labels = getattr(metadata, "labels", None) or {}
        created = getattr(metadata, "creation_timestamp", None)
        created_str = created.isoformat() if created and hasattr(created, "isoformat") else str(created) if created else None

        pod_status = getattr(status, "phase", "Unknown")
        pod_ip = getattr(status, "pod_ip", None)
        node_name = getattr(spec, "node_name", None)

        containers_raw = getattr(spec, "containers", []) or []
        containers = []
        for c in containers_raw:
            c_name = getattr(c, "name", "")
            c_image = getattr(c, "image", "")
            c_ports_raw = getattr(c, "port", None) or getattr(c, "ports", []) or []
            c_ports = []
            for p in c_ports_raw:
                cp = getattr(p, "container_port", None) or getattr(p, "port", None)
                if cp is not None:
                    c_ports.append(int(cp))
            containers.append(ContainerSummary(name=c_name, image=c_image, ports=c_ports))

        return PodSummary(
            name=name,
            namespace=namespace,
            status=pod_status,
            node=node_name,
            pod_ip=pod_ip,
            created=created_str,
            containers=containers,
            labels=dict(labels),
        )

    @staticmethod
    def _serialize_deployment(dep: object) -> DeploymentSummary:
        metadata = getattr(dep, "metadata", None)
        spec = getattr(dep, "spec", None)
        status = getattr(dep, "status", None)

        name = getattr(metadata, "name", "")
        namespace = getattr(metadata, "namespace", "")
        created = getattr(metadata, "creation_timestamp", None)
        created_str = created.isoformat() if created and hasattr(created, "isoformat") else str(created) if created else None

        replicas = getattr(spec, "replicas", 0) or 0
        strategy_obj = getattr(spec, "strategy", None)
        strategy = "RollingUpdate"
        if strategy_obj:
            strategy = getattr(strategy_obj, "type", "RollingUpdate") or "RollingUpdate"

        ready_replicas = getattr(status, "ready_replicas", 0) or 0
        available_replicas = getattr(status, "available_replicas", 0) or 0

        return DeploymentSummary(
            name=name,
            namespace=namespace,
            replicas=replicas,
            ready_replicas=ready_replicas,
            available_replicas=available_replicas,
            strategy=strategy,
            created=created_str,
        )

    @staticmethod
    def _serialize_service(svc: object) -> ServiceSummary:
        metadata = getattr(svc, "metadata", None)
        spec = getattr(svc, "spec", None)

        name = getattr(metadata, "name", "")
        namespace = getattr(metadata, "namespace", "")
        created = getattr(metadata, "creation_timestamp", None)
        created_str = created.isoformat() if created and hasattr(created, "isoformat") else str(created) if created else None

        svc_type = getattr(spec, "type", "ClusterIP") or "ClusterIP"
        cluster_ip = getattr(spec, "cluster_ip", None)

        ports_raw = getattr(spec, "ports", []) or []
        ports = []
        for p in ports_raw:
            port_info = {
                "port": getattr(p, "port", None),
                "target_port": str(getattr(p, "target_port", "")),
                "protocol": getattr(p, "protocol", "TCP"),
            }
            ports.append(port_info)

        return ServiceSummary(
            name=name,
            namespace=namespace,
            type=svc_type,
            cluster_ip=cluster_ip,
            ports=ports,
            created=created_str,
        )

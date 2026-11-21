"""Kubernetes observation and explicitly gated local scaling operations."""
from __future__ import annotations

import re

from .config import settings

CONFIRMATION = "I_APPROVE_LOCAL_CLUSTER_SCALING"


def _client():
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise RuntimeError("Install Kubernetes support with: uv sync --extra kubernetes") from exc
    try:
        config.load_kube_config()
    except Exception:  # noqa: BLE001 - fall back to in-cluster credentials for read-only use
        config.load_incluster_config()
    return client


def _check_scope(namespace: str, deployment_name: str) -> None:
    if namespace not in settings.k8s_allowed_namespaces:
        raise ValueError(f"Namespace '{namespace}' is not in SCALETEST_K8S_ALLOWED_NAMESPACES.")
    if deployment_name not in settings.k8s_allowed_deployments:
        raise ValueError(f"Deployment '{deployment_name}' is not in SCALETEST_K8S_ALLOWED_DEPLOYMENTS.")


def _check_mutation(confirmation: str) -> None:
    if not settings.enable_k8s_mutations:
        raise PermissionError("Cluster mutations are disabled. Set SCALETEST_ENABLE_K8S_MUTATIONS=true only for a disposable local demo cluster.")
    if confirmation != CONFIRMATION:
        raise PermissionError(f"Explicit confirmation required: pass confirmation='{CONFIRMATION}'.")


def _check_local_context() -> str:
    from kubernetes import config

    try:
        config.load_kube_config()
        _, active = config.list_kube_config_contexts()
    except Exception as exc:
        raise PermissionError(f"Could not verify the active kubeconfig context: {exc}") from exc
    context_name = active.get("name") if active else None
    if context_name not in settings.k8s_allowed_contexts:
        raise PermissionError(
            f"Active context '{context_name}' is not allowlisted. Allowed contexts: {sorted(settings.k8s_allowed_contexts)}. "
            "Use a dedicated local Kind/Minikube context."
        )
    return context_name


def _deployment_summary(item) -> dict:
    return {
        "name": item.metadata.name,
        "namespace": item.metadata.namespace,
        "generation": item.metadata.generation,
        "desired_replicas": item.spec.replicas or 0,
        "ready_replicas": item.status.ready_replicas or 0,
        "available_replicas": item.status.available_replicas or 0,
        "updated_replicas": item.status.updated_replicas or 0,
        "containers": [
            {
                "name": container.name,
                "resources": container.resources.to_dict() if container.resources else {},
            }
            for container in item.spec.template.spec.containers
        ],
    }


def inspect_deployment_scaling(
    namespace: str = "scaletest-demo",
    deployment_name: str = "scaletest-demo",
) -> dict:
    """Read deployment replica/resource state and matching HPA configuration."""
    try:
        _check_scope(namespace, deployment_name)
        client = _client()
        deployment = client.AppsV1Api().read_namespaced_deployment(deployment_name, namespace)
        hpas = client.AutoscalingV2Api().list_namespaced_horizontal_pod_autoscaler(namespace).items
        matching = [
            {
                "name": hpa.metadata.name,
                "min_replicas": hpa.spec.min_replicas,
                "max_replicas": hpa.spec.max_replicas,
                "target": hpa.spec.scale_target_ref.name,
                "metrics": [
                    {
                        "type": metric.type,
                        "resource": metric.resource.name if metric.resource else None,
                        "target_type": metric.resource.target.type if metric.resource else None,
                        "average_utilization": metric.resource.target.average_utilization if metric.resource else None,
                    }
                    for metric in (hpa.spec.metrics or [])
                ],
            }
            for hpa in hpas
            if hpa.spec.scale_target_ref.name == deployment_name
        ]
        return {"available": True, "deployment": _deployment_summary(deployment), "autoscalers": matching}
    except Exception as exc:  # noqa: BLE001 - Kubernetes client errors vary by API operation
        return {"available": False, "error": str(exc)}


def set_horizontal_scaling(
    namespace: str,
    deployment_name: str,
    min_replicas: int,
    max_replicas: int,
    confirmation: str,
) -> dict:
    """Adjust the matching HPA replica range. This changes only allowlisted demo deployments."""
    try:
        _check_mutation(confirmation)
        _check_scope(namespace, deployment_name)
        context_name = _check_local_context()
        if not (1 <= min_replicas <= max_replicas <= 10):
            raise ValueError("Require 1 <= min_replicas <= max_replicas <= 10.")
        client = _client()
        hpa_api = client.AutoscalingV2Api()
        hpas = hpa_api.list_namespaced_horizontal_pod_autoscaler(namespace).items
        matches = [hpa for hpa in hpas if hpa.spec.scale_target_ref.name == deployment_name]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one HPA targeting '{deployment_name}', found {len(matches)}.")
        hpa = matches[0]
        patched = hpa_api.patch_namespaced_horizontal_pod_autoscaler(
            hpa.metadata.name,
            namespace,
            {"spec": {"minReplicas": min_replicas, "maxReplicas": max_replicas}},
        )
        return {
            "changed": True,
            "operation": "horizontal_scaling",
            "context": context_name,
            "hpa": patched.metadata.name,
            "namespace": namespace,
            "deployment": deployment_name,
            "min_replicas": patched.spec.min_replicas,
            "max_replicas": patched.spec.max_replicas,
            "note": "HPA reconciles asynchronously. Verify actual replicas and metrics with inspect_local_deployment_scaling; Metrics Server must be healthy.",
        }
    except Exception as exc:  # noqa: BLE001 - preserve structured MCP error responses
        return {"changed": False, "error": str(exc)}


def _cpu_millicores(value: str) -> int:
    if not re.fullmatch(r"(?:[0-9]+m|[0-9]+)", value):
        raise ValueError("CPU must be an integer core value (for example 1) or millicores (for example 500m).")
    result = int(value[:-1]) if value.endswith("m") else int(value) * 1000
    if result <= 0:
        raise ValueError("CPU requests and limits must be greater than zero.")
    return result


def _memory_bytes(value: str) -> int:
    match = re.fullmatch(r"([0-9]+)(Ki|Mi|Gi)", value)
    if not match:
        raise ValueError("Memory must use Ki, Mi or Gi (for example 512Mi or 1Gi).")
    factor = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3}[match.group(2)]
    result = int(match.group(1)) * factor
    if result <= 0:
        raise ValueError("Memory requests and limits must be greater than zero.")
    return result


def set_vertical_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    cpu_request: str,
    cpu_limit: str,
    memory_request: str,
    memory_limit: str,
    confirmation: str,
) -> dict:
    """Patch an allowlisted Deployment's pod-template resources; this creates a rollout."""
    try:
        _check_mutation(confirmation)
        _check_scope(namespace, deployment_name)
        context_name = _check_local_context()
        if _cpu_millicores(cpu_limit) < _cpu_millicores(cpu_request):
            raise ValueError("CPU limit must be greater than or equal to CPU request.")
        if _memory_bytes(memory_limit) < _memory_bytes(memory_request):
            raise ValueError("Memory limit must be greater than or equal to memory request.")
        client = _client()
        apps = client.AppsV1Api()
        deployment = apps.read_namespaced_deployment(deployment_name, namespace)
        names = {container.name for container in deployment.spec.template.spec.containers}
        if container_name not in names:
            raise ValueError(f"Container '{container_name}' not found. Available containers: {sorted(names)}")
        patched = apps.patch_namespaced_deployment(
            deployment_name,
            namespace,
            {"spec": {"template": {"spec": {"containers": [{
                "name": container_name,
                "resources": {
                    "requests": {"cpu": cpu_request, "memory": memory_request},
                    "limits": {"cpu": cpu_limit, "memory": memory_limit},
                },
            }]}}}},
        )
        return {
            "changed": True,
            "operation": "vertical_resource_scaling",
            "context": context_name,
            "deployment": deployment_name,
            "namespace": namespace,
            "container": container_name,
            "resources": {
                "requests": {"cpu": cpu_request, "memory": memory_request},
                "limits": {"cpu": cpu_limit, "memory": memory_limit},
            },
            "generation": patched.metadata.generation,
            "note": "Deployment pod-template changed; Kubernetes will perform a rolling replacement. This is not in-place resizing.",
        }
    except Exception as exc:  # noqa: BLE001 - preserve structured MCP error responses
        return {"changed": False, "error": str(exc)}
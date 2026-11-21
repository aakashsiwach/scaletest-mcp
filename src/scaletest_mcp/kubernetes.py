"""Read-only Kubernetes deployment observation; requires optional Kubernetes client."""
from __future__ import annotations

def list_deployment_status(namespace: str = "default", deployment_name: str | None = None) -> dict:
    """Read replica status from a configured Kubernetes cluster."""
    try:
        from kubernetes import client, config
    except ImportError:
        return {"available": False, "error": "Install the optional dependency with: uv sync --extra kubernetes"}

    try:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()
        api = client.AppsV1Api()
        deployments = (
            [api.read_namespaced_deployment(deployment_name, namespace)]
            if deployment_name
            else api.list_namespaced_deployment(namespace).items
        )
        return {
            "available": True,
            "namespace": namespace,
            "deployments": [
                {
                    "name": item.metadata.name,
                    "desired_replicas": item.spec.replicas or 0,
                    "ready_replicas": item.status.ready_replicas or 0,
                    "available_replicas": item.status.available_replicas or 0,
                    "updated_replicas": item.status.updated_replicas or 0,
                }
                for item in deployments
            ],
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
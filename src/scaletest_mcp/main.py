from mcp.server.fastmcp import FastMCP

from .availability import (
    get_availability_report,
    mark_scaling_event,
    start_availability_monitor,
    stop_availability_monitor,
)
from .config import settings
from .engine import latest_summary, run_load_test, validate_url
from .kubernetes import (
    CONFIRMATION,
    inspect_deployment_scaling,
    set_horizontal_scaling,
    set_vertical_resources,
)

mcp = FastMCP("ScaleTest MCP")

@mcp.tool()
async def inspect_target(url: str) -> dict:
    """Validate a target URL and issue one low-impact HEAD request; does not run a load test."""
    return await validate_url(url)

@mcp.tool()
async def run_authorized_load_test(
    url: str,
    virtual_users: int = 2,
    duration_seconds: int = 10,
    authorization_confirmed: bool = False,
) -> dict:
    """Run a conservative k6 HTTP test. Explicit authorization confirmation is required."""
    return await run_load_test(url, virtual_users, duration_seconds, authorization_confirmed)

@mcp.tool()
def get_latest_test_summary() -> dict:
    """Return the latest k6 summary file, including request and latency metrics."""
    return latest_summary()

@mcp.tool()
def get_safety_limits() -> dict:
    """Show configured load-test limits and Kubernetes mutation policy."""
    return {
        "max_virtual_users": settings.max_vus,
        "max_duration_seconds": settings.max_duration_seconds,
        "max_requests_per_second_pacing": settings.max_rps,
        "private_targets_enabled": settings.allow_private_targets,
        "authorization_required_for_load_test": True,
        "kubernetes_mutations_enabled": settings.enable_k8s_mutations,
        "kubernetes_allowed_namespaces": sorted(settings.k8s_allowed_namespaces),
        "kubernetes_allowed_deployments": sorted(settings.k8s_allowed_deployments),
        "kubernetes_mutation_confirmation": CONFIRMATION,
        "public_url_can_modify_infrastructure": False,
        "availability_monitoring": {
            "min_probe_interval_ms": 250,
            "max_probe_interval_ms": 10000,
            "default_max_downtime_slo_ms": 3000,
            "max_observation_seconds": 3600,
            "max_concurrent_monitors": 3,
        },
    }

@mcp.tool()
def inspect_local_deployment_scaling(
    namespace: str = "scaletest-demo",
    deployment_name: str = "scaletest-demo",
) -> dict:
    """Read replica counts, pod resource requests/limits and HPA configuration for an allowlisted demo deployment."""
    return inspect_deployment_scaling(namespace, deployment_name)

@mcp.tool()
def change_local_horizontal_scaling(
    namespace: str,
    deployment_name: str,
    min_replicas: int,
    max_replicas: int,
    confirmation: str,
) -> dict:
    """Change the HPA replica range for an allowlisted local demo only. Requires explicit confirmation and opt-in."""
    return set_horizontal_scaling(namespace, deployment_name, min_replicas, max_replicas, confirmation)

@mcp.tool()
def change_local_vertical_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    cpu_request: str,
    cpu_limit: str,
    memory_request: str,
    memory_limit: str,
    confirmation: str,
) -> dict:
    """Change CPU/memory requests and limits on an allowlisted demo Deployment. Triggers a rollout; requires opt-in and confirmation."""
    return set_vertical_resources(
        namespace, deployment_name, container_name, cpu_request, cpu_limit,
        memory_request, memory_limit, confirmation,
    )


@mcp.tool()
def start_scaling_availability_monitor(
    url: str,
    interval_ms: int = 250,
    observation_duration_seconds: int = 180,
    max_downtime_ms: int = 3000,
    method: str = "HEAD",
    authorization_confirmed: bool = False,
) -> dict:
    """Start passive availability probes; requires authorization and does not generate load."""
    return start_availability_monitor(
        url, interval_ms, observation_duration_seconds, max_downtime_ms,
        method, authorization_confirmed,
    )

@mcp.tool()
def mark_scaling_event_timestamp(
    monitor_id: str,
    event_name: str = "scaling_change",
) -> dict:
    """Record the timestamp when an operator starts an approved scaling change."""
    return mark_scaling_event(monitor_id, event_name)

@mcp.tool()
def get_scaling_availability_report(monitor_id: str) -> dict:
    """Get the live monitor snapshot or final availability regression report."""
    return get_availability_report(monitor_id)

@mcp.tool()
def stop_scaling_availability_monitor(monitor_id: str) -> dict:
    """Stop passive monitoring and persist JSON and Markdown reports."""
    return stop_availability_monitor(monitor_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

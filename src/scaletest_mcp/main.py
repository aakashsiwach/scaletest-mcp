from mcp.server.fastmcp import FastMCP

from .config import settings
from .engine import latest_summary, run_load_test, validate_url

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
    """Show the configured limits and target network policy."""
    return {
        "max_virtual_users": settings.max_vus,
        "max_duration_seconds": settings.max_duration_seconds,
        "max_requests_per_second_pacing": settings.max_rps,
        "private_targets_enabled": settings.allow_private_targets,
        "authorization_required_for_load_test": True,
        "public_url_can_modify_infrastructure": False,
    }

def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
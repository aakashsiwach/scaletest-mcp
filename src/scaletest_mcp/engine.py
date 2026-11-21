from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import httpx

from .config import settings
from .security import TargetValidationError, validate_target

PROJECT_ROOT = Path(__file__).resolve().parents[2]
K6_SCRIPT = PROJECT_ROOT / "load" / "k6" / "http-test.js"

async def validate_url(url: str) -> dict:
    """Validate a URL and issue exactly one low-impact HEAD request."""
    try:
        safe_url = validate_target(url, settings.allow_private_targets)
    except TargetValidationError as exc:
        return {"valid": False, "error": str(exc)}

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "ScaleTest-MCP/0.1"},
        ) as client:
            response = await client.head(safe_url)
        return {
            "valid": True,
            "reachable": True,
            "url": safe_url,
            "status_code": response.status_code,
            "note": "A 405 response to HEAD may still indicate a reachable endpoint. Redirects are not followed.",
        }
    except httpx.HTTPError as exc:
        return {"valid": True, "reachable": False, "url": safe_url, "error": str(exc)}

async def run_load_test(
    url: str,
    virtual_users: int = 2,
    duration_seconds: int = 10,
    authorization_confirmed: bool = False,
) -> dict:
    """Run a capped k6 test against a target the caller is authorized to test."""
    if not authorization_confirmed:
        return {"started": False, "error": "Explicit authorization confirmation is required. Only test systems you own or have written permission to test."}
    if not 1 <= virtual_users <= settings.max_vus:
        return {"started": False, "error": f"virtual_users must be between 1 and {settings.max_vus}."}
    if not 5 <= duration_seconds <= settings.max_duration_seconds:
        return {"started": False, "error": f"duration_seconds must be between 5 and {settings.max_duration_seconds}."}

    try:
        safe_url = validate_target(url, settings.allow_private_targets)
    except TargetValidationError as exc:
        return {"started": False, "error": str(exc)}

    k6_path = shutil.which(settings.k6_binary)
    if not k6_path:
        return {"started": False, "error": "k6 was not found on PATH. Install Grafana k6 first."}
    if not K6_SCRIPT.is_file():
        return {"started": False, "error": f"k6 script is missing: {K6_SCRIPT}"}

    results_dir = PROJECT_ROOT / settings.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    summary_path = results_dir / "latest-summary.json"
    summary_path.unlink(missing_ok=True)

    command = [
        k6_path, "run", "--quiet", "--summary-export", str(summary_path),
        "-e", f"TARGET_URL={safe_url}",
        "-e", f"VUS={virtual_users}",
        "-e", f"DURATION_SECONDS={duration_seconds}",
        "-e", f"MAX_RPS={settings.max_rps}",
        str(K6_SCRIPT),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=duration_seconds + 30)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return {"started": True, "completed": False, "stopped": True, "reason": "Safety timeout reached; k6 process terminated."}
    except OSError as exc:
        return {"started": False, "error": f"Unable to start k6: {exc}"}

    summary = None
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = None
    return {
        "started": True,
        "completed": process.returncode == 0,
        "exit_code": process.returncode,
        "target": safe_url,
        "virtual_users": virtual_users,
        "duration_seconds": duration_seconds,
        "configured_max_rps": settings.max_rps,
        "summary": summary,
        "console_output": output.decode("utf-8", errors="replace")[-8000:],
        "limitation": "HTTP performance metrics do not expose or prove changes to target infrastructure. Infrastructure access is required to validate scaling.",
        "safety_note": "Review output for HTTP 403/429. Stop testing immediately if the target denies or rate-limits requests.",
    }

def latest_summary() -> dict:
    """Read the most recent k6 summary, if present."""
    summary_path = PROJECT_ROOT / settings.results_dir / "latest-summary.json"
    if not summary_path.is_file():
        return {"available": False, "message": "No test summary exists yet."}
    try:
        return {"available": True, "summary": json.loads(summary_path.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "error": str(exc)}
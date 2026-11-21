"""Passive availability monitoring around operator-marked scaling events."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .security import TargetValidationError, validate_target

MIN_INTERVAL_MS = 250
MAX_INTERVAL_MS = 10_000
MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 3_600
MAX_ACTIVE_MONITORS = 3
DEFAULT_MAX_DOWNTIME_MS = 3_000
CORRELATION_BEFORE_SECONDS = 5
CORRELATION_AFTER_SECONDS = 30

_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return round(ordered[index], 2)


def analyze_outages(
    probes: list[dict[str, Any]],
    scaling_events: list[dict[str, Any]],
    finished_monotonic: float,
) -> list[dict[str, Any]]:
    """Group consecutive failed probes and bound outage duration from probe samples."""
    outages: list[dict[str, Any]] = []
    streak: list[dict[str, Any]] = []
    last_success: dict[str, Any] | None = None

    def close_streak(recovery: dict[str, Any] | None) -> None:
        nonlocal streak
        if not streak:
            return
        first, last = streak[0], streak[-1]
        estimated_end = recovery["_started"] if recovery else finished_monotonic
        estimated_ms = max(0.0, (estimated_end - first["_started"]) * 1000)
        upper_start = last_success["_ended"] if last_success else first["_started"]
        upper_end = recovery["_ended"] if recovery else finished_monotonic
        upper_ms = max(0.0, (upper_end - upper_start) * 1000)
        nearby = []
        for event in scaling_events:
            marker = event["_mono"]
            if upper_start <= marker + CORRELATION_AFTER_SECONDS and upper_end >= marker - CORRELATION_BEFORE_SECONDS:
                nearby.append({k: event[k] for k in ("event_id", "event_name", "timestamp_utc")})
        outages.append({
            "first_failure_at_utc": first["started_at_utc"],
            "last_failure_at_utc": last["started_at_utc"],
            "recovered_at_utc": recovery["ended_at_utc"] if recovery else None,
            "open_at_monitor_end": recovery is None,
            "failed_probe_count": len(streak),
            "estimated_downtime_ms": round(estimated_ms, 2),
            "conservative_downtime_upper_bound_ms": round(upper_ms, 2),
            "recovery_probe_latency_ms": recovery["duration_ms"] if recovery else None,
            "nearby_scaling_events": nearby,
        })
        streak = []

    for probe in probes:
        if probe["success"]:
            if streak:
                close_streak(probe)
            last_success = probe
        else:
            streak.append(probe)
    if streak:
        close_streak(None)
    return outages


def evaluate_slo(outages: list[dict[str, Any]], max_downtime_ms: int, final: bool = True) -> str:
    if not final:
        return "RUNNING"
    if any(item["estimated_downtime_ms"] > max_downtime_ms for item in outages):
        return "FAIL"
    if any(item["open_at_monitor_end"] for item in outages):
        return "FAIL" if max((x["conservative_downtime_upper_bound_ms"] for x in outages), default=0) > max_downtime_ms else "INCONCLUSIVE"
    if max((x["conservative_downtime_upper_bound_ms"] for x in outages), default=0) > max_downtime_ms:
        return "INCONCLUSIVE"
    return "PASS"


def _run_monitor(session: dict[str, Any]) -> None:
    interval = session["interval_ms"] / 1000
    timeout = min(5.0, max(1.0, interval * 3))
    next_at = session["started_mono"]
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            headers={"User-Agent": "ScaleTest-MCP/0.2 availability-monitor"},
        ) as client:
            while not session["stop_event"].is_set():
                if time.monotonic() - session["started_mono"] >= session["duration_seconds"]:
                    session["stop_reason"] = "observation_window_completed"
                    break
                started = time.monotonic()
                started_utc = _utc_now()
                status: int | None = None
                error_type = None
                error_message = None
                try:
                    # HEAD avoids downloading page bodies. Use GET when the
                    # target does not implement HEAD or when that is the desired SLI.
                    with client.stream(session["method"], session["url"]) as response:
                        status = response.status_code
                        response.close()
                    success = 200 <= status < 400
                    if not success:
                        error_type, error_message = "http_status", f"HTTP {status}"
                except httpx.TimeoutException as exc:
                    success, error_type, error_message = False, "timeout", str(exc) or "Request timed out"
                except httpx.HTTPError as exc:
                    success, error_type, error_message = False, "connection_or_http_error", str(exc) or type(exc).__name__
                ended = time.monotonic()
                probe = {
                    "sequence": len(session["probes"]) + 1,
                    "started_at_utc": started_utc,
                    "ended_at_utc": _utc_now(),
                    "duration_ms": round((ended - started) * 1000, 2),
                    "success": success,
                    "status_code": status,
                    "error_type": error_type,
                    "error_message": error_message,
                    "_started": started,
                    "_ended": ended,
                }
                with session["lock"]:
                    session["probes"].append(probe)
                # An explicit deny or rate limit means stop, do not try to work around it.
                if status in {403, 429}:
                    session["stop_reason"] = f"http_{status}_received"
                    break
                next_at += interval
                now = time.monotonic()
                if next_at < now:
                    next_at = now  # skip missed ticks; never burst to catch up
                if session["stop_event"].wait(max(0.0, next_at - now)):
                    break
    except Exception as exc:  # noqa: BLE001 - capture monitor runtime errors in its report
        session["stop_reason"] = f"monitor_error: {type(exc).__name__}: {exc}"
    finally:
        session["finished_utc"] = _utc_now()
        session["finished_mono"] = time.monotonic()


def _build_report(session: dict[str, Any], final: bool) -> dict[str, Any]:
    with session["lock"]:
        probes = list(session["probes"])
        events = list(session["events"])
    finished_mono = session.get("finished_mono") or time.monotonic()
    finished_utc = session.get("finished_utc") or _utc_now()
    successes = [p for p in probes if p["success"]]
    failures = [p for p in probes if not p["success"]]
    latencies = [float(p["duration_ms"]) for p in successes]
    outages = analyze_outages(probes, events, finished_mono)
    max_estimated = max((x["estimated_downtime_ms"] for x in outages), default=0.0)
    max_upper = max((x["conservative_downtime_upper_bound_ms"] for x in outages), default=0.0)
    event_output = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]
    return {
        "monitor_id": session["monitor_id"],
        "target": session["url"],
        "method": session["method"],
        "monitor_started_at_utc": session["started_utc"],
        "monitor_finished_at_utc": finished_utc,
        "observation_duration_seconds": round(max(0.0, finished_mono - session["started_mono"]), 3),
        "probe_interval_ms": session["interval_ms"],
        "max_downtime_slo_ms": session["max_downtime_ms"],
        "final": final,
        "stop_reason": session["stop_reason"],
        "slo_result": evaluate_slo(outages, session["max_downtime_ms"], final),
        "summary": {
            "total_probes": len(probes),
            "successful_probes": len(successes),
            "failed_probes": len(failures),
            "availability_percent": round(len(successes) / len(probes) * 100, 3) if probes else None,
            "average_successful_probe_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p50_successful_probe_latency_ms": _percentile(latencies, 50),
            "p95_successful_probe_latency_ms": _percentile(latencies, 95),
            "p99_successful_probe_latency_ms": _percentile(latencies, 99),
            "outage_count": len(outages),
            "longest_estimated_downtime_ms": round(max_estimated, 2),
            "longest_conservative_downtime_upper_bound_ms": round(max_upper, 2),
            "scaling_event_count": len(events),
            "outages_near_scaling_events": sum(bool(x["nearby_scaling_events"]) for x in outages),
        },
        "scaling_events": event_output,
        "outages": outages,
        "probes": [{k: v for k, v in p.items() if not k.startswith("_")} for p in probes],
        "interpretation": (
            "An outage near a scaling marker is temporal correlation, not proof that scaling caused it. "
            "Use infrastructure events, load-balancer logs and application telemetry to establish causality."
        ),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# ScaleTest Availability Regression Report",
        "",
        f"- **Target:** {report['target']}",
        f"- **Method:** {report['method']}",
        f"- **Monitor ID:** {report['monitor_id']}",
        f"- **Started:** {report['monitor_started_at_utc']}",
        f"- **Finished:** {report['monitor_finished_at_utc']}",
        f"- **Duration:** {report['observation_duration_seconds']} seconds",
        f"- **Probe interval:** {report['probe_interval_ms']} ms",
        f"- **Maximum downtime SLO:** {report['max_downtime_slo_ms']} ms",
        f"- **SLO result:** **{report['slo_result']}**",
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Total probes | {s['total_probes']} |",
        f"| Successful probes | {s['successful_probes']} |",
        f"| Failed probes | {s['failed_probes']} |",
        f"| Availability | {s['availability_percent']}% |",
        f"| Average latency | {s['average_successful_probe_latency_ms']} ms |",
        f"| P95 latency | {s['p95_successful_probe_latency_ms']} ms |",
        f"| P99 latency | {s['p99_successful_probe_latency_ms']} ms |",
        f"| Outage count | {s['outage_count']} |",
        f"| Longest estimated downtime | {s['longest_estimated_downtime_ms']} ms |",
        f"| Longest conservative downtime bound | {s['longest_conservative_downtime_upper_bound_ms']} ms |",
        f"| Scaling markers | {s['scaling_event_count']} |",
        f"| Outages near scaling markers | {s['outages_near_scaling_events']} |",
        "",
        "## Scaling events",
        "",
    ]
    if report["scaling_events"]:
        lines.extend(f"- **{e['event_name']}** at {e['timestamp_utc']} ({e['event_id']})" for e in report["scaling_events"])
    else:
        lines.append("No scaling event marker was recorded.")
    lines.extend(["", "## Outages", ""])
    for index, outage in enumerate(report["outages"], start=1):
        related = ", ".join(e["event_name"] for e in outage["nearby_scaling_events"]) or "None"
        lines.extend([
            f"### Outage {index}",
            f"- First failure: {outage['first_failure_at_utc']}",
            f"- Recovery: {outage['recovered_at_utc'] or 'Not observed'}",
            f"- Estimated downtime: {outage['estimated_downtime_ms']} ms",
            f"- Conservative upper bound: {outage['conservative_downtime_upper_bound_ms']} ms",
            f"- Failed probes: {outage['failed_probe_count']}",
            f"- Open at monitor end: {outage['open_at_monitor_end']}",
            f"- Nearby scaling markers: {related}",
            "",
        ])
    if not report["outages"]:
        lines.append("No failed probes were observed.")
    lines.extend([
        "## Interpretation and limitations",
        "",
        report["interpretation"],
        "",
        "Probe sampling creates uncertainty around exact outage boundaries. The conservative upper bound "
        "avoids understating downtime. If it crosses the SLO but the point estimate does not, the result "
        "is INCONCLUSIVE rather than a false pass or failure.",
    ])
    if report["stop_reason"]:
        lines.append(f"Monitor stop reason: {report['stop_reason']}")
    return "\n".join(lines)


def _report_dir() -> Path:
    base = Path(settings.results_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[2] / base
    return base / "availability"


def _save_report(report: dict[str, Any]) -> dict[str, str]:
    folder = _report_dir()
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{report['monitor_id']}.json"
    markdown_path = folder / f"{report['monitor_id']}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return {"json_report": str(json_path), "markdown_report": str(markdown_path)}


def start_availability_monitor(
    url: str,
    interval_ms: int = 250,
    observation_duration_seconds: int = 180,
    max_downtime_ms: int = DEFAULT_MAX_DOWNTIME_MS,
    method: str = "HEAD",
    authorization_confirmed: bool = False,
) -> dict:
    """Start passive periodic HTTP probes. This is monitoring, not load generation."""
    if not authorization_confirmed:
        return {"started": False, "error": "Explicit authorization is required. Monitor only systems you own or have permission to probe."}
    if not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS:
        return {"started": False, "error": f"interval_ms must be between {MIN_INTERVAL_MS} and {MAX_INTERVAL_MS}."}
    if not MIN_DURATION_SECONDS <= observation_duration_seconds <= MAX_DURATION_SECONDS:
        return {"started": False, "error": f"observation_duration_seconds must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS}."}
    if not 100 <= max_downtime_ms <= 60_000:
        return {"started": False, "error": "max_downtime_ms must be between 100 and 60000."}
    method = method.upper().strip()
    if method not in {"HEAD", "GET"}:
        return {"started": False, "error": "method must be HEAD or GET."}
    try:
        safe_url = validate_target(url, settings.allow_private_targets)
    except TargetValidationError as exc:
        return {"started": False, "error": str(exc)}

    with _SESSIONS_LOCK:
        active = sum(1 for s in _SESSIONS.values() if s["thread"] and s["thread"].is_alive())
        if active >= MAX_ACTIVE_MONITORS:
            return {"started": False, "error": f"At most {MAX_ACTIVE_MONITORS} monitors may run concurrently."}
        monitor_id = uuid.uuid4().hex
        session = {
            "monitor_id": monitor_id,
            "url": safe_url,
            "method": method,
            "interval_ms": interval_ms,
            "duration_seconds": observation_duration_seconds,
            "max_downtime_ms": max_downtime_ms,
            "started_utc": _utc_now(),
            "started_mono": time.monotonic(),
            "stop_event": threading.Event(),
            "lock": threading.RLock(),
            "probes": [],
            "events": [],
            "thread": None,
            "finished_utc": None,
            "finished_mono": None,
            "stop_reason": None,
        }
        thread = threading.Thread(target=_run_monitor, args=(session,), name=f"scaletest-availability-{monitor_id[:8]}", daemon=True)
        session["thread"] = thread
        _SESSIONS[monitor_id] = session
        thread.start()
    return {
        "started": True,
        "monitor_id": monitor_id,
        "target": safe_url,
        "method": method,
        "probe_interval_ms": interval_ms,
        "expected_probe_rate_per_second": round(1000 / interval_ms, 2),
        "observation_duration_seconds": observation_duration_seconds,
        "max_downtime_slo_ms": max_downtime_ms,
        "instructions": [
            "Wait for initial probes.",
            "When the approved scaling change starts, call mark_scaling_event immediately.",
            "After the change and recovery window, call stop_availability_monitor.",
            "A 403 or 429 response automatically stops monitoring.",
        ],
        "note": "Passive probes only; no load ramp, retry loop, IP rotation or infrastructure mutation is performed.",
    }


def mark_scaling_event(monitor_id: str, event_name: str = "scaling_change") -> dict:
    """Record the operator-reported timestamp of a scaling change."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(monitor_id)
    if not session:
        return {"marked": False, "error": "Unknown monitor_id. Start a monitor first."}
    if session["finished_mono"] is not None or not session["thread"] or not session["thread"].is_alive():
        return {"marked": False, "error": "Monitor is no longer running; mark events while it is active."}
    event_name = event_name.strip()
    if not event_name or len(event_name) > 80:
        return {"marked": False, "error": "event_name must contain 1 to 80 characters."}
    event = {
        "event_id": uuid.uuid4().hex,
        "event_name": event_name,
        "timestamp_utc": _utc_now(),
        "_mono": time.monotonic(),
    }
    with session["lock"]:
        session["events"].append(event)
    return {
        "marked": True,
        "monitor_id": monitor_id,
        "event_id": event["event_id"],
        "event_name": event_name,
        "timestamp_utc": event["timestamp_utc"],
        "note": "Operator-reported marker time, not an independently verified infrastructure event.",
    }


def get_availability_report(monitor_id: str) -> dict:
    """Return a live snapshot or load a previously saved final report."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(monitor_id)
    if session:
        final = session["finished_mono"] is not None or (session["thread"] and not session["thread"].is_alive())
        report = _build_report(session, final=bool(final))
        report["report_files"] = _save_report(report) if final else None
        return report
    if not monitor_id.isalnum() or len(monitor_id) != 32:
        return {"available": False, "error": "Invalid monitor_id."}
    path = _report_dir() / f"{monitor_id}.json"
    if not path.is_file():
        return {"available": False, "error": "Monitor/report not found in this MCP server instance."}
    try:
        return {"available": True, "report": json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "error": str(exc)}


def stop_availability_monitor(monitor_id: str) -> dict:
    """Stop the monitor and persist JSON and Markdown reports."""
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(monitor_id)
    if not session:
        return {"stopped": False, "error": "Unknown monitor_id. Start a monitor first."}
    session["stop_event"].set()
    if session["thread"]:
        session["thread"].join(timeout=10)
        if session["thread"].is_alive():
            return {"stopped": False, "monitor_id": monitor_id, "error": "Monitor is still stopping; retry shortly."}
    report = _build_report(session, final=True)
    paths = _save_report(report)
    return {
        "stopped": True,
        "monitor_id": monitor_id,
        "slo_result": report["slo_result"],
        "summary": report["summary"],
        "scaling_events": report["scaling_events"],
        "outages": report["outages"],
        "report_files": paths,
        "markdown_report": _render_markdown(report),
        "interpretation": report["interpretation"],
    }

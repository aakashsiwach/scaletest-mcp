# ScaleTest MCP

Local-first MCP server for controlled HTTP load testing and local Kubernetes scaling demonstrations. Designed for Claude Code and Cursor.

## Capability boundary

With only a public URL, ScaleTest can measure HTTP response time, request failures and request throughput from the load generator. It **cannot** inspect or modify the target's CPU, memory, replica count or autoscaling policy, and cannot prove that the target infrastructure scaled. Those capabilities require explicit infrastructure and monitoring access from the service owner.

Only test systems you own or have explicit written authorization to test. Agree on concurrency, request rate and duration limits with the owner. Do not use this project to bypass WAFs, rate limits, IP blocks or other controls. Stop testing immediately on HTTP 403/429 or signs of service degradation.

## Included

- MCP server with target inspection, authorized k6 execution, test summaries and safety configuration tools.
- Conservative default envelope: at most 10 virtual users and 60 seconds per run.
- Public IP validation; loopback/private targets are blocked unless local mode is explicitly enabled.
- Optional read-only Kubernetes Deployment replica observer.
- Local sample application, Deployment, Service and HPA manifests.
- No proxy rotation, IP rotation, WAF bypass or automatic infrastructure mutations.

## Requirements

- Python 3.10+
- uv
- Grafana k6
- Claude Code or Cursor (optional MCP client)

Install k6 using the official guide: https://grafana.com/docs/k6/latest/set-up/install-k6/

## Install and run

    uv sync
    uv run scaletest

For local/private targets only, explicitly enable local mode:

Linux/macOS:

    SCALETEST_ALLOW_PRIVATE_TARGETS=true uv run scaletest

Windows PowerShell:

    $env:SCALETEST_ALLOW_PRIVATE_TARGETS="true"
    uv run scaletest

Environment variables:

- SCALETEST_MAX_VUS (default 10)
- SCALETEST_MAX_DURATION_SECONDS (default 60)
- SCALETEST_MAX_RPS (default 5; used for per-VU pacing)
- SCALETEST_ALLOW_PRIVATE_TARGETS (default false)
- SCALETEST_RESULTS_DIR (default results)

The load-test MCP tool requires authorization_confirmed=true. Set it only after receiving explicit permission from the target owner.

## MCP tools

- inspect_target(url): validates a URL and issues one low-impact HEAD request.
- run_authorized_load_test(url, virtual_users, duration_seconds, authorization_confirmed): runs a capped k6 test.
- get_latest_test_summary(): reads the latest k6 summary JSON.
- get_safety_limits(): returns the configured safety policy.

## Claude Code

For local development, launch Claude Code from the repository root; the checked-in .mcp.json starts the local MCP server using uv.

The .claude-plugin/plugin.json is a minimal plugin manifest. Validate the manifest against the current Claude Code plugin requirements before publishing it in a marketplace. The MCP server runs locally; no hosted service is required.

## Cursor

Add an MCP server entry to Cursor's MCP configuration, replacing the path with the absolute local repository path:

    {
      "mcpServers": {
        "scaletest": {
          "command": "uv",
          "args": ["--directory", "/absolute/path/to/scaletest-mcp", "run", "scaletest"]
        }
      }
    }

## Local Kubernetes scaling demo

1. Create a Kind or Minikube cluster.
2. Build the demo image from demo/app/Dockerfile as scaletest-demo:local.
3. Load the image into the local cluster.
4. Install Metrics Server compatible with the cluster.
5. Apply demo/kubernetes/deployment.yaml and demo/kubernetes/hpa.yaml.
6. Run a k6 generator inside the cluster against http://scaletest-demo.default.svc.cluster.local:8080.
7. Observe replica changes with kubectl get hpa,pods -w.

Use a separate load-generator pod and monitor its CPU/memory. A saturated generator can make scaling measurements misleading. The included Kubernetes observer is read-only; it does not mutate cluster resources.

This local experiment demonstrates real Kubernetes replica scaling without access to Defectly's infrastructure.

## Development

    uv sync --extra dev
    uv run pytest
    uv run ruff check .

This is an initial MVP. Distributed load generation, durable run history, full report export, vertical-scaling orchestration and end-to-end Kubernetes tests are follow-up work.
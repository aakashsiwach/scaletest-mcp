# ScaleTest MCP

Local-first MCP server for controlled HTTP load testing and local Kubernetes scaling demonstrations. Designed for Claude Code and Cursor.

## Capability boundary

With only a public URL, ScaleTest can measure HTTP response time, request failures and request throughput from the load generator. It **cannot** inspect or modify the target's CPU, memory, replica count or autoscaling policy, and cannot prove that the target infrastructure scaled. Those capabilities require explicit infrastructure and monitoring access from the service owner.

Only test systems you own or have explicit written authorization to test. Agree on concurrency, request rate and duration limits with the owner. Do not use this project to bypass WAFs, rate limits, IP blocks or other controls. Stop testing immediately on HTTP 403/429 or signs of service degradation.

## Features

- MCP server with URL inspection, authorized k6 execution and test summary tools.
- Conservative defaults: at most 10 virtual users and 60 seconds per test.
- Public IP validation; private/loopback targets are blocked unless local mode is explicitly enabled.
- Kubernetes deployment/HPA observation.
- Explicitly gated local horizontal scaling (HPA bounds) and vertical resource changes.
- Kubernetes mutations are disabled by default, require an exact confirmation string, and are limited to allowlisted namespaces/deployments.
- Local demo app, Deployment, Service and HPA manifests.
- No proxy rotation, IP rotation or WAF bypass.

## Requirements

- Python 3.10+
- uv
- Grafana k6
- Docker and Kind/Minikube for the Kubernetes scaling demo
- Claude Code or Cursor (optional MCP client)

Install k6: https://grafana.com/docs/k6/latest/set-up/install-k6/

## Install and run

    uv sync
    uv run scaletest

For local/private HTTP targets, explicitly enable local mode:

Linux/macOS:

    SCALETEST_ALLOW_PRIVATE_TARGETS=true uv run scaletest

Windows PowerShell:

    $env:SCALETEST_ALLOW_PRIVATE_TARGETS="true"
    uv run scaletest

## Enable local demo-cluster scaling controls

These operations are disabled by default. Use only a disposable local Kind/Minikube cluster:

Linux/macOS:

    SCALETEST_ENABLE_K8S_MUTATIONS=true uv run scaletest

Windows PowerShell:

    $env:SCALETEST_ENABLE_K8S_MUTATIONS="true"
    uv run scaletest

Install Kubernetes client support with:

    uv sync --extra kubernetes

Default mutation scope is restricted to namespace and Deployment name scaletest-demo. Override only deliberately:

- SCALETEST_K8S_ALLOWED_NAMESPACES
- SCALETEST_K8S_ALLOWED_DEPLOYMENTS

Every mutation additionally requires the exact confirmation string returned by get_safety_limits: I_APPROVE_LOCAL_CLUSTER_SCALING.

Environment variables:

- SCALETEST_MAX_VUS (default 10)
- SCALETEST_MAX_DURATION_SECONDS (default 60)
- SCALETEST_MAX_RPS (default 5; used for per-VU pacing)
- SCALETEST_ALLOW_PRIVATE_TARGETS (default false)
- SCALETEST_ENABLE_K8S_MUTATIONS (default false)
- SCALETEST_K8S_ALLOWED_NAMESPACES (default scaletest-demo)
- SCALETEST_K8S_ALLOWED_DEPLOYMENTS (default scaletest-demo)

## MCP tools

- inspect_target(url): URL validation and one low-impact HEAD request.
- run_authorized_load_test(...): capped k6 run; requires authorization_confirmed=true.
- get_latest_test_summary(): latest k6 summary JSON.
- get_safety_limits(): configured safety policies.
- inspect_local_deployment_scaling(...): read replica, resource and HPA state.
- change_local_horizontal_scaling(...): update HPA minimum/maximum replicas.
- change_local_vertical_resources(...): patch a Deployment's pod CPU/memory requests and limits.

Vertical resource changes update the pod template and trigger a Kubernetes rollout; they are not in-place resizing. Horizontal changes edit the HPA replica bounds and HPA reconciles asynchronously. Metrics Server must be healthy for CPU-based HPA to react to load.

## Claude Code

Start Claude Code from the repository root; the checked-in .mcp.json launches the local MCP server using uv. The .claude-plugin/plugin.json is a minimal plugin manifest; validate it against current Claude Code plugin requirements before publishing to a marketplace.

## Cursor

Add this MCP server to Cursor's MCP configuration, using the absolute local repository path:

    {
      "mcpServers": {
        "scaletest": {
          "command": "uv",
          "args": ["--directory", "/absolute/path/to/scaletest-mcp", "run", "scaletest"]
        }
      }
    }

## Local Kubernetes demo

1. Create a Kind or Minikube cluster.
2. Build the demo image: docker build -t scaletest-demo:local demo/app
3. Load the image into Kind: kind load docker-image scaletest-demo:local
4. Install Metrics Server compatible with your cluster.
5. Apply the manifests: kubectl apply -f demo/kubernetes/deployment.yaml and kubectl apply -f demo/kubernetes/hpa.yaml
6. Verify: kubectl -n scaletest-demo get deploy,pods,hpa
7. Configure ScaleTest with private targets and Kubernetes mutations enabled.
8. Use a separate k6 pod/job against http://scaletest-demo.scaletest-demo.svc.cluster.local:8080 to generate test traffic.
9. Change HPA bounds through the MCP tool and inspect replica count. For vertical scaling, change app CPU/memory resources through the MCP tool and watch the Deployment rollout.

Monitor the load-generator's CPU/memory separately; otherwise it can become the bottleneck. These controls only affect the allowlisted local demo cluster, never Defectly's infrastructure.

## Development

    uv sync --extra dev
    uv run pytest
    uv run ruff check .

This is an initial MVP. Distributed load generation, durable run history, automated report export and end-to-end cluster tests remain follow-up work.
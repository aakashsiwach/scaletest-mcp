# ScaleTest MCP

Local-first MCP server for controlled HTTP load testing and local Kubernetes scaling demonstrations. Designed for Claude Code and Cursor.

## Capability boundary

With only a public URL, ScaleTest can measure HTTP response time, request failures and request throughput from the load generator. It **cannot** inspect or modify the target's CPU, memory, replica count or autoscaling policy, and cannot prove that the target infrastructure scaled. Those capabilities require explicit infrastructure and monitoring access from the service owner.

Only test systems you own or have explicit written authorization to test. Agree on concurrency, request rate and duration limits with the owner. Do not use this project to bypass WAFs, rate limits, IP blocks or other controls. Stop testing immediately on HTTP 403/429 or signs of service degradation.

## Features

- MCP server with URL inspection, authorized k6 execution and test summary tools.
- Conservative defaults: at most 10 virtual users and 60 seconds per public-URL test.
- Public IP validation; private/loopback targets are blocked unless local mode is explicitly enabled.
- Kubernetes Deployment/HPA observation.
- Explicitly gated local horizontal scaling (HPA bounds) and vertical resource changes.
- Kubernetes mutations are disabled by default, require an exact confirmation string, and are restricted to allowlisted namespaces, Deployments and Kubernetes contexts.
- Claude Code plugin manifest, plugin-provided MCP server configuration and a ScaleTest usage Skill.
- MIT license. The plugin declares wildcard target hosts because the user selects the authorized HTTP test destination at runtime; this is descriptive plugin metadata, not a security allow/deny policy.
- Local demo app, Deployment, Service, HPA and in-cluster k6 Job manifests.
- No proxy rotation, IP rotation or WAF bypass.

## Requirements

- Python 3.10+
- uv
- Grafana k6 on the MCP host for direct URL tests
- Docker and Kind/Minikube for the Kubernetes scaling demo
- Claude Code or Cursor (optional MCP client)

Install k6: https://grafana.com/docs/k6/latest/set-up/install-k6/

Windows (Winget):

    winget install k6 --source winget

Open a new PowerShell window after installation. If `k6` is still not found, check the default machine install path and add it to the current session:

    $k6Path = Join-Path $env:ProgramFiles "k6"
    & (Join-Path $k6Path "k6.exe") version
    $env:Path = "$k6Path;$env:Path"
    k6 version

## Install and run

Recommended Windows PowerShell setup from the repository root:

    deactivate
    uv sync --extra dev --extra kubernetes
    uv run pytest
    uv run ruff check .

If `deactivate` is not recognized, ignore that line and run the `uv sync` command. The parent virtual environment warning means an environment from another project is active; uv will use this repository's own `.venv`.

For a runtime-only install without the optional Kubernetes tools:

    uv sync
    uv run scaletest

For local/private HTTP targets, explicitly enable local mode:

Linux/macOS:

    SCALETEST_ALLOW_PRIVATE_TARGETS=true uv run scaletest

Windows PowerShell:

    $env:SCALETEST_ALLOW_PRIVATE_TARGETS="true"
    uv run scaletest

## Claude Code plugin

Prepare the local Python environment once before launching the plugin:

    uv sync --extra dev --extra kubernetes

Then test the plugin from a local checkout:

    claude --plugin-dir .

The plugin manifest embeds its MCP server configuration and uses CLAUDE_PLUGIN_ROOT to launch the server from its installed plugin directory. It uses `uv run --no-sync` so startup does not resolve or install Python dependencies during the MCP handshake. Re-run `uv sync --extra dev --extra kubernetes` after pulling dependency changes. The plugin exposes the ScaleTest tools and the /scaletest:load-test Skill. There is intentionally no root .mcp.json, so Claude does not also parse CLAUDE_PLUGIN_ROOT as a project-level variable.

To verify a local plugin, keep the `claude --plugin-dir .` session open and run `/mcp` inside it. Also try `/scaletest:load-test`. A locally loaded plugin is session-scoped; a separate `claude mcp list` invocation outside that session does not prove whether that local plugin session loaded its bundled server.

For a reviewable plugin release, run:

    claude plugin validate . --strict

Third-party plugin submissions are handled through Anthropic's current plugin submission flow; community listing requires review and approval. Until then, users can test the plugin locally with --plugin-dir.

## Cursor

Cursor workspace configuration is provided at .cursor/mcp.json. It uses ${workspaceFolder}, which Cursor resolves to the repository root. Open the repository in Cursor and approve the ScaleTest server when prompted.

## Enable local demo-cluster scaling controls

Create a dedicated local cluster with the expected context name:

    kind create cluster --name scaletest-demo

Install Kubernetes client support:

    uv sync --extra kubernetes

Enable mutations only for this disposable local cluster:

Linux/macOS:

    SCALETEST_ENABLE_K8S_MUTATIONS=true uv run scaletest

Windows PowerShell:

    $env:SCALETEST_ENABLE_K8S_MUTATIONS="true"
    uv run scaletest

Default mutation scope is limited to:
- Kubernetes context: kind-scaletest-demo or minikube
- Namespace: scaletest-demo
- Deployment: scaletest-demo

Override only deliberately:
- SCALETEST_K8S_ALLOWED_CONTEXTS
- SCALETEST_K8S_ALLOWED_NAMESPACES
- SCALETEST_K8S_ALLOWED_DEPLOYMENTS

Every mutation additionally requires the exact confirmation string returned by get_safety_limits: I_APPROVE_LOCAL_CLUSTER_SCALING.

Environment variables:
- SCALETEST_MAX_VUS (default 10)
- SCALETEST_MAX_DURATION_SECONDS (default 60)
- SCALETEST_MAX_RPS (default 5; used for per-VU pacing)
- SCALETEST_ALLOW_PRIVATE_TARGETS (default false)
- SCALETEST_ENABLE_K8S_MUTATIONS (default false)
- SCALETEST_K8S_ALLOWED_CONTEXTS (default kind-scaletest-demo,minikube)
- SCALETEST_K8S_ALLOWED_NAMESPACES (default scaletest-demo)
- SCALETEST_K8S_ALLOWED_DEPLOYMENTS (default scaletest-demo)

## MCP tools

- inspect_target(url): URL validation and one low-impact HEAD request.
- run_authorized_load_test(...): capped k6 run; requires authorization_confirmed=true.
- get_latest_test_summary(): latest k6 summary JSON.
- get_safety_limits(): configured safety policies.
- inspect_local_deployment_scaling(...): read replica, resource and HPA state.
- change_local_horizontal_scaling(...): update HPA minimum/maximum replicas.
- change_local_vertical_resources(...): patch a Deployment's pod CPU/memory requests and limits.\n- start_scaling_availability_monitor(...): start passive HTTP probes around an approved scaling event.\n- mark_scaling_event_timestamp(...): record the operator-reported scaling-change timestamp.\n- get_scaling_availability_report(...): retrieve live or final results.\n- stop_scaling_availability_monitor(...): stop monitoring and save Markdown/JSON reports.

Vertical resource changes update the pod template and trigger a Kubernetes rollout; they are not in-place resizing. Horizontal changes edit HPA replica bounds and HPA reconciles asynchronously. Metrics Server must be healthy for CPU-based HPA to react to load.

## Local Kubernetes demo

1. Create a Kind cluster: kind create cluster --name scaletest-demo
2. Build the demo image: docker build -t scaletest-demo:local demo/app
3. Load the image: kind load docker-image scaletest-demo:local --name scaletest-demo
4. Install Metrics Server compatible with your cluster.
5. Apply demo/kubernetes/deployment.yaml and demo/kubernetes/hpa.yaml.
6. Verify: kubectl -n scaletest-demo get deploy,pods,hpa
7. Set SCALETEST_ALLOW_PRIVATE_TARGETS=true and SCALETEST_ENABLE_K8S_MUTATIONS=true before launching the MCP server.
8. Apply demo/kubernetes/k6-load.yaml to generate load inside the cluster. Watch scaling with kubectl -n scaletest-demo get hpa,pods -w.
9. Change HPA bounds with change_local_horizontal_scaling and inspect actual replica count.
10. For a vertical experiment, delete the HPA first, record baseline resources, call change_local_vertical_resources, wait for the rollout, then rerun the same workload. Reapply the HPA only after the vertical test.

Delete the k6 Job before repeating it:

    kubectl -n scaletest-demo delete job scaletest-k6-load

Monitor the load-generator's CPU/memory separately; otherwise it can become the bottleneck. These controls affect only the allowlisted local demo cluster.

## Development

    uv sync --extra dev
    uv run pytest
    uv run ruff check .

This is an initial MVP. Distributed load generation, durable run history, automated report export and end-to-end cluster tests remain follow-up work.
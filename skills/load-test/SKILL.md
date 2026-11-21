---
description: Use ScaleTest MCP to validate an authorized HTTP target, run a conservative k6 load test, inspect results, or perform isolated local Kubernetes scaling experiments.
---

# ScaleTest workflow

Use the ScaleTest MCP tools to run controlled performance checks. Prefer a small baseline before any larger run.

## Safety rules

- Never load-test a third-party or public URL without explicit permission from its owner and agreed traffic limits.
- Do not attempt to evade WAFs, IP blocks, rate limits, bot protections, or HTTP 403/429 responses.
- Never increase concurrency or duration beyond the configured limits.
- The public-URL tools measure HTTP behaviour only. They cannot modify or verify the target's infrastructure scaling.
- Kubernetes mutations are for the dedicated local demo cluster only. Never use these tools against production or a cluster that was not explicitly approved by the user.
- Before any mutation, inspect safety limits and current Deployment/HPA state. Explain the intended change and wait for explicit user approval. Pass the required confirmation token only after the user approves.
- If a target returns HTTP 403 or 429, stop the test; do not retry through other IPs or proxies.

## Public HTTP test

1. Call get_safety_limits.
2. Ask the user to confirm they own the target or have written authorization, including the target URL and allowed test envelope.
3. Call inspect_target for a single low-impact HEAD validation.
4. If validation succeeds and authorization is confirmed, run run_authorized_load_test within the configured VU and duration caps.
5. Call get_latest_test_summary and explain request count, latency percentiles, failed-request rate and any errors.
6. State clearly that an HTTP test does not prove infrastructure scaling.

## Local Kubernetes horizontal scaling experiment

1. Confirm the active cluster is the dedicated Kind/Minikube demo context.
2. Call get_safety_limits and inspect_local_deployment_scaling.
3. Confirm Metrics Server is healthy and the demo HPA targets the intended Deployment.
4. Explain the proposed HPA min/max replica change and get explicit user approval.
5. Call change_local_horizontal_scaling using the exact confirmation token returned by get_safety_limits.
6. Poll inspect_local_deployment_scaling and report desired/ready replicas. HPA reconciliation is asynchronous; do not report success until replica status confirms it.
7. For load-driven scaling, the user may apply the repository's demo/kubernetes/k6-load.yaml Job and watch HPA/pods.

## Local Kubernetes vertical resource experiment

1. Ensure the HPA is removed or suspended for the test so CPU-utilization autoscaling does not confound the vertical comparison.
2. Inspect the Deployment and record current CPU/memory requests and limits.
3. Explain that changing Deployment pod-template resources triggers a rollout; it is not in-place pod resizing.
4. Get explicit user approval.
5. Call change_local_vertical_resources with the exact confirmation token.
6. Inspect the Deployment again and report the applied values and rollout state.
7. Run the same controlled workload and compare measured results. Do not claim improved throughput unless the measurements support it.

## Reporting

Always distinguish:
- observed measurements from recommendations;
- configured resource values from actual pod readiness;
- HPA desired replicas from ready replicas;
- public HTTP performance from real infrastructure scaling.

Include the target, date/time if available, workload settings, safety limits, results, scaling changes, and any measurement limitations.

## Scaling availability regression experiment

1. Obtain explicit authorization to probe the target and agree the probe interval and observation window.
2. Call get_safety_limits and explain that the default availability SLO is 3,000 ms.
3. Call start_scaling_availability_monitor with the approved URL, interval (250 ms default), observation duration, max_downtime_ms=3000, method (HEAD by default; GET if HEAD is unsupported), and authorization_confirmed=true.
4. Save the returned monitor_id. Wait until initial probes have been recorded.
5. When the operator actually starts the scaling change, call mark_scaling_event_timestamp immediately. This records the time the marker tool was called; it does not independently verify the infrastructure event.
6. Continue monitoring through recovery, then call stop_scaling_availability_monitor.
7. Report the SLO result, availability, successful/failed probe counts, estimated and conservative outage duration, recovery time and nearby scaling markers.
8. Use get_scaling_availability_report for interim snapshots or persisted reports.

Do not run this against a third-party public target without explicit permission. The monitor is not a load test; it sends one probe per interval. A 250 ms interval means up to four requests per second. If HTTP 403 or 429 is received, stop monitoring and do not retry through alternate paths.

The report's scaling-event relationship is temporal correlation only. It does not prove scaling caused the outage. Use cloud/Kubernetes events, load-balancer logs and application telemetry for causal analysis.

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const target = __ENV.TARGET_URL;
const vus = Number(__ENV.VUS || 2);
const duration = Number(__ENV.DURATION_SECONDS || 10);
const maxRps = Number(__ENV.MAX_RPS || 5);
const denied = new Rate("scaletest_denied");

export const options = {
  scenarios: {
    controlled_http: {
      executor: "constant-vus",
      vus,
      duration: duration + "s",
      gracefulStop: "3s",
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: "rate<0.10", abortOnFail: true, delayAbortEval: "2s" }],
    scaletest_denied: [{ threshold: "rate<0.01", abortOnFail: true, delayAbortEval: "1s" }],
  },
};

export default function () {
  const response = http.get(target, {
    headers: { "User-Agent": "ScaleTest-MCP/0.1 (authorized performance test)" },
    redirects: 0,
    timeout: "8s",
    tags: { test_type: "controlled_http" },
  });

  const isDenied = response.status === 403 || response.status === 429;
  denied.add(isDenied);
  check(response, {
    "received an HTTP response": (r) => r.status > 0,
    "not forbidden": (r) => r.status !== 403,
    "not rate limited": (r) => r.status !== 429,
  });

  // Do not retry or evade denials. The threshold aborts the run when the
  // denied-response rate breaches its configured safety threshold.
  if (isDenied) return;
  sleep(Math.max(1, vus / Math.max(1, maxRps)));
}
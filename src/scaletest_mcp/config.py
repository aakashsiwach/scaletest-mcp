import os
from dataclasses import dataclass


def _csv_env(name: str, default: str) -> frozenset[str]:
    return frozenset(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    k6_binary: str = os.getenv("SCALETEST_K6_BINARY", "k6")
    max_vus: int = int(os.getenv("SCALETEST_MAX_VUS", "10"))
    max_duration_seconds: int = int(os.getenv("SCALETEST_MAX_DURATION_SECONDS", "60"))
    max_rps: int = int(os.getenv("SCALETEST_MAX_RPS", "5"))
    request_timeout_seconds: float = float(os.getenv("SCALETEST_REQUEST_TIMEOUT_SECONDS", "8"))
    allow_private_targets: bool = os.getenv("SCALETEST_ALLOW_PRIVATE_TARGETS", "false").lower() == "true"
    enable_k8s_mutations: bool = os.getenv("SCALETEST_ENABLE_K8S_MUTATIONS", "false").lower() == "true"
    k8s_allowed_namespaces: frozenset[str] = _csv_env("SCALETEST_K8S_ALLOWED_NAMESPACES", "scaletest-demo")
    k8s_allowed_deployments: frozenset[str] = _csv_env("SCALETEST_K8S_ALLOWED_DEPLOYMENTS", "scaletest-demo")
    k8s_allowed_contexts: frozenset[str] = _csv_env("SCALETEST_K8S_ALLOWED_CONTEXTS", "kind-scaletest-demo,minikube")
    results_dir: str = os.getenv("SCALETEST_RESULTS_DIR", "results")


settings = Settings()
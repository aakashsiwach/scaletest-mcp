from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    k6_binary: str = os.getenv("SCALETEST_K6_BINARY", "k6")
    max_vus: int = int(os.getenv("SCALETEST_MAX_VUS", "10"))
    max_duration_seconds: int = int(os.getenv("SCALETEST_MAX_DURATION_SECONDS", "60"))
    max_rps: int = int(os.getenv("SCALETEST_MAX_RPS", "5"))
    request_timeout_seconds: float = float(os.getenv("SCALETEST_REQUEST_TIMEOUT_SECONDS", "8"))
    allow_private_targets: bool = os.getenv("SCALETEST_ALLOW_PRIVATE_TARGETS", "false").lower() == "true"
    results_dir: str = os.getenv("SCALETEST_RESULTS_DIR", "results")

settings = Settings()
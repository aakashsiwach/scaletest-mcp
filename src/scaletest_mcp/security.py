"""Conservative URL validation for authorized performance testing."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

class TargetValidationError(ValueError):
    """Raised when a target URL is invalid or outside the configured network policy."""

def validate_target(url: str, allow_private: bool = False) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TargetValidationError("Target must be an absolute http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise TargetValidationError("Credentials embedded in target URLs are not allowed.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise TargetValidationError("Target URL contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise TargetValidationError("Target port is outside the valid range.")

    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} and not allow_private:
        raise TargetValidationError("Local targets are disabled. Set SCALETEST_ALLOW_PRIVATE_TARGETS=true for local demos.")

    try:
        records = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise TargetValidationError(f"Could not resolve target host: {host}") from exc

    addresses = {record[4][0] for record in records}
    if not addresses:
        raise TargetValidationError("Target hostname did not resolve to an address.")
    if not allow_private:
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise TargetValidationError(
                    f"Target resolves to a non-public address ({address}); private, loopback, link-local and reserved targets are blocked."
                )
    return value
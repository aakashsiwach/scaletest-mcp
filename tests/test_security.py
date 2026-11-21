import pytest

from scaletest_mcp.security import TargetValidationError, validate_target

def test_rejects_non_http_scheme():
    with pytest.raises(TargetValidationError):
        validate_target("file:///etc/passwd")

def test_rejects_embedded_credentials():
    with pytest.raises(TargetValidationError):
        validate_target("https://alice:secret@example.com")

def test_rejects_localhost_by_default():
    with pytest.raises(TargetValidationError):
        validate_target("http://localhost:8080")

def test_rejects_invalid_port():
    with pytest.raises(TargetValidationError):
        validate_target("https://example.com:99999")
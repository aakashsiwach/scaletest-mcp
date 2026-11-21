import pytest

from scaletest_mcp.kubernetes import _cpu_millicores, _memory_bytes


def test_cpu_units_are_normalized():
    assert _cpu_millicores("500m") == 500
    assert _cpu_millicores("2") == 2000


def test_memory_units_are_normalized():
    assert _memory_bytes("512Mi") == 512 * 1024 * 1024
    assert _memory_bytes("1Gi") == 1024 * 1024 * 1024


@pytest.mark.parametrize("value", ["0", "0m", "1.5", "-1", "abc"])
def test_invalid_cpu_values_are_rejected(value):
    with pytest.raises(ValueError):
        _cpu_millicores(value)


@pytest.mark.parametrize("value", ["0Mi", "512M", "1GB", "-1Gi", "abc"])
def test_invalid_memory_values_are_rejected(value):
    with pytest.raises(ValueError):
        _memory_bytes(value)
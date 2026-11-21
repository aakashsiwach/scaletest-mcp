import pytest

from scaletest_mcp.engine import run_load_test

@pytest.mark.asyncio
async def test_load_test_requires_explicit_authorization():
    result = await run_load_test(
        "https://example.com",
        virtual_users=1,
        duration_seconds=5,
        authorization_confirmed=False,
    )
    assert result["started"] is False
    assert "authorization" in result["error"].lower()

@pytest.mark.asyncio
async def test_load_test_rejects_vus_over_configured_cap():
    result = await run_load_test(
        "https://example.com",
        virtual_users=10_000,
        duration_seconds=5,
        authorization_confirmed=True,
    )
    assert result["started"] is False
    assert "virtual_users" in result["error"]
"""Tests for GDB client wrapper — no live GDB required."""

from lablens.config import Settings
from lablens.knowledge.gdb_client import GDBClient


def test_gdb_client_not_configured():
    """GDB client gracefully handles missing config."""
    settings = Settings(
        dashscope_api_key="test",
        gdb_host=None,
    )
    client = GDBClient(settings)
    assert not client.is_configured


def test_gdb_client_configured():
    settings = Settings(
        dashscope_api_key="test",
        gdb_host="localhost",
        gdb_port=8182,
    )
    client = GDBClient(settings)
    assert client.is_configured


def test_gdb_client_connect_skips_when_not_configured():
    settings = Settings(dashscope_api_key="test", gdb_host=None)
    client = GDBClient(settings)
    # Should not raise
    client.connect()
    assert client._g is None

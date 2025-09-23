"""Pytest fixtures and configuration."""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from .test_rss_server import LocalRSSServer
except ImportError:
    try:
        from test_rss_server import LocalRSSServer
    except ImportError:
        LocalRSSServer = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def environment_isolation():
    """Automatically ensure environment isolation for all tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Set default environment variables for all tests
        default_env = {
            "RSS_MCP_CONFIG_PATH": str(tmpdir_path / "config"),
            "RSS_MCP_CACHE_PATH": str(tmpdir_path / "cache"),
            "RSS_MCP_USER": "pytest_test_user",
        }
        
        with patch.dict(os.environ, default_env):
            yield tmpdir_path


@pytest.fixture
def temp_dir(environment_isolation):
    """Get the temporary directory path from environment isolation."""
    return environment_isolation


@pytest.fixture(scope="session")
async def local_rss_server():
    """Create a local RSS server for testing."""
    if LocalRSSServer is None:
        pytest.skip("LocalRSSServer not available")

    server = LocalRSSServer()
    base_url = await server.start()
    yield server
    await server.stop()


@pytest.fixture
def test_rss_data_path():
    """Get path to test RSS data directory."""
    return Path(__file__).parent / "fixtures" / "rss_data"


@pytest.fixture
async def rss_server():
    """Create a fresh RSS server instance for each test."""
    if LocalRSSServer is None:
        pytest.skip("LocalRSSServer not available")

    server = LocalRSSServer()
    base_url = await server.start()
    yield server
    await server.stop()


@pytest.fixture
def free_port():
    """Get a free port for testing servers."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    return port

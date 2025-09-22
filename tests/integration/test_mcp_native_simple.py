"""Simple integration tests to verify MCP server functionality."""

import asyncio
import json
import os
import sys

import httpx
import pytest

from rss_mcp.config import get_config_manager
from rss_mcp.server import RSSMCPServer


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServerDirect:
    """Test MCP server directly without client library."""

    @pytest.fixture
    def test_config(self, temp_dir):
        """Create test configuration."""
        config_path = temp_dir / "config.json"
        cache_path = temp_dir / "cache"
        cache_path.mkdir(exist_ok=True)

        config_data = {
            "cache_path": str(cache_path),
            "default_fetch_interval": 3600,
            "max_entries_per_feed": 100,
            "cleanup_days": 30,
            "request_timeout": 10,
            "max_retries": 2,
            "max_concurrent_fetches": 5,
            "log_level": "INFO",
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Set environment variables
        os.environ["RSS_MCP_CONFIG_DIR"] = str(config_path.parent / "config")
        os.environ["RSS_MCP_CACHE_DIR"] = str(cache_path)

        # Create and return config - it will load automatically from env vars
        config_manager = get_config_manager()

        return config_manager.config

    @pytest.fixture
    def mcp_server(self, test_config):
        """Create MCP server instance."""
        server = RSSMCPServer()
        return server

    async def test_server_initialization(self, mcp_server):
        """Test that server initializes correctly."""
        assert mcp_server is not None
        assert mcp_server.server is not None
        assert mcp_server.storage is not None
        assert mcp_server.fetcher is not None




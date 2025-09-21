"""Simple integration tests to verify MCP server functionality."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import httpx

from rss_mcp.server import RSSMCPServer, run_http_server
from rss_mcp.config import RSSConfig, get_config_manager
from rss_mcp.storage import RSSStorage


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
            "log_level": "INFO"
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        # Set environment variables
        os.environ["RSS_MCP_CONFIG"] = str(config_path)
        os.environ["RSS_MCP_CACHE"] = str(cache_path)
        
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
    
    async def test_list_tools_handler(self, mcp_server):
        """Test list_tools handler directly."""
        # Get the list tools handler
        handler = None
        for h in mcp_server.server._tool_list_handlers:
            handler = h
            break
        
        assert handler is not None
        
        # Call the handler
        tools = await handler()
        
        assert tools is not None
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool.name for tool in tools]
        assert "list_feeds" in tool_names
        assert "add_feed" in tool_names
        assert "get_entries" in tool_names
    
    async def test_call_tool_handler(self, mcp_server):
        """Test call_tool handler directly."""
        # Get the call tool handler
        handler = None
        for h in mcp_server.server._tool_call_handlers:
            handler = h
            break
        
        assert handler is not None
        
        # Test list_feeds tool
        result = await handler("list_feeds", {})
        assert result is not None
        assert len(result) > 0
        assert result[0].type == "text"
        
        # Test add_feed tool
        add_result = await handler("add_feed", {
            "name": "test-feed",
            "urls": ["https://example.com/rss.xml"],
            "title": "Test Feed"
        })
        assert add_result is not None
        assert "Added feed" in add_result[0].text or "already exists" in add_result[0].text
        
        # Test invalid tool
        error_result = await handler("invalid_tool", {})
        assert error_result is not None
        assert "Error" in error_result[0].text
    
    async def test_feed_workflow(self, mcp_server):
        """Test complete feed workflow."""
        handler = None
        for h in mcp_server.server._tool_call_handlers:
            handler = h
            break
        
        # Add feed
        add_result = await handler("add_feed", {
            "name": "workflow-test",
            "urls": ["https://rsshub.app/github/trending/daily"],
            "title": "Workflow Test",
            "fetch_interval": 1800
        })
        assert "Added feed" in add_result[0].text
        
        # List feeds
        list_result = await handler("list_feeds", {})
        assert "workflow-test" in list_result[0].text
        
        # Add source
        source_result = await handler("add_source", {
            "feed_name": "workflow-test",
            "url": "https://rsshub.app/github/trending/weekly",
            "priority": 1
        })
        assert "Added source" in source_result[0].text
        
        # Get stats
        stats_result = await handler("get_feed_stats", {
            "feed_name": "workflow-test"
        })
        assert "workflow-test" in stats_result[0].text or "Statistics" in stats_result[0].text
        
        # Remove feed
        remove_result = await handler("remove_feed", {
            "name": "workflow-test"
        })
        assert "Removed feed" in remove_result[0].text
    
    async def test_error_handling(self, mcp_server):
        """Test error handling in tool calls."""
        handler = None
        for h in mcp_server.server._tool_call_handlers:
            handler = h
            break
        
        # Try to remove non-existent feed
        result = await handler("remove_feed", {
            "name": "does-not-exist"
        })
        assert "not found" in result[0].text.lower() or "error" in result[0].text.lower()
        
        # Try to add source to non-existent feed
        result = await handler("add_source", {
            "feed_name": "does-not-exist",
            "url": "https://example.com/rss.xml"
        })
        assert "not found" in result[0].text.lower() or "error" in result[0].text.lower()
        
        # Try missing required arguments
        result = await handler("add_feed", {
            "name": "test"
            # Missing 'urls' argument
        })
        assert "error" in result[0].text.lower()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.network
class TestMCPHTTPServerDirect:
    """Test MCP HTTP server directly."""
    
    @pytest.fixture
    async def http_server(self, temp_dir):
        """Start HTTP server and return client."""
        # Setup environment
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
            "log_level": "INFO"
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        os.environ["RSS_MCP_CONFIG"] = str(config_path)
        os.environ["RSS_MCP_CACHE"] = str(cache_path)
        
        # Start server in background
        import subprocess
        import socket
        
        # Find free port
        sock = socket.socket()
        sock.bind(('', 0))
        port = sock.getsockname()[1]
        sock.close()
        
        process = subprocess.Popen(
            [sys.executable, "-m", "rss_mcp", "serve", "http", "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy()
        )
        
        # Wait for server to start
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(base_url=base_url) as client:
            for _ in range(20):  # Try for 10 seconds
                try:
                    response = await client.get("/")
                    if response.status_code == 200:
                        break
                except:
                    pass
                await asyncio.sleep(0.5)
            
            yield client
        
        # Cleanup
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    
    async def test_http_root_endpoint(self, http_server):
        """Test HTTP root endpoint."""
        response = await http_server.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "RSS MCP Server" in data["message"]
        assert "version" in data
    
    async def test_http_list_tools(self, http_server):
        """Test HTTP list tools endpoint."""
        response = await http_server.get("/tools")
        assert response.status_code == 200
        
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) > 0
        
        # Check for expected tools
        tool_names = [tool["name"] for tool in data["tools"]]
        assert "list_feeds" in tool_names
        assert "add_feed" in tool_names
    
    async def test_http_call_tool(self, http_server):
        """Test HTTP call tool endpoint."""
        # Test list_feeds
        response = await http_server.post(
            "/call-tool",
            json={
                "name": "list_feeds",
                "arguments": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0
        
        # Test add_feed
        response = await http_server.post(
            "/call-tool",
            json={
                "name": "add_feed",
                "arguments": {
                    "name": "http-test",
                    "urls": ["https://example.com/rss.xml"],
                    "title": "HTTP Test Feed"
                }
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data
        
        # Verify feed was added
        response = await http_server.post(
            "/call-tool",
            json={
                "name": "list_feeds",
                "arguments": {}
            }
        )
        data = response.json()
        results_text = str(data["results"])
        assert "http-test" in results_text
    
    async def test_http_error_handling(self, http_server):
        """Test HTTP error handling."""
        # Test invalid tool
        response = await http_server.post(
            "/call-tool",
            json={
                "name": "invalid_tool",
                "arguments": {}
            }
        )
        # Should still return 200 but with error in results
        assert response.status_code == 200 or response.status_code == 400
        
        # Test missing arguments
        response = await http_server.post(
            "/call-tool",
            json={
                "name": "add_feed",
                "arguments": {
                    "name": "test"
                    # Missing 'urls'
                }
            }
        )
        assert response.status_code == 200 or response.status_code == 400
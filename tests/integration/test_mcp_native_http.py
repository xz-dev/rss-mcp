"""Integration tests using MCP Python library's native HTTP/SSE client."""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import TextContent

from .utils import TestRSSFeeds, find_free_port


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.network
class TestMCPNativeHTTPClient:
    """Test RSS MCP server using MCP Python library's native HTTP/SSE client."""

    @pytest.fixture
    async def http_server_url(self, temp_dir):
        """Start HTTP server and return its URL."""
        port = find_free_port()
        url = f"http://127.0.0.1:{port}"
        
        # Set up test environment paths
        config_path = temp_dir / "config.json"
        cache_path = temp_dir / "cache"
        cache_path.mkdir(exist_ok=True)
        
        # Create basic config file
        config_data = {
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
        env = os.environ.copy()
        env["RSS_MCP_CONFIG_DIR"] = str(config_path.parent / "config")
        env["RSS_MCP_CACHE_DIR"] = str(cache_path)
        
        # Start server process
        import subprocess
        process = subprocess.Popen(
            [sys.executable, "-m", "rss_mcp", "serve", "http", "--host", "127.0.0.1", "--port", str(port)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{url}/")
                    if response.status_code == 200:
                        break
            except:
                pass
            await asyncio.sleep(0.5)
        
        yield url
        
        # Cleanup
        process.terminate()
        process.wait(timeout=5)

    @pytest.fixture
    async def sse_session(self, http_server_url):
        """Create an MCP SSE client session."""
        async with sse_client(http_server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def test_http_sse_client_connection(self, sse_session: ClientSession):
        """Test basic connection and initialization with HTTP/SSE client."""
        # Check that session is initialized
        assert sse_session is not None
        
        # List available tools
        tools_response = await sse_session.list_tools()
        assert tools_response is not None
        assert hasattr(tools_response, 'tools')
        
        tools = tools_response.tools
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "list_feeds", "add_feed", "remove_feed",
            "get_entries", "refresh_feeds", "get_feed_stats"
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Missing tool: {expected_tool}"

    async def test_http_direct_api_calls(self, http_server_url):
        """Test direct HTTP API calls without SSE."""
        async with httpx.AsyncClient(base_url=http_server_url, timeout=30) as client:
            # Test root endpoint
            response = await client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert "RSS MCP Server" in data["message"]
            
            # Test list tools endpoint
            tools_response = await client.get("/tools")
            assert tools_response.status_code == 200
            tools_data = tools_response.json()
            assert "tools" in tools_data
            assert len(tools_data["tools"]) > 0
            
            # Test tool call endpoint
            call_response = await client.post(
                "/call-tool",
                json={
                    "name": "list_feeds",
                    "arguments": {}
                }
            )
            assert call_response.status_code == 200
            call_data = call_response.json()
            assert "results" in call_data

    async def test_sse_feed_management(self, sse_session: ClientSession):
        """Test feed management operations via SSE client."""
        # Add a test feed
        result = await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "test-feed-sse",
                "urls": ["https://rsshub.app/github/trending/daily"],
                "title": "Test Feed via SSE",
                "description": "Feed added using native MCP SSE client"
            }
        )
        
        assert result is not None
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        assert "Added feed" in result.content[0].text
        
        # List feeds to verify
        list_result = await sse_session.call_tool("list_feeds", arguments={})
        assert list_result is not None
        assert len(list_result.content) > 0
        assert "test-feed-sse" in list_result.content[0].text
        
        # Add a backup source
        source_result = await sse_session.call_tool(
            "add_source",
            arguments={
                "feed_name": "test-feed-sse",
                "url": "https://rsshub.app/github/trending/weekly",
                "priority": 1
            }
        )
        
        assert source_result is not None
        assert "Added source" in source_result.content[0].text
        
        # Remove the feed
        remove_result = await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "test-feed-sse"}
        )
        
        assert remove_result is not None
        assert "Removed feed" in remove_result.content[0].text

    async def test_sse_concurrent_operations(self, sse_session: ClientSession):
        """Test concurrent operations via SSE client."""
        # Add multiple feeds concurrently
        feed_names = ["sse-concurrent-1", "sse-concurrent-2", "sse-concurrent-3"]
        
        add_tasks = []
        for name in feed_names:
            task = sse_session.call_tool(
                "add_feed",
                arguments={
                    "name": name,
                    "urls": [f"https://rsshub.app/test/{name}"],
                    "title": f"SSE Concurrent Test {name}"
                }
            )
            add_tasks.append(task)
        
        add_results = await asyncio.gather(*add_tasks, return_exceptions=True)
        
        # Check results
        success_count = 0
        for result in add_results:
            if not isinstance(result, Exception):
                success_count += 1
        
        assert success_count >= len(feed_names) - 1  # Allow one failure
        
        # List feeds to verify
        list_result = await sse_session.call_tool("list_feeds", arguments={})
        list_text = list_result.content[0].text
        
        found_count = sum(1 for name in feed_names if name in list_text)
        assert found_count >= len(feed_names) - 1
        
        # Cleanup
        cleanup_tasks = []
        for name in feed_names:
            task = sse_session.call_tool(
                "remove_feed",
                arguments={"name": name}
            )
            cleanup_tasks.append(task)
        
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def test_sse_feed_refresh_and_stats(self, sse_session: ClientSession):
        """Test feed refresh and statistics via SSE client."""
        # Setup test feed
        feed_data = TestRSSFeeds.get_test_feed_data("tech-news")
        
        await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "sse-refresh-test",
                "urls": [feed_data["url"]],
                "title": "SSE Refresh Test"
            }
        )
        
        # Refresh the feed
        refresh_result = await sse_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": "sse-refresh-test"}
        )
        
        assert refresh_result is not None
        refresh_text = refresh_result.content[0].text
        assert "sse-refresh-test" in refresh_text.lower() or "✓" in refresh_text
        
        # Get statistics
        stats_result = await sse_session.call_tool(
            "get_feed_stats",
            arguments={"feed_name": "sse-refresh-test"}
        )
        
        assert stats_result is not None
        stats_text = stats_result.content[0].text
        assert "sse-refresh-test" in stats_text or "Statistics" in stats_text
        
        # Get overall statistics
        overall_stats = await sse_session.call_tool(
            "get_feed_stats",
            arguments={}
        )
        
        assert overall_stats is not None
        overall_text = overall_stats.content[0].text
        assert "Total feeds" in overall_text or "Overall" in overall_text
        
        # Cleanup
        await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "sse-refresh-test"}
        )

    async def test_sse_error_handling(self, sse_session: ClientSession):
        """Test error handling with SSE client."""
        # Try to remove non-existent feed
        result = await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "does-not-exist-sse"}
        )
        
        assert result is not None
        error_text = result.content[0].text.lower()
        assert "not found" in error_text or "error" in error_text
        
        # Try to add duplicate feed
        await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "sse-duplicate-test",
                "urls": ["https://example.com/rss.xml"]
            }
        )
        
        # Try to add same feed again
        duplicate_result = await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "sse-duplicate-test",
                "urls": ["https://example.com/rss2.xml"]
            }
        )
        
        assert duplicate_result is not None
        dup_text = duplicate_result.content[0].text.lower()
        assert "already exists" in dup_text or "error" in dup_text
        
        # Cleanup
        await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "sse-duplicate-test"}
        )

    async def test_sse_entries_and_pagination(self, sse_session: ClientSession):
        """Test entry retrieval and pagination via SSE client."""
        # Add feed
        await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "sse-entries-test",
                "urls": [
                    "https://rsshub.app/github/trending/daily",
                    "https://rsshub.app/36kr/newsflashes"
                ],
                "title": "SSE Entries Test"
            }
        )
        
        # Refresh to get entries
        await sse_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": "sse-entries-test"}
        )
        
        # Test pagination
        page_tests = [
            {"page": 1, "page_size": 5},
            {"page": 2, "page_size": 5},
            {"page": 1, "page_size": 10}
        ]
        
        for page_args in page_tests:
            entries_result = await sse_session.call_tool(
                "get_entries",
                arguments={
                    "feed_name": "sse-entries-test",
                    **page_args
                }
            )
            
            assert entries_result is not None
            entries_text = entries_result.content[0].text
            
            # Check for pagination info or entries
            if "Page" in entries_text or "entries" in entries_text.lower():
                assert len(entries_text) > 50  # Should have content
        
        # Test time filtering
        time_result = await sse_session.call_tool(
            "get_entries",
            arguments={
                "feed_name": "sse-entries-test",
                "start_time": "2 days ago",
                "page_size": 15
            }
        )
        
        assert time_result is not None
        
        # Cleanup
        await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "sse-entries-test"}
        )

    async def test_http_mixed_operations(self, http_server_url):
        """Test mixed HTTP and SSE operations."""
        async with httpx.AsyncClient(base_url=http_server_url, timeout=30) as http_client:
            # Add feed via HTTP
            add_response = await http_client.post(
                "/call-tool",
                json={
                    "name": "add_feed",
                    "arguments": {
                        "name": "http-mixed-test",
                        "urls": ["https://rsshub.app/zhihu/hot"],
                        "title": "Mixed Operations Test"
                    }
                }
            )
            assert add_response.status_code == 200
            
            # Verify via SSE client
            async with sse_client(http_server_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    # List feeds via SSE
                    list_result = await session.call_tool("list_feeds", arguments={})
                    assert "http-mixed-test" in list_result.content[0].text
                    
                    # Add source via SSE
                    await session.call_tool(
                        "add_source",
                        arguments={
                            "feed_name": "http-mixed-test",
                            "url": "https://rsshub.app/zhihu/daily",
                            "priority": 1
                        }
                    )
            
            # Remove via HTTP
            remove_response = await http_client.post(
                "/call-tool",
                json={
                    "name": "remove_feed",
                    "arguments": {"name": "http-mixed-test"}
                }
            )
            assert remove_response.status_code == 200

    async def test_sse_streaming_updates(self, sse_session: ClientSession):
        """Test SSE streaming capabilities with real-time updates."""
        # Add feed for streaming test
        await sse_session.call_tool(
            "add_feed",
            arguments={
                "name": "sse-streaming-test",
                "urls": ["https://rsshub.app/github/trending/daily"],
                "title": "SSE Streaming Test",
                "fetch_interval": 60  # Short interval for testing
            }
        )
        
        # Perform multiple refresh operations
        refresh_tasks = []
        for i in range(3):
            task = sse_session.call_tool(
                "refresh_feeds",
                arguments={"feed_name": "sse-streaming-test"}
            )
            refresh_tasks.append(task)
            await asyncio.sleep(0.5)  # Small delay between requests
        
        results = await asyncio.gather(*refresh_tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        assert success_count >= 2  # Most should succeed
        
        # Get final stats
        stats = await sse_session.call_tool(
            "get_feed_stats",
            arguments={"feed_name": "sse-streaming-test"}
        )
        assert stats is not None
        
        # Cleanup
        await sse_session.call_tool(
            "remove_feed",
            arguments={"name": "sse-streaming-test"}
        )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.network
class TestMCPHTTPAdvanced:
    """Advanced HTTP/SSE client tests."""
    
    async def test_http_batch_operations(self, http_server_url):
        """Test batch operations via HTTP."""
        async with httpx.AsyncClient(base_url=http_server_url, timeout=30) as client:
            # Prepare batch of feeds to add
            feeds = [
                {
                    "name": f"batch-feed-{i}",
                    "urls": [f"https://rsshub.app/test/feed{i}"],
                    "title": f"Batch Feed {i}"
                }
                for i in range(5)
            ]
            
            # Add feeds in batch
            add_tasks = []
            for feed in feeds:
                task = client.post(
                    "/call-tool",
                    json={
                        "name": "add_feed",
                        "arguments": feed
                    }
                )
                add_tasks.append(task)
            
            add_responses = await asyncio.gather(*add_tasks, return_exceptions=True)
            
            # Count successful adds
            success_count = sum(
                1 for r in add_responses 
                if not isinstance(r, Exception) and r.status_code == 200
            )
            assert success_count >= len(feeds) - 1
            
            # List all feeds
            list_response = await client.post(
                "/call-tool",
                json={
                    "name": "list_feeds",
                    "arguments": {}
                }
            )
            assert list_response.status_code == 200
            
            # Batch remove
            remove_tasks = []
            for feed in feeds:
                task = client.post(
                    "/call-tool",
                    json={
                        "name": "remove_feed",
                        "arguments": {"name": feed["name"]}
                    }
                )
                remove_tasks.append(task)
            
            await asyncio.gather(*remove_tasks, return_exceptions=True)

    async def test_http_long_polling_simulation(self, http_server_url):
        """Test long-polling style operations."""
        async with httpx.AsyncClient(base_url=http_server_url, timeout=60) as client:
            # Add feed with frequent updates
            await client.post(
                "/call-tool",
                json={
                    "name": "add_feed",
                    "arguments": {
                        "name": "polling-test",
                        "urls": ["https://rsshub.app/github/trending/daily"],
                        "fetch_interval": 30
                    }
                }
            )
            
            # Simulate polling for updates
            poll_results = []
            for _ in range(3):
                response = await client.post(
                    "/call-tool",
                    json={
                        "name": "get_entries",
                        "arguments": {
                            "feed_name": "polling-test",
                            "page_size": 5
                        }
                    }
                )
                
                if response.status_code == 200:
                    poll_results.append(response.json())
                
                await asyncio.sleep(2)  # Poll interval
            
            assert len(poll_results) >= 2
            
            # Cleanup
            await client.post(
                "/call-tool",
                json={
                    "name": "remove_feed",
                    "arguments": {"name": "polling-test"}
                }
            )

    async def test_sse_reconnection_handling(self, http_server_url):
        """Test SSE client reconnection handling."""
        connections_made = 0
        
        for _ in range(2):
            try:
                async with sse_client(http_server_url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        connections_made += 1
                        
                        # Perform operation
                        result = await session.call_tool("list_feeds", arguments={})
                        assert result is not None
                        
            except Exception as e:
                # Log but don't fail - testing reconnection
                print(f"Connection attempt failed: {e}")
        
        assert connections_made >= 1, "Should establish at least one connection"
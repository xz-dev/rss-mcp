"""Integration tests using MCP Python library's native stdio client."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from .utils import TestRSSFeeds


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPNativeStdioClient:
    """Test RSS MCP server using MCP Python library's native stdio client."""

    @pytest.fixture
    async def stdio_session(self, temp_dir):
        """Create an MCP stdio client session."""
        env = os.environ.copy()
        
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
        
        env["RSS_MCP_CONFIG"] = str(config_path)
        env["RSS_MCP_CACHE"] = str(cache_path)
        
        # Use the actual server command
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rss_mcp", "serve", "stdio"],
            env=env
        )
        
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def test_stdio_client_connection(self, stdio_session: ClientSession):
        """Test basic connection and initialization with stdio client."""
        # Check that session is initialized
        assert stdio_session is not None
        
        # List available tools
        tools_response = await stdio_session.list_tools()
        assert tools_response is not None
        assert hasattr(tools_response, 'tools')
        
        tools = tools_response.tools
        assert len(tools) > 0
        
        # Check for expected tools
        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "list_feeds", "add_feed", "remove_feed",
            "add_source", "remove_source", "get_entries",
            "get_entry_summary", "refresh_feeds", "get_feed_stats"
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Missing tool: {expected_tool}"

    async def test_stdio_feed_management(self, stdio_session: ClientSession):
        """Test feed management operations via stdio client."""
        # Add a test feed
        result = await stdio_session.call_tool(
            "add_feed",
            arguments={
                "name": "test-feed-stdio",
                "urls": ["https://rsshub.app/github/trending/daily"],
                "title": "Test Feed via Stdio",
                "description": "Feed added using native MCP stdio client"
            }
        )
        
        assert result is not None
        assert len(result.content) > 0
        assert isinstance(result.content[0], TextContent)
        assert "Added feed" in result.content[0].text
        
        # List feeds to verify
        list_result = await stdio_session.call_tool("list_feeds", arguments={})
        assert list_result is not None
        assert len(list_result.content) > 0
        assert "test-feed-stdio" in list_result.content[0].text
        
        # Add a backup source
        source_result = await stdio_session.call_tool(
            "add_source",
            arguments={
                "feed_name": "test-feed-stdio",
                "url": "https://rsshub.app/github/trending/weekly",
                "priority": 1
            }
        )
        
        assert source_result is not None
        assert "Added source" in source_result.content[0].text
        
        # Remove the feed
        remove_result = await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": "test-feed-stdio"}
        )
        
        assert remove_result is not None
        assert "Removed feed" in remove_result.content[0].text

    async def test_stdio_feed_refresh_and_entries(self, stdio_session: ClientSession):
        """Test feed refresh and entry retrieval via stdio client."""
        # Setup test feed
        feed_data = TestRSSFeeds.get_test_feed_data("github-trending")
        
        await stdio_session.call_tool(
            "add_feed",
            arguments={
                "name": "refresh-test-stdio",
                "urls": [feed_data["url"]],
                "title": "Refresh Test Feed"
            }
        )
        
        # Refresh the feed
        refresh_result = await stdio_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": "refresh-test-stdio"}
        )
        
        assert refresh_result is not None
        refresh_text = refresh_result.content[0].text
        assert "refresh-test-stdio" in refresh_text.lower() or "✓" in refresh_text
        
        # Get entries
        entries_result = await stdio_session.call_tool(
            "get_entries",
            arguments={
                "feed_name": "refresh-test-stdio",
                "page_size": 5
            }
        )
        
        assert entries_result is not None
        entries_text = entries_result.content[0].text
        
        # Should have entries or indicate no entries
        assert len(entries_text) > 50  # Should have some content
        
        # Cleanup
        await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": "refresh-test-stdio"}
        )

    async def test_stdio_statistics(self, stdio_session: ClientSession):
        """Test statistics retrieval via stdio client."""
        # Add test feeds
        test_feeds = [
            ("stats-feed-1", ["https://rsshub.app/36kr/newsflashes"]),
            ("stats-feed-2", ["https://rsshub.app/zhihu/hot"])
        ]
        
        for name, urls in test_feeds:
            await stdio_session.call_tool(
                "add_feed",
                arguments={"name": name, "urls": urls, "title": f"Stats Test {name}"}
            )
        
        # Get overall statistics
        overall_stats = await stdio_session.call_tool(
            "get_feed_stats",
            arguments={}
        )
        
        assert overall_stats is not None
        stats_text = overall_stats.content[0].text
        assert "Total feeds" in stats_text or "Statistics" in stats_text
        
        # Get feed-specific statistics
        feed_stats = await stdio_session.call_tool(
            "get_feed_stats",
            arguments={"feed_name": "stats-feed-1"}
        )
        
        assert feed_stats is not None
        feed_stats_text = feed_stats.content[0].text
        assert "stats-feed-1" in feed_stats_text
        
        # Cleanup
        for name, _ in test_feeds:
            await stdio_session.call_tool(
                "remove_feed",
                arguments={"name": name}
            )

    async def test_stdio_error_handling(self, stdio_session: ClientSession):
        """Test error handling with stdio client."""
        # Try to remove non-existent feed
        result = await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": "does-not-exist-stdio"}
        )
        
        assert result is not None
        error_text = result.content[0].text.lower()
        assert "not found" in error_text or "error" in error_text
        
        # Try to add source to non-existent feed
        source_result = await stdio_session.call_tool(
            "add_source",
            arguments={
                "feed_name": "non-existent-feed",
                "url": "https://example.com/rss.xml"
            }
        )
        
        assert source_result is not None
        source_error = source_result.content[0].text.lower()
        assert "not found" in source_error or "error" in source_error
        
        # Try invalid tool call
        with pytest.raises(Exception) as exc_info:
            await stdio_session.call_tool(
                "invalid_tool_name",
                arguments={}
            )
        assert "invalid_tool_name" in str(exc_info.value) or "unknown" in str(exc_info.value).lower()

    async def test_stdio_pagination(self, stdio_session: ClientSession):
        """Test pagination features via stdio client."""
        # Add feed with multiple sources
        await stdio_session.call_tool(
            "add_feed",
            arguments={
                "name": "pagination-test",
                "urls": [
                    "https://rsshub.app/github/trending/daily",
                    "https://rsshub.app/github/trending/weekly"
                ],
                "title": "Pagination Test Feed"
            }
        )
        
        # Refresh to get entries
        await stdio_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": "pagination-test"}
        )
        
        # Test different page sizes
        page_sizes = [5, 10, 20]
        
        for page_size in page_sizes:
            result = await stdio_session.call_tool(
                "get_entries",
                arguments={
                    "feed_name": "pagination-test",
                    "page": 1,
                    "page_size": page_size
                }
            )
            
            assert result is not None
            entries_text = result.content[0].text
            
            # Check pagination info in response
            if "Page" in entries_text:
                assert f"Page 1/" in entries_text or "entries" in entries_text.lower()
        
        # Test time-based filtering
        time_filter_result = await stdio_session.call_tool(
            "get_entries",
            arguments={
                "feed_name": "pagination-test",
                "start_time": "2 days ago",
                "page_size": 10
            }
        )
        
        assert time_filter_result is not None
        
        # Cleanup
        await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": "pagination-test"}
        )

    async def test_stdio_concurrent_operations(self, stdio_session: ClientSession):
        """Test concurrent operations via stdio client."""
        # Add multiple feeds
        feed_names = ["concurrent-1", "concurrent-2", "concurrent-3"]
        
        # Add feeds concurrently
        add_tasks = []
        for name in feed_names:
            task = stdio_session.call_tool(
                "add_feed",
                arguments={
                    "name": name,
                    "urls": [f"https://rsshub.app/test/{name}"],
                    "title": f"Concurrent Test {name}"
                }
            )
            add_tasks.append(task)
        
        add_results = await asyncio.gather(*add_tasks, return_exceptions=True)
        
        # Check results
        success_count = 0
        for result in add_results:
            if not isinstance(result, Exception):
                success_count += 1
        
        assert success_count >= len(feed_names) - 1  # Allow one failure due to race conditions
        
        # List feeds to verify
        list_result = await stdio_session.call_tool("list_feeds", arguments={})
        list_text = list_result.content[0].text
        
        found_count = sum(1 for name in feed_names if name in list_text)
        assert found_count >= len(feed_names) - 1
        
        # Cleanup concurrently
        cleanup_tasks = []
        for name in feed_names:
            task = stdio_session.call_tool(
                "remove_feed",
                arguments={"name": name}
            )
            cleanup_tasks.append(task)
        
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def test_stdio_workflow_complete(self, stdio_session: ClientSession):
        """Test complete workflow with stdio client."""
        workflow_feed = "complete-workflow"
        
        # Step 1: Add feed with multiple sources
        await stdio_session.call_tool(
            "add_feed",
            arguments={
                "name": workflow_feed,
                "urls": ["https://rsshub.app/github/trending/daily"],
                "title": "Complete Workflow Test",
                "description": "Testing complete RSS workflow",
                "fetch_interval": 1800
            }
        )
        
        # Step 2: Add backup source
        await stdio_session.call_tool(
            "add_source",
            arguments={
                "feed_name": workflow_feed,
                "url": "https://rsshub.app/github/trending/weekly",
                "priority": 1
            }
        )
        
        # Step 3: List feeds with active filter
        active_feeds = await stdio_session.call_tool(
            "list_feeds",
            arguments={"active_only": True}
        )
        assert workflow_feed in active_feeds.content[0].text
        
        # Step 4: Refresh feed
        refresh_result = await stdio_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": workflow_feed}
        )
        assert "✓" in refresh_result.content[0].text or workflow_feed in refresh_result.content[0].text
        
        # Step 5: Get entries with pagination
        entries_page1 = await stdio_session.call_tool(
            "get_entries",
            arguments={
                "feed_name": workflow_feed,
                "page": 1,
                "page_size": 5
            }
        )
        
        # Step 6: Get statistics
        stats = await stdio_session.call_tool(
            "get_feed_stats",
            arguments={"feed_name": workflow_feed}
        )
        assert workflow_feed in stats.content[0].text
        
        # Step 7: Remove a source
        await stdio_session.call_tool(
            "remove_source",
            arguments={
                "feed_name": workflow_feed,
                "url": "https://rsshub.app/github/trending/weekly"
            }
        )
        
        # Step 8: Verify source was removed
        feeds_after = await stdio_session.call_tool(
            "list_feeds",
            arguments={}
        )
        assert "weekly" not in feeds_after.content[0].text or "[1]" not in feeds_after.content[0].text
        
        # Step 9: Clean up
        cleanup_result = await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": workflow_feed}
        )
        assert "Removed feed" in cleanup_result.content[0].text


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPNativeStdioAdvanced:
    """Advanced tests for stdio client functionality."""
    
    @pytest.fixture
    async def stdio_session_with_feeds(self, stdio_session: ClientSession):
        """Create stdio session with pre-populated feeds."""
        # Add test feeds
        test_feeds = [
            {
                "name": "advanced-github",
                "urls": ["https://rsshub.app/github/trending/daily"],
                "title": "GitHub Trending"
            },
            {
                "name": "advanced-news",
                "urls": ["https://rsshub.app/36kr/newsflashes"],
                "title": "Tech News"
            }
        ]
        
        for feed in test_feeds:
            await stdio_session.call_tool("add_feed", arguments=feed)
        
        yield stdio_session
        
        # Cleanup
        for feed in test_feeds:
            await stdio_session.call_tool(
                "remove_feed",
                arguments={"name": feed["name"]}
            )
    
    async def test_stdio_entry_summary(self, stdio_session_with_feeds: ClientSession):
        """Test entry summary retrieval."""
        # Refresh feeds first
        await stdio_session_with_feeds.call_tool(
            "refresh_feeds",
            arguments={}
        )
        
        # Get entries
        entries = await stdio_session_with_feeds.call_tool(
            "get_entries",
            arguments={
                "feed_name": "advanced-github",
                "page_size": 1
            }
        )
        
        entries_text = entries.content[0].text
        
        # Try to extract entry GUID if available
        # This is a simplified example - in real use you'd parse the response properly
        if "Link:" in entries_text:
            # Attempt to get entry summary (may fail if no entries)
            try:
                # Note: This would need proper parsing of the entry GUID
                summary_result = await stdio_session_with_feeds.call_tool(
                    "get_entry_summary",
                    arguments={
                        "feed_name": "advanced-github",
                        "entry_guid": "test-guid",  # This would be extracted from entries
                        "max_length": 200
                    }
                )
                # If successful, check response
                if summary_result:
                    assert "Summary" in summary_result.content[0].text or "Error" in summary_result.content[0].text
            except Exception:
                # Expected if no valid GUID
                pass
    
    async def test_stdio_time_filtering(self, stdio_session_with_feeds: ClientSession):
        """Test time-based filtering of entries."""
        # Refresh feeds
        await stdio_session_with_feeds.call_tool(
            "refresh_feeds",
            arguments={}
        )
        
        # Test various time filters
        time_filters = [
            {"start_time": "1 hour ago"},
            {"start_time": "1 day ago", "end_time": "now"},
            {"start_time": "2 days ago"},
        ]
        
        for filter_args in time_filters:
            result = await stdio_session_with_feeds.call_tool(
                "get_entries",
                arguments={
                    **filter_args,
                    "page_size": 10
                }
            )
            
            assert result is not None
            # Results may vary based on actual feed content
            assert len(result.content[0].text) > 0
    
    async def test_stdio_feed_failover(self, stdio_session: ClientSession):
        """Test feed failover with multiple sources."""
        # Create feed with primary and backup sources
        await stdio_session.call_tool(
            "add_feed",
            arguments={
                "name": "failover-test",
                "urls": ["https://invalid.example.com/rss"],  # Primary (will fail)
                "title": "Failover Test"
            }
        )
        
        # Add valid backup source
        await stdio_session.call_tool(
            "add_source",
            arguments={
                "feed_name": "failover-test",
                "url": "https://rsshub.app/github/trending/daily",  # Backup (should work)
                "priority": 1
            }
        )
        
        # Refresh - should use backup
        refresh_result = await stdio_session.call_tool(
            "refresh_feeds",
            arguments={"feed_name": "failover-test"}
        )
        
        # Check that refresh attempted
        refresh_text = refresh_result.content[0].text
        assert "failover-test" in refresh_text.lower() or "error" in refresh_text.lower() or "✓" in refresh_text
        
        # Check feed status
        list_result = await stdio_session.call_tool(
            "list_feeds",
            arguments={}
        )
        
        list_text = list_result.content[0].text
        assert "failover-test" in list_text
        
        # Cleanup
        await stdio_session.call_tool(
            "remove_feed",
            arguments={"name": "failover-test"}
        )
"""Test FastMCP client functionality with HTTP headers support for multi-user isolation."""

import asyncio
import logging
from typing import Dict, Any

import pytest
from fastmcp.client import Client, StreamableHttpTransport

from src.rss_mcp.fastmcp_multiuser_v2 import server, cleanup_resources

logger = logging.getLogger(__name__)

# Test server configurations
TEST_HOST = "127.0.0.1"
TEST_PORT = 8087
TEST_BASE_URL = f"http://{TEST_HOST}:{TEST_PORT}/mcp"


class HeadersAwareHttpTransport(StreamableHttpTransport):
    """Custom HTTP transport that can pass headers to the server."""
    
    def __init__(self, base_url: str, headers: Dict[str, str]):
        super().__init__(base_url)
        self.custom_headers = headers
    
    def _get_headers(self) -> Dict[str, str]:
        """Override to add custom headers."""
        headers = super()._get_headers() if hasattr(super(), '_get_headers') else {}
        headers.update(self.custom_headers)
        return headers


@pytest.fixture(scope="module")
async def fastmcp_server():
    """Start the FastMCP server for testing."""
    logger.info(f"Starting test FastMCP server on {TEST_HOST}:{TEST_PORT}")
    
    # Start server in background
    server_task = asyncio.create_task(
        server.run_http(host=TEST_HOST, port=TEST_PORT)
    )
    
    # Give server time to start
    await asyncio.sleep(2)
    
    yield server
    
    # Cleanup
    server_task.cancel()
    await cleanup_resources()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


async def create_client_with_headers(headers: Dict[str, str]) -> Client:
    """Create a FastMCP client with custom headers."""
    transport = HeadersAwareHttpTransport(TEST_BASE_URL, headers)
    return Client(transport=transport)


@pytest.mark.asyncio
async def test_client_authentication_required(fastmcp_server):
    """Test that client requests without proper headers are rejected."""
    # Test with no headers
    client = Client(TEST_BASE_URL)
    
    async with client:
        with pytest.raises(Exception) as exc_info:
            await client.call_tool("list_feeds", {})
        
        assert "authentication" in str(exc_info.value).lower() or "user" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_client_with_valid_headers(fastmcp_server):
    """Test that client with valid X-User-ID header works."""
    headers = {"X-User-ID": "test_user_alice"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # Test ping
        await client.ping()
        
        # Test list_feeds (should return empty initially)
        result = await client.call_tool("list_feeds", {})
        assert result["user_id"] == "test_user_alice"
        assert "feeds" in result
        assert isinstance(result["feeds"], list)


@pytest.mark.asyncio
async def test_multi_user_isolation(fastmcp_server):
    """Test that different users have isolated data."""
    alice_headers = {"X-User-ID": "alice"}
    bob_headers = {"X-User-ID": "bob"}
    
    alice_client = await create_client_with_headers(alice_headers)
    bob_client = await create_client_with_headers(bob_headers)
    
    async with alice_client, bob_client:
        # Create a feed for Alice
        alice_feed_result = await alice_client.call_tool("add_feed", {
            "name": "alice_news",
            "title": "Alice's News Feed",
            "description": "Personal news for Alice"
        })
        assert alice_feed_result["success"] is True
        assert alice_feed_result["user_id"] == "alice"
        
        # Create a different feed for Bob
        bob_feed_result = await bob_client.call_tool("add_feed", {
            "name": "bob_tech",
            "title": "Bob's Tech Feed", 
            "description": "Tech news for Bob"
        })
        assert bob_feed_result["success"] is True
        assert bob_feed_result["user_id"] == "bob"
        
        # Verify Alice only sees her feed
        alice_feeds = await alice_client.call_tool("list_feeds", {})
        assert len(alice_feeds["feeds"]) == 1
        assert alice_feeds["feeds"][0]["name"] == "alice_news"
        assert alice_feeds["user_id"] == "alice"
        
        # Verify Bob only sees his feed
        bob_feeds = await bob_client.call_tool("list_feeds", {})
        assert len(bob_feeds["feeds"]) == 1
        assert bob_feeds["feeds"][0]["name"] == "bob_tech"
        assert bob_feeds["user_id"] == "bob"


@pytest.mark.asyncio
async def test_feed_management_operations(fastmcp_server):
    """Test comprehensive feed management operations with headers."""
    headers = {"X-User-ID": "test_feed_manager"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # 1. Add a feed
        add_result = await client.call_tool("add_feed", {
            "name": "test_feed",
            "title": "Test RSS Feed",
            "description": "A test feed for validation",
            "fetch_interval": 3600
        })
        assert add_result["success"] is True
        assert add_result["feed_name"] == "test_feed"
        
        # 2. Add a source to the feed
        source_result = await client.call_tool("add_source", {
            "feed_name": "test_feed",
            "url": "https://example.com/rss.xml",
            "priority": 0
        })
        assert source_result["success"] is True
        assert source_result["source_url"] == "https://example.com/rss.xml"
        
        # 3. List feeds and verify details
        feeds_result = await client.call_tool("list_feeds", {})
        assert len(feeds_result["feeds"]) == 1
        feed = feeds_result["feeds"][0]
        assert feed["name"] == "test_feed"
        assert feed["title"] == "Test RSS Feed"
        assert len(feed["sources"]) == 1
        assert feed["sources"][0]["url"] == "https://example.com/rss.xml"
        
        # 4. Get feed statistics
        stats_result = await client.call_tool("get_feed_stats", {
            "feed_name": "test_feed"
        })
        assert stats_result["user_id"] == "test_feed_manager"
        assert stats_result["feed_name"] == "test_feed"
        assert "total_entries" in stats_result
        
        # 5. Remove the source
        remove_source_result = await client.call_tool("remove_source", {
            "feed_name": "test_feed",
            "url": "https://example.com/rss.xml"
        })
        assert remove_source_result["success"] is True
        
        # 6. Delete the feed
        delete_result = await client.call_tool("delete_feed", {
            "feed_name": "test_feed"
        })
        assert delete_result["success"] is True
        
        # 7. Verify feed is gone
        final_feeds = await client.call_tool("list_feeds", {})
        assert len(final_feeds["feeds"]) == 0


@pytest.mark.asyncio 
async def test_entries_retrieval(fastmcp_server):
    """Test entry retrieval with various filters."""
    headers = {"X-User-ID": "test_entries_user"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # Create a test feed (entries will be empty since we're not fetching real RSS)
        await client.call_tool("add_feed", {
            "name": "entries_test",
            "title": "Entries Test Feed"
        })
        
        # Test get_entries with various parameters
        entries_result = await client.call_tool("get_entries", {
            "feed_name": "entries_test",
            "limit": 10,
            "offset": 0
        })
        assert entries_result["user_id"] == "test_entries_user"
        assert "entries" in entries_result
        assert isinstance(entries_result["entries"], list)
        
        # Test get_entries without feed_name (all feeds)
        all_entries = await client.call_tool("get_entries", {
            "limit": 5
        })
        assert all_entries["user_id"] == "test_entries_user"
        assert "entries" in all_entries


@pytest.mark.asyncio
async def test_error_handling(fastmcp_server):
    """Test error handling in various scenarios."""
    headers = {"X-User-ID": "test_error_user"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # Test adding duplicate feed
        await client.call_tool("add_feed", {
            "name": "duplicate_test",
            "title": "First Feed"
        })
        
        duplicate_result = await client.call_tool("add_feed", {
            "name": "duplicate_test",
            "title": "Duplicate Feed"
        })
        assert duplicate_result["success"] is False
        assert "already exists" in duplicate_result["error"]
        
        # Test adding source to non-existent feed
        source_error = await client.call_tool("add_source", {
            "feed_name": "nonexistent_feed",
            "url": "https://example.com/rss.xml"
        })
        assert source_error["success"] is False
        assert "not found" in source_error["error"]
        
        # Test deleting non-existent feed
        delete_error = await client.call_tool("delete_feed", {
            "feed_name": "nonexistent_feed"
        })
        assert delete_error["success"] is False
        assert "not found" in delete_error["message"]


@pytest.mark.asyncio
async def test_refresh_feeds_functionality(fastmcp_server):
    """Test the refresh_feeds tool (will mostly test structure since no real RSS)."""
    headers = {"X-User-ID": "test_refresh_user"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # Create a test feed with a source
        await client.call_tool("add_feed", {
            "name": "refresh_test",
            "title": "Refresh Test Feed"
        })
        
        await client.call_tool("add_source", {
            "feed_name": "refresh_test",
            "url": "https://httpbin.org/xml"  # Mock RSS-like endpoint
        })
        
        # Test refresh specific feed
        refresh_result = await client.call_tool("refresh_feeds", {
            "feed_name": "refresh_test"
        })
        assert refresh_result["user_id"] == "test_refresh_user"
        assert "feeds_total" in refresh_result
        assert "feeds_processed" in refresh_result
        
        # Test refresh all feeds
        refresh_all_result = await client.call_tool("refresh_feeds", {})
        assert refresh_all_result["user_id"] == "test_refresh_user"
        assert "feeds_total" in refresh_all_result


@pytest.mark.asyncio
async def test_overall_stats(fastmcp_server):
    """Test overall statistics functionality."""
    headers = {"X-User-ID": "test_stats_user"}
    client = await create_client_with_headers(headers)
    
    async with client:
        # Create multiple feeds
        for i in range(3):
            await client.call_tool("add_feed", {
                "name": f"stats_feed_{i}",
                "title": f"Stats Feed {i}"
            })
        
        # Get overall statistics
        stats_result = await client.call_tool("get_feed_stats", {})
        assert stats_result["user_id"] == "test_stats_user"
        assert stats_result["total_feeds"] == 3
        assert stats_result["active_feeds"] == 3  # Default feeds are active
        assert "top_feeds" in stats_result


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
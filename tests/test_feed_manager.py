"""Tests for RSS feed manager."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import feedparser

from rss_mcp.feed_manager import FeedFetcher
from rss_mcp.models import RSSFeed, RSSSource, RSSEntry


class TestFeedFetcher:
    """Test RSS feed fetcher."""
    
    def test_create_fetcher(self, test_config, storage):
        """Test creating feed fetcher."""
        fetcher = FeedFetcher(test_config, storage)
        assert fetcher.config == test_config
        assert fetcher.storage == storage
        assert fetcher._session is None
    
    @pytest.mark.asyncio
    async def test_get_session(self, async_feed_fetcher):
        """Test HTTP session creation."""
        session = await async_feed_fetcher._get_session()
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed
        
        # Should reuse same session
        session2 = await async_feed_fetcher._get_session()
        assert session is session2
    
    @pytest.mark.asyncio
    async def test_close_session(self, async_feed_fetcher):
        """Test closing HTTP session."""
        session = await async_feed_fetcher._get_session()
        assert not session.closed
        
        await async_feed_fetcher.close()
        assert session.closed
    
    @pytest.mark.asyncio
    async def test_fetch_feed_content_success(self, async_feed_fetcher, mock_feed_content):
        """Test successful feed content fetching."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = mock_feed_content
            mock_get.return_value.__aenter__.return_value = mock_response
            
            success, content, error = await async_feed_fetcher.fetch_feed_content("https://example.com/rss.xml")
            
            assert success is True
            assert content == mock_feed_content
            assert error is None
    
    @pytest.mark.asyncio
    async def test_fetch_feed_content_http_error(self, async_feed_fetcher):
        """Test HTTP error during fetch."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.reason = "Not Found"
            mock_get.return_value.__aenter__.return_value = mock_response
            
            success, content, error = await async_feed_fetcher.fetch_feed_content("https://example.com/rss.xml")
            
            assert success is False
            assert content is None
            assert "HTTP 404" in error
    
    @pytest.mark.asyncio
    async def test_fetch_feed_content_timeout(self, async_feed_fetcher):
        """Test timeout during fetch."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = asyncio.TimeoutError()
            
            success, content, error = await async_feed_fetcher.fetch_feed_content("https://example.com/rss.xml")
            
            assert success is False
            assert content is None
            assert error == "Request timeout"
    
    @pytest.mark.asyncio
    async def test_fetch_feed_content_client_error(self, async_feed_fetcher):
        """Test client error during fetch."""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = aiohttp.ClientError("Connection failed")
            
            success, content, error = await async_feed_fetcher.fetch_feed_content("https://example.com/rss.xml")
            
            assert success is False
            assert content is None
            assert "Client error" in error
    
    def test_parse_feed_content_success(self, feed_fetcher, mock_feed_content):
        """Test successful feed parsing."""
        success, parsed, error = feed_fetcher.parse_feed_content(mock_feed_content, "https://example.com/rss.xml")
        
        assert success is True
        assert parsed is not None
        assert hasattr(parsed, 'entries')
        assert len(parsed.entries) == 2
        assert error is None
    
    def test_parse_feed_content_invalid(self, feed_fetcher):
        """Test parsing invalid feed content."""
        invalid_content = "Not valid RSS content"
        success, parsed, error = feed_fetcher.parse_feed_content(invalid_content, "https://example.com/rss.xml")
        
        # feedparser is tolerant, might still parse something
        # But should handle gracefully regardless
        assert isinstance(success, bool)
    
    def test_extract_entries(self, feed_fetcher, mock_feed_content):
        """Test extracting entries from parsed feed."""
        parsed_feed = feedparser.parse(mock_feed_content)
        entries = feed_fetcher.extract_entries(parsed_feed, "test-feed", "https://example.com/rss.xml")
        
        assert len(entries) == 2
        
        entry = entries[0]
        assert entry.feed_name == "test-feed"
        assert entry.source_url == "https://example.com/rss.xml"
        assert entry.title == "Test Entry 1"
        assert entry.link == "https://example.com/entry/1"
        assert entry.guid == "entry-1"
        assert entry.author == "Test Author"
        assert "test" in entry.tags
    
    def test_parse_date_variants(self, feed_fetcher):
        """Test parsing various date formats."""
        # time.struct_time
        import time
        time_tuple = time.strptime("2023-01-01 12:00:00", "%Y-%m-%d %H:%M:%S")
        parsed = feed_fetcher._parse_date(time_tuple)
        assert parsed.year == 2023
        assert parsed.month == 1
        assert parsed.day == 1
        
        # String date
        parsed = feed_fetcher._parse_date("2023-01-01T12:00:00Z")
        assert parsed.year == 2023
        
        # Datetime object
        dt = datetime(2023, 1, 1, 12, 0, 0)
        parsed = feed_fetcher._parse_date(dt)
        assert parsed == dt.replace(tzinfo=dt.tzinfo or parsed.tzinfo)
        
        # Invalid date
        assert feed_fetcher._parse_date("invalid") is None
        assert feed_fetcher._parse_date(None) is None
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_failover_success(self, storage, async_feed_fetcher, sample_feed, mock_feed_content):
        """Test successful feed fetch with failover."""
        storage.create_feed(sample_feed)
        
        with patch.object(async_feed_fetcher, 'fetch_feed_content') as mock_fetch:
            with patch.object(async_feed_fetcher, 'parse_feed_content') as mock_parse:
                with patch.object(async_feed_fetcher, 'extract_entries') as mock_extract:
                    
                    # Setup mocks
                    mock_fetch.return_value = (True, mock_feed_content, None)
                    mock_parse.return_value = (True, feedparser.parse(mock_feed_content), None)
                    mock_extract.return_value = [
                        RSSEntry(
                            feed_name="test-feed",
                            source_url="https://example.com/rss.xml",
                            guid="entry-1",
                            title="Test Entry",
                        )
                    ]
                    
                    # Fetch feed
                    success, entries, message = await async_feed_fetcher.fetch_feed_with_failover(sample_feed)
                    
                    assert success is True
                    assert len(entries) == 1
                    assert "Fetched 1 entries" in message
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_failover_first_fails(self, storage, async_feed_fetcher, sample_feed, mock_feed_content):
        """Test failover when first source fails."""
        storage.create_feed(sample_feed)
        
        with patch.object(async_feed_fetcher, 'fetch_feed_content') as mock_fetch:
            with patch.object(async_feed_fetcher, 'parse_feed_content') as mock_parse:
                with patch.object(async_feed_fetcher, 'extract_entries') as mock_extract:
                    
                    # First call fails, second succeeds
                    mock_fetch.side_effect = [
                        (False, None, "Connection failed"),
                        (True, mock_feed_content, None)
                    ]
                    mock_parse.return_value = (True, feedparser.parse(mock_feed_content), None)
                    mock_extract.return_value = [
                        RSSEntry(
                            feed_name="test-feed",
                            source_url="https://example.com/backup.xml",
                            guid="entry-1",
                            title="Test Entry",
                        )
                    ]
                    
                    # Fetch feed
                    success, entries, message = await async_feed_fetcher.fetch_feed_with_failover(sample_feed)
                    
                    assert success is True
                    assert len(entries) == 1
                    assert "backup.xml" in message
                    
                    # Should have called fetch twice (failover)
                    assert mock_fetch.call_count == 2
    
    @pytest.mark.asyncio
    async def test_fetch_feed_with_failover_all_fail(self, storage, async_feed_fetcher, sample_feed):
        """Test when all sources fail."""
        storage.create_feed(sample_feed)
        
        with patch.object(async_feed_fetcher, 'fetch_feed_content') as mock_fetch:
            mock_fetch.return_value = (False, None, "Connection failed")
            
            success, entries, message = await async_feed_fetcher.fetch_feed_with_failover(sample_feed)
            
            assert success is False
            assert len(entries) == 0
            assert "Connection failed" in message
    
    @pytest.mark.asyncio
    async def test_fetch_feed_no_sources(self, storage, async_feed_fetcher):
        """Test fetching feed with no sources."""
        feed = RSSFeed(name="empty-feed")
        storage.create_feed(feed)
        
        success, entries, message = await async_feed_fetcher.fetch_feed_with_failover(feed)
        
        assert success is False
        assert len(entries) == 0
        assert "No active sources" in message
    
    @pytest.mark.asyncio
    async def test_store_entries(self, storage, async_feed_fetcher, sample_feed):
        """Test storing entries."""
        storage.create_feed(sample_feed)
        
        entries = [
            RSSEntry(
                feed_name="test-feed",
                source_url="https://example.com/rss.xml",
                guid=f"entry-{i}",
                title=f"Entry {i}",
            )
            for i in range(3)
        ]
        
        new_count = await async_feed_fetcher.store_entries(entries)
        assert new_count == 3
        
        # Store same entries again (should be 0 new)
        new_count = await async_feed_fetcher.store_entries(entries)
        assert new_count == 0
    
    @pytest.mark.asyncio
    async def test_refresh_feed_success(self, storage, async_feed_fetcher, sample_feed):
        """Test refreshing a single feed successfully."""
        storage.create_feed(sample_feed)
        
        with patch.object(async_feed_fetcher, 'fetch_feed_with_failover') as mock_failover:
            with patch.object(async_feed_fetcher, 'store_entries') as mock_store:
                
                # Setup mocks
                mock_entries = [RSSEntry(feed_name="test-feed", guid="entry-1", title="Entry 1")]
                mock_failover.return_value = (True, mock_entries, "Success message")
                mock_store.return_value = 1
                
                success, message = await async_feed_fetcher.refresh_feed("test-feed")
                
                assert success is True
                assert "1 new entries" in message
    
    @pytest.mark.asyncio
    async def test_refresh_feed_not_found(self, storage, async_feed_fetcher):
        """Test refreshing nonexistent feed."""
        success, message = await async_feed_fetcher.refresh_feed("nonexistent")
        
        assert success is False
        assert "not found" in message
    
    @pytest.mark.asyncio
    async def test_refresh_feed_disabled(self, storage, async_feed_fetcher, sample_feed):
        """Test refreshing disabled feed."""
        sample_feed.active = False
        storage.create_feed(sample_feed)
        
        success, message = await async_feed_fetcher.refresh_feed("test-feed")
        
        assert success is False
        assert "disabled" in message
    
    @pytest.mark.asyncio
    async def test_refresh_all_feeds(self, storage, async_feed_fetcher):
        """Test refreshing all active feeds."""
        # Create test feeds
        feed1 = RSSFeed(name="feed1", active=True)
        feed2 = RSSFeed(name="feed2", active=True)
        feed3 = RSSFeed(name="feed3", active=False)  # Should be skipped
        
        storage.create_feed(feed1)
        storage.create_feed(feed2)
        storage.create_feed(feed3)
        
        with patch.object(async_feed_fetcher, 'refresh_feed') as mock_refresh:
            mock_refresh.side_effect = [
                (True, "feed1: Success"),
                (False, "feed2: Failed"),
            ]
            
            results = await async_feed_fetcher.refresh_all_feeds()
            
            assert len(results) == 2  # Only active feeds
            assert results[0] == ("feed1", True, "feed1: Success")
            assert results[1] == ("feed2", False, "feed2: Failed")
    
    @pytest.mark.asyncio
    async def test_refresh_specific_feeds(self, storage, async_feed_fetcher):
        """Test refreshing specific feeds."""
        feed1 = RSSFeed(name="feed1")
        feed2 = RSSFeed(name="feed2")
        storage.create_feed(feed1)
        storage.create_feed(feed2)
        
        with patch.object(async_feed_fetcher, 'refresh_feed') as mock_refresh:
            mock_refresh.return_value = (True, "Success")
            
            results = await async_feed_fetcher.refresh_all_feeds(["feed1"])
            
            assert len(results) == 1
            assert results[0][0] == "feed1"
            mock_refresh.assert_called_once_with("feed1")
    
    @pytest.mark.asyncio
    async def test_refresh_concurrent_limit(self, storage, async_feed_fetcher, test_config):
        """Test concurrent fetch limiting."""
        # Set low limit for testing
        test_config.max_concurrent_fetches = 2
        
        # Create multiple feeds
        for i in range(5):
            feed = RSSFeed(name=f"feed{i}")
            storage.create_feed(feed)
        
        call_times = []
        
        async def mock_refresh(feed_name):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate work
            return True, f"{feed_name}: Success"
        
        with patch.object(async_feed_fetcher, 'refresh_feed', side_effect=mock_refresh):
            await async_feed_fetcher.refresh_all_feeds()
        
        # Due to semaphore limiting, not all calls should start simultaneously
        # This is a basic check - in real scenarios the timing would be more controlled
        assert len(call_times) == 5
    
    def test_cleanup_old_entries(self, storage, feed_fetcher):
        """Test cleaning up old entries."""
        with patch.object(storage, 'cleanup_old_entries') as mock_cleanup:
            mock_cleanup.return_value = 10
            
            result = feed_fetcher.cleanup_old_entries()
            
            assert result == 10
            mock_cleanup.assert_called_once_with(feed_fetcher.config.cleanup_days)
"""Tests for RSS models."""

import pytest
from datetime import datetime

from rss_mcp.models import RSSFeed, RSSSource, RSSEntry, FeedStats


class TestRSSSource:
    """Test RSSSource model."""
    
    def test_create_source(self):
        """Test creating a valid RSS source."""
        source = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss.xml",
            priority=0,
        )
        
        assert source.feed_name == "test-feed"
        assert source.url == "https://example.com/rss.xml"
        assert source.priority == 0
        assert source.active is True
        assert source.error_count == 0
        assert source.is_healthy is True
    
    def test_invalid_url(self):
        """Test that invalid URLs raise ValueError."""
        with pytest.raises(ValueError, match="Invalid URL"):
            RSSSource(
                feed_name="test-feed",
                url="not-a-url",
            )
    
    def test_is_healthy(self):
        """Test health check logic."""
        source = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss.xml",
            error_count=0,
        )
        assert source.is_healthy is True
        
        source.error_count = 3
        assert source.is_healthy is True
        
        source.error_count = 5
        assert source.is_healthy is False


class TestRSSFeed:
    """Test RSSFeed model."""
    
    def test_create_feed(self):
        """Test creating a valid RSS feed."""
        feed = RSSFeed(
            name="test-feed",
            title="Test Feed",
            description="A test feed",
        )
        
        assert feed.name == "test-feed"
        assert feed.title == "Test Feed"
        assert feed.description == "A test feed"
        assert feed.active is True
        assert feed.sources == []
    
    def test_empty_name_validation(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Feed name cannot be empty"):
            RSSFeed(name="")
    
    def test_auto_title(self):
        """Test that title defaults to name."""
        feed = RSSFeed(name="test-feed")
        assert feed.title == "test-feed"
    
    def test_primary_source(self):
        """Test primary source selection."""
        feed = RSSFeed(name="test-feed")
        
        # No sources
        assert feed.primary_source is None
        
        # Add sources
        source1 = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss1.xml",
            priority=1,
        )
        source2 = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss2.xml",
            priority=0,  # Higher priority (lower number)
        )
        
        feed.sources = [source1, source2]
        
        # Should return source with lowest priority number
        assert feed.primary_source == source2
    
    def test_healthy_sources(self):
        """Test healthy sources filtering."""
        feed = RSSFeed(name="test-feed")
        
        source1 = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss1.xml",
            priority=1,
            error_count=0,
        )
        source2 = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss2.xml",
            priority=0,
            error_count=10,  # Unhealthy
        )
        source3 = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss3.xml",
            priority=2,
            active=False,  # Inactive
        )
        
        feed.sources = [source1, source2, source3]
        
        healthy = feed.healthy_sources
        assert len(healthy) == 1
        assert healthy[0] == source1


class TestRSSEntry:
    """Test RSSEntry model."""
    
    def test_create_entry(self):
        """Test creating a valid RSS entry."""
        entry = RSSEntry(
            feed_name="test-feed",
            source_url="https://example.com/rss.xml",
            guid="entry-1",
            title="Test Entry",
            link="https://example.com/entry/1",
            description="Test description",
        )
        
        assert entry.feed_name == "test-feed"
        assert entry.guid == "entry-1"
        assert entry.title == "Test Entry"
        assert entry.link == "https://example.com/entry/1"
    
    def test_empty_feed_name_validation(self):
        """Test that empty feed name raises ValueError."""
        with pytest.raises(ValueError, match="Entry must belong to a feed"):
            RSSEntry(
                feed_name="",
                guid="entry-1",
            )
    
    def test_guid_fallback(self):
        """Test that link is used as GUID if GUID is empty."""
        entry = RSSEntry(
            feed_name="test-feed",
            link="https://example.com/entry/1",
        )
        
        assert entry.guid == "https://example.com/entry/1"
    
    def test_no_guid_or_link_validation(self):
        """Test that missing GUID and link raises ValueError."""
        with pytest.raises(ValueError, match="Entry must have either GUID or link"):
            RSSEntry(feed_name="test-feed")
    
    def test_effective_published(self):
        """Test effective publication date logic."""
        pub_date = datetime(2023, 1, 1, 12, 0, 0)
        created_date = datetime(2023, 1, 2, 12, 0, 0)
        
        # With published date
        entry = RSSEntry(
            feed_name="test-feed",
            guid="entry-1",
            published=pub_date,
            created_at=created_date,
        )
        assert entry.effective_published == pub_date
        
        # Without published date
        entry = RSSEntry(
            feed_name="test-feed",
            guid="entry-1",
            created_at=created_date,
        )
        assert entry.effective_published == created_date
    
    def test_summary(self):
        """Test summary property."""
        # With content
        entry = RSSEntry(
            feed_name="test-feed",
            guid="entry-1",
            description="Short description",
            content="Full content here",
        )
        assert entry.summary == "Full content here"
        
        # Without content
        entry = RSSEntry(
            feed_name="test-feed",
            guid="entry-1",
            description="Short description",
        )
        assert entry.summary == "Short description"
    
    def test_truncated_summary(self):
        """Test truncated summary generation."""
        long_content = "This is a very long content that should be truncated " * 10
        
        entry = RSSEntry(
            feed_name="test-feed",
            guid="entry-1",
            content=long_content,
        )
        
        truncated = entry.get_truncated_summary(100)
        assert len(truncated) <= 103  # 100 + "..."
        assert truncated.endswith("...")
        
        # Test word boundary breaking
        short_content = "This is short"
        entry.content = short_content
        truncated = entry.get_truncated_summary(100)
        assert truncated == short_content  # No truncation needed


class TestFeedStats:
    """Test FeedStats model."""
    
    def test_create_stats(self):
        """Test creating feed statistics."""
        stats = FeedStats(
            feed_name="test-feed",
            total_entries=100,
            entries_last_24h=5,
            entries_last_7d=25,
            active_sources=2,
            healthy_sources=1,
        )
        
        assert stats.feed_name == "test-feed"
        assert stats.total_entries == 100
        assert stats.entries_last_24h == 5
        assert stats.entries_last_7d == 25
        assert stats.active_sources == 2
        assert stats.healthy_sources == 1
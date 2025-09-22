"""Tests using real RSS data from Caixin feed."""

import json
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import pytest

from src.rss_mcp.models import RSSEntry, RSSFeed, RSSSource
from src.rss_mcp.storage import RSSStorage


@pytest.fixture
def caixin_rss_content():
    """Load real Caixin RSS content for testing."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    caixin_file = fixtures_dir / "caixin_test_data.xml"
    
    if not caixin_file.exists():
        pytest.skip("Caixin test data not available")
    
    with open(caixin_file, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def parsed_caixin_feed(caixin_rss_content):
    """Parse the real Caixin RSS content."""
    return feedparser.parse(caixin_rss_content)


@pytest.fixture
def caixin_feed_with_source(tmp_path):
    """Create a Caixin feed with source for testing."""
    storage = RSSStorage(tmp_path)
    
    # Create feed
    feed = RSSFeed(
        name="caixin-latest",
        title="财新网 - 最新文章",
        description="财新网 - 最新文章 - Powered by RSSHub",
        active=True
    )
    
    # Create source
    source = RSSSource(
        feed_name="caixin-latest",
        url="http://10.1.1.22:1200/caixin/latest",
        active=True,
        priority=0
    )
    
    storage.create_feed(feed)
    storage.create_source(source)
    
    return storage, feed, source


class TestRealRSSDataProcessing:
    """Test processing of real RSS data."""
    
    def test_parse_caixin_rss_basic_info(self, parsed_caixin_feed):
        """Test basic RSS feed parsing."""
        feed = parsed_caixin_feed
        
        # Check feed metadata
        assert feed.feed.title == "财新网 - 最新文章"
        assert feed.feed.description == "财新网 - 最新文章 - Powered by RSSHub"
        assert feed.feed.link == "https://www.caixin.com/"
        assert "RSSHub" in feed.feed.generator
        
        # Check entries
        assert len(feed.entries) > 0
        print(f"Found {len(feed.entries)} entries in the RSS feed")
    
    def test_parse_caixin_rss_entries(self, parsed_caixin_feed):
        """Test parsing individual RSS entries."""
        entries = parsed_caixin_feed.entries
        
        # Test first entry
        first_entry = entries[0]
        
        # Check required fields
        assert hasattr(first_entry, 'title')
        assert hasattr(first_entry, 'link')
        assert hasattr(first_entry, 'published')
        assert hasattr(first_entry, 'guid')
        
        # Check specific content (based on current feed content)
        assert "蔚来汽车" in first_entry.title or len(first_entry.title) > 0
        assert first_entry.link.startswith("https://")
        assert first_entry.guid.startswith("caixin:latest:")
        
        print(f"First entry title: {first_entry.title}")
        print(f"First entry link: {first_entry.link}")
        print(f"First entry GUID: {first_entry.guid}")
    
    def test_convert_rss_to_storage_entries(self, parsed_caixin_feed, tmp_path):
        """Test converting RSS entries to storage format."""
        storage = RSSStorage(tmp_path)
        feed_name = "caixin-latest"
        source_url = "http://10.1.1.22:1200/caixin/latest"
        
        entries = parsed_caixin_feed.entries
        created_count = 0
        
        for entry_data in entries[:5]:  # Test first 5 entries
            # Convert to RSSEntry
            rss_entry = RSSEntry(
                feed_name=feed_name,
                source_url=source_url,
                guid=entry_data.get("guid", entry_data.get("id", "")),
                title=entry_data.get("title", ""),
                link=entry_data.get("link", ""),
                description=entry_data.get("description", ""),
                author=entry_data.get("author", ""),
                published=datetime.now(timezone.utc),  # Simplified for test
                tags=[entry_data.get("category", "")] if entry_data.get("category") else [],
            )
            
            # Store entry
            if storage.create_entry(rss_entry):
                created_count += 1
        
        assert created_count > 0
        print(f"Successfully created {created_count} entries")
        
        # Verify retrieval
        retrieved_entries = storage.get_entries(feed_name=feed_name)
        assert len(retrieved_entries) == created_count


class TestRealDataWithMCPServer:
    """Test MCP server operations with real data."""
    
    def test_storage_get_feeds_method(self, caixin_feed_with_source):
        """Test the new get_feeds method with real feed."""
        storage, feed, source = caixin_feed_with_source
        
        # Test get_feeds method (should work after our fix)
        feeds = storage.get_feeds()
        assert len(feeds) == 1
        assert feeds[0].name == "caixin-latest"
        assert feeds[0].enabled == True  # Test the new enabled property
        
        # Test with active_only filter
        feeds_active = storage.get_feeds(active_only=True)
        assert len(feeds_active) == 1
        
        # Disable feed and test filter
        feed.active = False
        storage.update_feed(feed)
        feeds_active = storage.get_feeds(active_only=True)
        assert len(feeds_active) == 0
    
    def test_storage_get_entries_with_since_until(self, caixin_feed_with_source, parsed_caixin_feed):
        """Test get_entries with since/until parameters."""
        storage, feed, source = caixin_feed_with_source
        feed_name = "caixin-latest"
        
        # Add some test entries first
        entries = parsed_caixin_feed.entries[:3]
        for entry_data in entries:
            rss_entry = RSSEntry(
                feed_name=feed_name,
                source_url=source.url,
                guid=entry_data.get("guid", entry_data.get("id", "")),
                title=entry_data.get("title", ""),
                link=entry_data.get("link", ""),
                description=entry_data.get("description", ""),
                published=datetime.now(timezone.utc),
            )
            storage.create_entry(rss_entry)
        
        # Test get_entries with since parameter (should work after our fix)
        from datetime import timedelta
        since_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        entries_with_since = storage.get_entries(
            feed_name=feed_name,
            limit=10,
            since=since_time  # This should work now
        )
        
        assert len(entries_with_since) > 0
        print(f"Found {len(entries_with_since)} entries since {since_time}")
    
    def test_feed_enabled_property(self):
        """Test the new enabled property on RSSFeed."""
        # Test active=True
        feed = RSSFeed(name="test", title="Test", active=True)
        assert feed.enabled == True
        
        # Test active=False  
        feed = RSSFeed(name="test", title="Test", active=False)
        assert feed.enabled == False
    
    def test_source_enabled_property(self):
        """Test the new enabled property on RSSSource."""
        # Test active=True
        source = RSSSource(feed_name="test", url="https://example.com/rss", active=True)
        assert source.enabled == True
        
        # Test active=False
        source = RSSSource(feed_name="test", url="https://example.com/rss", active=False)
        assert source.enabled == False


class TestRealDataValidation:
    """Validate the structure and content of real RSS data."""
    
    def test_caixin_feed_structure(self, parsed_caixin_feed):
        """Validate that Caixin feed has expected structure."""
        feed = parsed_caixin_feed
        
        # Feed level checks
        assert not feed.bozo, f"RSS parsing issues: {feed.bozo_exception}"
        assert feed.feed.title
        assert feed.feed.link
        assert feed.feed.description
        
        # Entry level checks
        for entry in feed.entries[:5]:  # Check first 5 entries
            assert entry.title, "Entry must have title"
            assert entry.link, "Entry must have link" 
            assert entry.link.startswith("https://"), "Entry link must be HTTPS"
            
            # GUID format check
            if hasattr(entry, 'guid'):
                assert entry.guid.startswith("caixin:latest:"), "GUID should follow expected format"
            
            # Category check
            if hasattr(entry, 'category'):
                assert entry.category.endswith("频道"), "Category should be a Chinese channel name"
    
    def test_caixin_content_quality(self, parsed_caixin_feed):
        """Test the quality of content in real RSS feed."""
        entries = parsed_caixin_feed.entries
        
        # Should have reasonable number of entries
        assert 10 <= len(entries) <= 50, f"Expected 10-50 entries, got {len(entries)}"
        
        # Check for Chinese content
        chinese_titles = [e for e in entries if any('\u4e00' <= char <= '\u9fff' for char in e.title)]
        assert len(chinese_titles) > len(entries) * 0.8, "Most entries should have Chinese titles"
        
        # Check publication times are recent (within last week for news feed)
        from datetime import timedelta
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        
        recent_entries = []
        for entry in entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if pub_time > recent_cutoff:
                    recent_entries.append(entry)
        
        # At least some entries should be recent (this is a live feed)
        assert len(recent_entries) > 0, "Feed should contain recent entries"
        
        print(f"Found {len(recent_entries)} recent entries out of {len(entries)} total")
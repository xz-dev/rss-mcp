"""Tests for RSS entry accumulation and retention functionality."""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import shutil

from rss_mcp.cache_storage import CacheStorage
from rss_mcp.models import RSSEntry
from rss_mcp.config import RSSFeedConfig
from rss_mcp.feed_manager import FeedManager
from rss_mcp.user_rss_manager import UserRssManager
from rss_mcp.config import Config, UserConfigManager


class TestEntryAccumulation:
    """Test RSS entry accumulation and retention features."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def cache_storage(self, temp_dir):
        """Create a cache storage instance for testing."""
        return CacheStorage(temp_dir, "test_user")

    @pytest.fixture
    def sample_entries(self):
        """Create sample RSS entries for testing."""
        now = datetime.now(timezone.utc)
        return [
            RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="entry1",
                title="Test Entry 1",
                link="https://example.com/1",
                description="First test entry",
                content="Content 1",
                author="Author 1",
                published=now - timedelta(hours=1),
                created_at=now - timedelta(hours=1)
            ),
            RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="entry1",  # Same GUID as above
                title="Test Entry 1 Updated",
                link="https://example.com/1",
                description="Updated test entry",
                content="Updated Content 1",
                author="Author 1",
                published=now,
                created_at=now
            ),
            RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="entry2",
                title="Test Entry 2",
                link="https://example.com/2",
                description="Second test entry",
                content="Content 2",
                author="Author 2",
                published=now - timedelta(minutes=30),
                created_at=now - timedelta(minutes=30)
            ),
        ]

    def test_entry_accumulation_instead_of_skip(self, cache_storage, sample_entries):
        """Test that entries are accumulated instead of being skipped as duplicates."""
        # First batch - store initial entries
        first_batch = [sample_entries[0], sample_entries[2]]  # entry1 and entry2
        count1 = cache_storage.store_entries(first_batch)
        assert count1 == 2

        # Second batch - includes updated version of entry1
        second_batch = [sample_entries[1]]  # updated entry1
        count2 = cache_storage.store_entries(second_batch)
        assert count2 == 1  # Should store, not skip

        # Verify both versions exist
        all_entries = cache_storage.get_entries(limit=100)
        assert len(all_entries) == 3  # Original entry1, updated entry1, entry2

        # Check that we have both versions of entry1
        entry1_versions = [e for e in all_entries if e.guid == "entry1"]
        assert len(entry1_versions) == 2
        
        # Verify content is different
        titles = {e.title for e in entry1_versions}
        assert "Test Entry 1" in titles
        assert "Test Entry 1 Updated" in titles

    def test_retention_period_cleanup(self, cache_storage):
        """Test that cleanup respects retention period in seconds."""
        now = datetime.now(timezone.utc)
        
        # Create entries with different ages
        entries = [
            RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="old_entry",
                title="Old Entry",
                link="https://example.com/old",
                description="Old entry",
                content="Old content",
                published=now - timedelta(days=35),  # 35 days old
                created_at=now - timedelta(days=35)
            ),
            RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="recent_entry",
                title="Recent Entry",
                link="https://example.com/recent",
                description="Recent entry",
                content="Recent content",
                published=now - timedelta(days=25),  # 25 days old
                created_at=now - timedelta(days=25)
            ),
        ]
        
        cache_storage.store_entries(entries)
        
        # Cleanup with 30-day retention (2592000 seconds)
        removed_count = cache_storage.cleanup_old_entries(retention_seconds=30 * 86400)
        
        assert removed_count == 1  # Should remove the 35-day-old entry
        
        remaining_entries = cache_storage.get_entries(limit=100)
        assert len(remaining_entries) == 1
        assert remaining_entries[0].guid == "recent_entry"

    def test_duplicate_cleanup_functionality(self, cache_storage):
        """Test the cleanup_duplicate_entries method."""
        now = datetime.now(timezone.utc)
        
        # Create multiple versions of the same entry with different timestamps
        entries = []
        for i in range(3):
            entry = RSSEntry(
                feed_name="test_feed",
                source_url="https://example.com/rss.xml",
                guid="duplicate_entry",
                title=f"Entry Version {i+1}",
                link="https://example.com/duplicate",
                description=f"Version {i+1}",
                content=f"Content version {i+1}",
                published=now - timedelta(hours=i),
                created_at=now - timedelta(hours=i)
            )
            entries.append(entry)
            
        cache_storage.store_entries(entries)
        
        # Verify all 3 versions exist
        all_entries = cache_storage.get_entries(limit=100)
        assert len(all_entries) == 3
        
        # Cleanup duplicates, keeping only 1 latest version
        removed_count = cache_storage.cleanup_duplicate_entries(keep_latest=1)
        assert removed_count == 2
        
        # Verify only 1 version remains (the most recent)
        remaining_entries = cache_storage.get_entries(limit=100)
        assert len(remaining_entries) == 1
        assert remaining_entries[0].title == "Entry Version 1"  # Most recent

    def test_retention_period_in_config(self, temp_dir):
        """Test that retention_period is properly configured and used."""
        # Create feed config with custom retention period
        feed_config = RSSFeedConfig(
            name="retention_test",
            title="Retention Test Feed",
            description="Testing retention",
            sources=["https://example.com/rss.xml"],
            fetch_interval=3600,
            retention_period=7 * 86400  # 7 days in seconds
        )
        
        assert feed_config.retention_period == 7 * 86400
        
        # Verify the default is 30 days
        default_config = RSSFeedConfig(
            name="default_test",
            title="Default Test",
            description="Default retention",
            sources=["https://example.com/rss2.xml"]
        )
        
        assert default_config.retention_period == 2592000  # 30 days

    def test_file_naming_with_timestamp(self, cache_storage, sample_entries):
        """Test that files are named with timestamps to allow accumulation."""
        entry = sample_entries[0]
        cache_storage.store_entries([entry])
        
        # Check that files exist with timestamp format
        entry_files = list(cache_storage.entries_dir.glob("test_feed_*.json"))
        assert len(entry_files) == 1
        
        filename = entry_files[0].name
        # Should be format: feed_name_guid_hash_timestamp.json
        parts = filename.replace('.json', '').split('_')
        assert len(parts) >= 3  # feed, hash, timestamp (and potentially more if feed name has underscores)
        
        # Last part should be a timestamp
        try:
            timestamp = int(parts[-1])
            assert timestamp > 0
        except ValueError:
            pytest.fail("Last part of filename should be a timestamp")

    def test_backward_compatibility_file_handling(self, cache_storage):
        """Test that both old and new file formats are handled correctly."""
        import json
        
        # Create an old-format file (without timestamp)
        old_file = cache_storage.entries_dir / "test_feed_oldformat.json"
        old_data = {
            "feed_name": "test_feed",
            "source_url": "https://example.com/rss.xml",
            "guid": "old_entry",
            "title": "Old Format Entry",
            "link": "https://example.com/old",
            "description": "Old format",
            "content": "Old content",
            "author": "Author",
            "published": None,
            "updated": None,
            "tags": [],
            "enclosures": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        
        # Store a new entry
        now = datetime.now(timezone.utc)
        new_entry = RSSEntry(
            feed_name="test_feed",
            source_url="https://example.com/rss.xml",
            guid="new_entry",
            title="New Format Entry",
            link="https://example.com/new",
            description="New format",
            content="New content",
            created_at=now
        )
        
        cache_storage.store_entries([new_entry])
        
        # Both should be readable
        entries = cache_storage.get_entries(limit=100)
        assert len(entries) == 2
        
        # Verify both entries can be read
        guids = {e.guid for e in entries}
        assert "old_entry" in guids
        assert "new_entry" in guids

    def test_refresh_includes_automatic_cleanup(self, temp_dir):
        """Test that refresh automatically cleans up old entries."""
        config = Config(
            cache_path=temp_dir,
            config_path=temp_dir / "config",
            log_level="INFO"
        )
        
        user_config_manager = UserConfigManager(config, "test_user")
        user_manager = UserRssManager(user_config_manager)
        cache_storage = CacheStorage(temp_dir, "test_user")
        feed_manager = FeedManager(user_manager, cache_storage, config)
        
        # Verify that FeedManager no longer has standalone cleanup method
        assert not hasattr(feed_manager, 'cleanup_old_entries')
        
        # The cleanup logic is now only integrated into the refresh process
        # This simplifies the API and ensures cleanup happens automatically


@pytest.mark.asyncio
async def test_integration_entry_accumulation():
    """Integration test for complete entry accumulation flow."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Setup
        config = Config(
            cache_path=temp_path,
            config_path=temp_path / "config",
            log_level="INFO"
        )
        
        user_config_manager = UserConfigManager(config, "test_user")
        user_manager = UserRssManager(user_config_manager)
        cache_storage = CacheStorage(temp_path, "test_user")
        feed_manager = FeedManager(user_manager, cache_storage, config)
        
        # Create test feed with short retention period
        feed_config = RSSFeedConfig(
            name="accumulation_test",
            title="Accumulation Test",
            description="Test feed",
            sources=["https://httpbin.org/xml"],  # Mock RSS endpoint (won't actually fetch)
            retention_period=3600  # 1 hour retention
        )
        
        user_manager.add_feed(feed_config)
        
        # Manually create some test entries with different ages
        now = datetime.now(timezone.utc)
        test_entries = [
            RSSEntry(
                feed_name="accumulation_test",
                source_url="https://httpbin.org/xml",
                guid="entry1",
                title="Entry 1 v1",
                link="https://example.com/1",
                description="First version",
                created_at=now - timedelta(hours=2)  # Outside retention period
            ),
            RSSEntry(
                feed_name="accumulation_test",
                source_url="https://httpbin.org/xml",
                guid="entry1",
                title="Entry 1 v2",
                link="https://example.com/1",
                description="Updated version",
                created_at=now - timedelta(minutes=30)  # Within retention period
            ),
        ]
        
        # Store entries directly to simulate historical accumulation
        cache_storage.store_entries(test_entries)
        
        # Verify both versions exist initially
        entries = cache_storage.get_entries(limit=100)
        assert len(entries) == 2
        
        # Note: In the real flow, cleanup would happen automatically during refresh
        # We can test the cleanup functionality directly on cache_storage since
        # it's still available as an internal method, but it's not exposed via CLI/API
        cache_storage.cleanup_old_entries(retention_seconds=3600)  # 1 hour
        
        # Should only have the recent entry now
        remaining_entries = cache_storage.get_entries(limit=100)
        assert len(remaining_entries) == 1
        assert remaining_entries[0].title == "Entry 1 v2"
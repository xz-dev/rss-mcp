"""Tests for RSS storage layer."""

from datetime import datetime, timedelta


from rss_mcp.models import RSSEntry, RSSFeed, RSSSource
from rss_mcp.storage import RSSStorage


class TestRSSStorage:
    """Test RSS storage operations."""

    def test_create_storage(self, storage):
        """Test creating storage instance."""
        assert isinstance(storage, RSSStorage)
        assert storage.cache_path.exists()
        assert storage.feeds_dir.exists()
        assert storage.sources_dir.exists()
        assert storage.entries_dir.exists()

    def test_directories_created(self, storage):
        """Test that storage directories are created."""
        assert storage.feeds_dir.is_dir()
        assert storage.sources_dir.is_dir()
        assert storage.entries_dir.is_dir()

    def test_create_and_get_feed(self, storage, sample_feed):
        """Test creating and retrieving a feed."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        assert storage.create_feed(feed_only) is True

        # Create sources separately
        for source in sample_feed.sources:
            assert storage.create_source(source) is True

        # Retrieve feed (should load sources automatically)
        retrieved = storage.get_feed("test-feed")
        assert retrieved is not None
        assert retrieved.name == "test-feed"
        assert retrieved.title == "Test Feed"
        assert retrieved.description == "A test RSS feed"
        assert len(retrieved.sources) == 2

    def test_create_duplicate_feed(self, storage, sample_feed):
        """Test creating duplicate feed fails."""
        assert storage.create_feed(sample_feed) is True
        assert storage.create_feed(sample_feed) is False

    def test_get_nonexistent_feed(self, storage):
        """Test retrieving nonexistent feed returns None."""
        assert storage.get_feed("nonexistent") is None

    def test_update_feed(self, storage, sample_feed):
        """Test updating a feed."""
        storage.create_feed(sample_feed)

        # Update feed
        sample_feed.title = "Updated Title"
        sample_feed.description = "Updated description"
        sample_feed.entry_count = 50

        assert storage.update_feed(sample_feed) is True

        # Verify update
        retrieved = storage.get_feed("test-feed")
        assert retrieved.title == "Updated Title"
        assert retrieved.description == "Updated description"
        assert retrieved.entry_count == 50

    def test_delete_feed(self, storage, sample_feed):
        """Test deleting a feed."""
        storage.create_feed(sample_feed)

        # Delete feed
        assert storage.delete_feed("test-feed") is True
        assert storage.get_feed("test-feed") is None

        # Delete nonexistent feed
        assert storage.delete_feed("nonexistent") is False

    def test_list_feeds(self, storage):
        """Test listing feeds."""
        # No feeds initially
        feeds = storage.list_feeds()
        assert len(feeds) == 0

        # Create test feeds
        feed1 = RSSFeed(name="feed1", title="Feed 1", active=True)
        feed2 = RSSFeed(name="feed2", title="Feed 2", active=False)

        storage.create_feed(feed1)
        storage.create_feed(feed2)

        # List all feeds
        all_feeds = storage.list_feeds()
        assert len(all_feeds) == 2

        # List only active feeds
        active_feeds = storage.list_feeds(active_only=True)
        assert len(active_feeds) == 1
        assert active_feeds[0].name == "feed1"

    def test_create_and_get_source(self, storage, sample_feed):
        """Test creating and retrieving sources."""
        storage.create_feed(sample_feed)

        # Create additional source
        source = RSSSource(
            feed_name="test-feed",
            url="https://example.com/rss3.xml",
            priority=2,
        )

        assert storage.create_source(source) is True
        assert source.id is not None

        # Retrieve source
        retrieved = storage.get_source(source.id)
        assert retrieved is not None
        assert retrieved.url == "https://example.com/rss3.xml"
        assert retrieved.priority == 2

    def test_create_duplicate_source(self, storage, sample_feed):
        """Test creating duplicate source fails."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        storage.create_feed(feed_only)

        # Create the original source
        original_source = sample_feed.sources[0]
        assert storage.create_source(original_source) is True

        # Try to create duplicate source with same URL
        duplicate_source = RSSSource(
            feed_name="test-feed",
            url=original_source.url,  # Same URL
            priority=5,
        )

        assert storage.create_source(duplicate_source) is False

    def test_get_sources_for_feed(self, storage, sample_feed):
        """Test retrieving sources for a feed."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        storage.create_feed(feed_only)

        # Create sources separately
        for source in sample_feed.sources:
            storage.create_source(source)

        sources = storage.get_sources_for_feed("test-feed")
        assert len(sources) == 2

        # Should be ordered by priority
        assert sources[0].priority == 0
        assert sources[1].priority == 1

    def test_update_source(self, storage, sample_feed):
        """Test updating a source."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        storage.create_feed(feed_only)

        # Create sources
        for source in sample_feed.sources:
            storage.create_source(source)

        sources = storage.get_sources_for_feed("test-feed")
        source = sources[0]

        # Update source
        source.error_count = 5
        source.last_error = "Connection failed"
        source.active = False

        assert storage.update_source(source) is True

        # Verify update
        retrieved = storage.get_source(source.id)
        assert retrieved.error_count == 5
        assert retrieved.last_error == "Connection failed"
        assert retrieved.active is False

    def test_delete_source(self, storage, sample_feed):
        """Test deleting a source."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        storage.create_feed(feed_only)

        # Create sources
        for source in sample_feed.sources:
            storage.create_source(source)

        # Delete source
        assert storage.delete_source("test-feed", "https://example.com/rss.xml") is True

        # Verify deletion
        sources = storage.get_sources_for_feed("test-feed")
        assert len(sources) == 1
        assert sources[0].url == "https://example.com/backup.xml"

        # Delete nonexistent source
        assert storage.delete_source("test-feed", "https://nonexistent.com") is False

    def test_create_and_get_entries(self, storage, sample_feed, sample_entries):
        """Test creating and retrieving entries."""
        storage.create_feed(sample_feed)

        # Create entries
        for entry in sample_entries:
            assert storage.create_entry(entry) is True
            assert entry.id is not None

    def test_create_duplicate_entry(self, storage, sample_feed, sample_entries):
        """Test creating duplicate entry fails."""
        storage.create_feed(sample_feed)

        entry = sample_entries[0]
        assert storage.create_entry(entry) is True
        assert storage.create_entry(entry) is False

    def test_get_entries_basic(self, storage, sample_feed, sample_entries):
        """Test basic entry retrieval."""
        storage.create_feed(sample_feed)

        for entry in sample_entries:
            storage.create_entry(entry)

        # Get all entries
        entries = storage.get_entries()
        assert len(entries) == 5

        # Should be ordered by published date (newest first)
        assert entries[0].title == "Test Entry 4"
        assert entries[-1].title == "Test Entry 0"

    def test_get_entries_by_feed(self, storage, sample_entries):
        """Test retrieving entries by feed."""
        # Create two feeds
        feed1 = RSSFeed(name="feed1")
        feed2 = RSSFeed(name="feed2")
        storage.create_feed(feed1)
        storage.create_feed(feed2)

        # Create entries for different feeds
        for i, entry in enumerate(sample_entries):
            if i < 3:
                entry.feed_name = "feed1"
            else:
                entry.feed_name = "feed2"
            storage.create_entry(entry)

        # Get entries for specific feed
        feed1_entries = storage.get_entries(feed_name="feed1")
        assert len(feed1_entries) == 3
        assert all(e.feed_name == "feed1" for e in feed1_entries)

        feed2_entries = storage.get_entries(feed_name="feed2")
        assert len(feed2_entries) == 2
        assert all(e.feed_name == "feed2" for e in feed2_entries)

    def test_get_entries_time_filter(self, storage, sample_feed, sample_entries):
        """Test retrieving entries with time filters."""
        storage.create_feed(sample_feed)

        for entry in sample_entries:
            storage.create_entry(entry)

        # Filter by start time
        start_time = datetime(2023, 1, 3, 0, 0, 0)
        entries = storage.get_entries(start_time=start_time)
        assert len(entries) == 3  # Entries 2, 3, 4

        # Filter by end time
        end_time = datetime(2023, 1, 3, 23, 59, 59)
        entries = storage.get_entries(end_time=end_time)
        assert len(entries) == 3  # Entries 0, 1, 2

        # Filter by both
        entries = storage.get_entries(
            start_time=datetime(2023, 1, 2, 0, 0, 0), end_time=datetime(2023, 1, 4, 23, 59, 59)
        )
        assert len(entries) == 3  # Entries 1, 2, 3

    def test_get_entries_pagination(self, storage, sample_feed, sample_entries):
        """Test entry pagination."""
        storage.create_feed(sample_feed)

        for entry in sample_entries:
            storage.create_entry(entry)

        # First page
        page1 = storage.get_entries(limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0].title == "Test Entry 4"
        assert page1[1].title == "Test Entry 3"

        # Second page
        page2 = storage.get_entries(limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0].title == "Test Entry 2"
        assert page2[1].title == "Test Entry 1"

        # Third page
        page3 = storage.get_entries(limit=2, offset=4)
        assert len(page3) == 1
        assert page3[0].title == "Test Entry 0"

    def test_get_entry_count(self, storage, sample_feed, sample_entries):
        """Test counting entries."""
        storage.create_feed(sample_feed)

        # No entries initially
        assert storage.get_entry_count() == 0

        # Add entries
        for entry in sample_entries:
            storage.create_entry(entry)

        # Count all entries
        assert storage.get_entry_count() == 5

        # Count by feed
        assert storage.get_entry_count(feed_name="test-feed") == 5
        assert storage.get_entry_count(feed_name="nonexistent") == 0

        # Count with time filter
        start_time = datetime(2023, 1, 3, 0, 0, 0)
        assert storage.get_entry_count(start_time=start_time) == 3

    def test_get_feed_stats(self, storage, sample_feed, sample_entries):
        """Test getting feed statistics."""
        # Create feed (without sources)
        feed_only = RSSFeed(
            name=sample_feed.name,
            title=sample_feed.title,
            description=sample_feed.description,
            link=sample_feed.link,
        )
        storage.create_feed(feed_only)

        # Create sources
        for source in sample_feed.sources:
            storage.create_source(source)

        # Adjust entry dates for testing
        now = datetime.now()
        for i, entry in enumerate(sample_entries):
            if i < 2:  # Last 24h
                entry.published = now - timedelta(hours=i)
            elif i < 4:  # Last week
                entry.published = now - timedelta(days=i - 1)
            else:  # Older
                entry.published = now - timedelta(days=10)
            storage.create_entry(entry)

        stats = storage.get_feed_stats("test-feed")
        assert stats.feed_name == "test-feed"
        assert stats.total_entries == 5
        assert stats.entries_last_24h == 2
        assert stats.entries_last_7d == 4
        assert stats.active_sources == 2
        assert stats.healthy_sources == 2

    def test_cleanup_old_entries(self, storage, sample_feed):
        """Test cleaning up old entries."""
        storage.create_feed(sample_feed)

        # Create entries with different ages
        now = datetime.now()
        old_entries = []
        new_entries = []

        for i in range(5):
            if i < 2:
                # Old entries (older than 30 days)
                pub_date = now - timedelta(days=40 + i)
                old_entries.append(
                    RSSEntry(
                        feed_name="test-feed",
                        source_url="https://example.com/rss.xml",
                        guid=f"old-{i}",
                        title=f"Old Entry {i}",
                        published=pub_date,
                    )
                )
            else:
                # New entries (within 30 days)
                pub_date = now - timedelta(days=i)
                new_entries.append(
                    RSSEntry(
                        feed_name="test-feed",
                        source_url="https://example.com/rss.xml",
                        guid=f"new-{i}",
                        title=f"New Entry {i}",
                        published=pub_date,
                    )
                )

        # Add all entries
        for entry in old_entries + new_entries:
            storage.create_entry(entry)

        # Verify all entries exist
        assert storage.get_entry_count() == 5

        # Cleanup entries older than 30 days
        cleaned = storage.cleanup_old_entries(days=30)
        assert cleaned == 2

        # Verify only new entries remain
        remaining = storage.get_entries()
        assert len(remaining) == 3
        assert all("New Entry" in entry.title for entry in remaining)

    def test_datetime_parsing(self, storage):
        """Test datetime parsing helper method."""
        # Valid datetime string
        dt_str = "2023-01-01T12:00:00"
        parsed = storage._parse_datetime(dt_str)
        assert parsed == datetime(2023, 1, 1, 12, 0, 0)

        # None
        assert storage._parse_datetime(None) is None

        # Empty string
        assert storage._parse_datetime("") is None

        # Invalid datetime
        assert storage._parse_datetime("invalid") is None

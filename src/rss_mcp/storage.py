"""JSON-based file storage layer for RSS MCP server."""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import FeedStats, RSSEntry, RSSFeed, RSSSource

logger = logging.getLogger(__name__)


class RSSStorage:
    """JSON file-based storage for RSS feeds, sources, and entries."""

    def __init__(self, cache_path: Path):
        """Initialize the storage with cache directory path."""
        self.cache_path = cache_path
        self.cache_path.mkdir(parents=True, exist_ok=True)

        # Storage directories
        self.feeds_dir = self.cache_path / "feeds"
        self.sources_dir = self.cache_path / "sources"
        self.entries_dir = self.cache_path / "entries"

        # Create directories
        for dir_path in [self.feeds_dir, self.sources_dir, self.entries_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _get_url_hash(self, url: str) -> str:
        """Generate SHA256 hash of URL for cache key.

        Args:
            url: The URL to hash

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    # Feed operations
    def create_feed(self, feed: RSSFeed) -> bool:
        """Create a new feed."""
        feed_file = self.feeds_dir / f"{feed.name}.json"
        if feed_file.exists():
            return False

        feed_data = {
            "name": feed.name,
            "title": feed.title,
            "description": feed.description,
            "link": feed.link,
            "active": feed.active,
            "fetch_interval": feed.fetch_interval,
            "last_fetch": feed.last_fetch.isoformat() if feed.last_fetch else None,
            "last_success": feed.last_success.isoformat() if feed.last_success else None,
            "entry_count": feed.entry_count,
            "created_at": feed.created_at.isoformat(),
            "updated_at": feed.updated_at.isoformat(),
        }

        with open(feed_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, indent=2, ensure_ascii=False)

        return True

    def get_feed(self, name: str) -> Optional[RSSFeed]:
        """Get a feed by name."""
        feed_file = self.feeds_dir / f"{name}.json"
        if not feed_file.exists():
            return None

        try:
            with open(feed_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            feed = RSSFeed(
                name=data["name"],
                title=data["title"],
                description=data["description"],
                link=data["link"],
                active=data["active"],
                fetch_interval=data["fetch_interval"],
                last_fetch=self._parse_datetime(data["last_fetch"]),
                last_success=self._parse_datetime(data["last_success"]),
                entry_count=data["entry_count"],
                created_at=self._parse_datetime(data["created_at"]),
                updated_at=self._parse_datetime(data["updated_at"]),
            )
            # Load associated sources
            feed.sources = self.get_sources_for_feed(data["name"])
            return feed
        except (json.JSONDecodeError, KeyError):
            return None

    def update_feed(self, feed: RSSFeed) -> bool:
        """Update an existing feed."""
        feed_file = self.feeds_dir / f"{feed.name}.json"
        if not feed_file.exists():
            return False

        feed.updated_at = datetime.now()

        feed_data = {
            "name": feed.name,
            "title": feed.title,
            "description": feed.description,
            "link": feed.link,
            "active": feed.active,
            "fetch_interval": feed.fetch_interval,
            "last_fetch": feed.last_fetch.isoformat() if feed.last_fetch else None,
            "last_success": feed.last_success.isoformat() if feed.last_success else None,
            "entry_count": feed.entry_count,
            "created_at": feed.created_at.isoformat(),
            "updated_at": feed.updated_at.isoformat(),
        }

        with open(feed_file, "w", encoding="utf-8") as f:
            json.dump(feed_data, f, indent=2, ensure_ascii=False)

        return True

    def delete_feed(self, name: str) -> bool:
        """Delete a feed and all its sources and entries."""
        feed_file = self.feeds_dir / f"{name}.json"
        if not feed_file.exists():
            return False

        # Remove feed file
        feed_file.unlink()

        # Remove all sources for this feed
        sources = self.get_sources_for_feed(name)
        for source in sources:
            if source.id:
                self.delete_source(source.id)

        # Remove all entries for this feed
        self._delete_entries_for_feed(name)

        return True

    def list_feeds(self, active_only: bool = False) -> List[RSSFeed]:
        """List all feeds."""
        feeds = []

        for feed_file in self.feeds_dir.glob("*.json"):
            try:
                with open(feed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if active_only and not data.get("active", True):
                    continue

                feed = RSSFeed(
                    name=data["name"],
                    title=data["title"],
                    description=data["description"],
                    link=data["link"],
                    active=data["active"],
                    fetch_interval=data["fetch_interval"],
                    last_fetch=self._parse_datetime(data["last_fetch"]),
                    last_success=self._parse_datetime(data["last_success"]),
                    entry_count=data["entry_count"],
                    created_at=self._parse_datetime(data["created_at"]),
                    updated_at=self._parse_datetime(data["updated_at"]),
                )
                # Load associated sources
                feed.sources = self.get_sources_for_feed(data["name"])
                feeds.append(feed)
            except (json.JSONDecodeError, KeyError):
                continue

        return sorted(feeds, key=lambda f: f.name)

    # Source operations
    def create_source(self, source: RSSSource) -> bool:
        """Create a new source."""
        # Check for duplicate URL in the same feed
        if self.find_source_by_url(source.feed_name, source.url):
            return False

        if not source.id:
            source.id = str(uuid4())

        source_file = self.sources_dir / f"{source.id}.json"
        if source_file.exists():
            return False

        source_data = {
            "id": source.id,
            "feed_name": source.feed_name,
            "url": source.url,
            "priority": source.priority,
            "active": source.active,
            "last_fetch": source.last_fetch.isoformat() if source.last_fetch else None,
            "last_success": source.last_success.isoformat() if source.last_success else None,
            "error_count": source.error_count,
            "last_error": source.last_error,
            "created_at": source.created_at.isoformat(),
        }

        with open(source_file, "w", encoding="utf-8") as f:
            json.dump(source_data, f, indent=2, ensure_ascii=False)

        return True

    def get_source(self, source_id: str) -> Optional[RSSSource]:
        """Get a source by ID."""
        source_file = self.sources_dir / f"{source_id}.json"
        if not source_file.exists():
            return None

        try:
            with open(source_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return RSSSource(
                id=data["id"],
                feed_name=data["feed_name"],
                url=data["url"],
                priority=data["priority"],
                active=data["active"],
                last_fetch=self._parse_datetime(data["last_fetch"]),
                last_success=self._parse_datetime(data["last_success"]),
                error_count=data["error_count"],
                last_error=data["last_error"],
                created_at=self._parse_datetime(data["created_at"]),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def get_sources_for_feed(self, feed_name: str) -> List[RSSSource]:
        """Get all sources for a feed."""
        sources = []

        for source_file in self.sources_dir.glob("*.json"):
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if data["feed_name"] != feed_name:
                    continue

                source = RSSSource(
                    id=data["id"],
                    feed_name=data["feed_name"],
                    url=data["url"],
                    priority=data["priority"],
                    active=data["active"],
                    last_fetch=self._parse_datetime(data["last_fetch"]),
                    last_success=self._parse_datetime(data["last_success"]),
                    error_count=data["error_count"],
                    last_error=data["last_error"],
                    created_at=self._parse_datetime(data["created_at"]),
                )
                sources.append(source)
            except (json.JSONDecodeError, KeyError):
                continue

        return sorted(sources, key=lambda s: s.priority)

    def update_source(self, source: RSSSource) -> bool:
        """Update an existing source."""
        source_file = self.sources_dir / f"{source.id}.json"
        if not source_file.exists():
            return False

        source_data = {
            "id": source.id,
            "feed_name": source.feed_name,
            "url": source.url,
            "priority": source.priority,
            "active": source.active,
            "last_fetch": source.last_fetch.isoformat() if source.last_fetch else None,
            "last_success": source.last_success.isoformat() if source.last_success else None,
            "error_count": source.error_count,
            "last_error": source.last_error,
            "created_at": source.created_at.isoformat(),
        }

        with open(source_file, "w", encoding="utf-8") as f:
            json.dump(source_data, f, indent=2, ensure_ascii=False)

        return True

    def delete_source(self, source_id_or_feed_name: str, url: Optional[str] = None) -> bool:
        """Delete a source by ID or by feed_name + URL."""
        if url is None:
            # Delete by source ID
            source_file = self.sources_dir / f"{source_id_or_feed_name}.json"
            if not source_file.exists():
                return False
            source_file.unlink()
            return True
        else:
            # Delete by feed_name + URL
            source = self.find_source_by_url(source_id_or_feed_name, url)
            if not source or not source.id:
                return False
            return self.delete_source(source.id)

    def find_source_by_url(self, feed_name: str, url: str) -> Optional[RSSSource]:
        """Find a source by feed name and URL."""
        sources = self.get_sources_for_feed(feed_name)
        for source in sources:
            if source.url == url:
                return source
        return None

    # Entry operations
    def create_entry(self, entry: RSSEntry) -> bool:
        """Create a new entry."""
        if not entry.id:
            entry.id = str(uuid4())

        # Create feed-specific directory
        feed_entries_dir = self.entries_dir / entry.feed_name
        feed_entries_dir.mkdir(exist_ok=True)

        entry_file = feed_entries_dir / f"{entry.id}.json"
        if entry_file.exists():
            return False

        entry_data = {
            "id": entry.id,
            "feed_name": entry.feed_name,
            "source_url": entry.source_url,
            "guid": entry.guid,
            "title": entry.title,
            "link": entry.link,
            "description": entry.description,
            "content": entry.content,
            "author": entry.author,
            "published": entry.published.isoformat() if entry.published else None,
            "updated": entry.updated.isoformat() if entry.updated else None,
            "tags": entry.tags,
            "enclosures": entry.enclosures,
            "created_at": entry.created_at.isoformat(),
        }

        with open(entry_file, "w", encoding="utf-8") as f:
            json.dump(entry_data, f, indent=2, ensure_ascii=False)

        return True

    def get_entry(self, entry_id: str, feed_name: str) -> Optional[RSSEntry]:
        """Get an entry by ID."""
        entry_file = self.entries_dir / feed_name / f"{entry_id}.json"
        if not entry_file.exists():
            return None

        try:
            with open(entry_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return RSSEntry(
                id=data["id"],
                feed_name=data["feed_name"],
                source_url=data["source_url"],
                guid=data["guid"],
                title=data["title"],
                link=data["link"],
                description=data["description"],
                content=data["content"],
                author=data["author"],
                published=self._parse_datetime(data["published"]),
                updated=self._parse_datetime(data["updated"]),
                tags=data["tags"],
                enclosures=data["enclosures"],
                created_at=self._parse_datetime(data["created_at"]),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def find_entry_by_guid(self, feed_name: str, guid: str) -> Optional[RSSEntry]:
        """Find an entry by feed name and GUID."""
        feed_entries_dir = self.entries_dir / feed_name
        if not feed_entries_dir.exists():
            return None

        for entry_file in feed_entries_dir.glob("*.json"):
            try:
                with open(entry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if data.get("guid") == guid:
                    return RSSEntry(
                        id=data["id"],
                        feed_name=data["feed_name"],
                        source_url=data["source_url"],
                        guid=data["guid"],
                        title=data["title"],
                        link=data["link"],
                        description=data["description"],
                        content=data["content"],
                        author=data["author"],
                        published=self._parse_datetime(data["published"]),
                        updated=self._parse_datetime(data["updated"]),
                        tags=data["tags"],
                        enclosures=data["enclosures"],
                        created_at=self._parse_datetime(data["created_at"]),
                    )
            except (json.JSONDecodeError, KeyError):
                continue

        return None

    def get_entries(
        self,
        feed_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[RSSEntry]:
        """Get entries with optional filtering and pagination."""
        # Handle legacy limit/offset style parameters
        if limit is not None:
            page_size = limit
            page = (offset // limit + 1) if offset else 1

        entries = []

        # Determine which feed directories to search
        if feed_name:
            search_dirs = (
                [self.entries_dir / feed_name] if (self.entries_dir / feed_name).exists() else []
            )
        else:
            search_dirs = [d for d in self.entries_dir.iterdir() if d.is_dir()]

        # Collect all matching entries
        for feed_dir in search_dirs:
            for entry_file in feed_dir.glob("*.json"):
                try:
                    with open(entry_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    published = self._parse_datetime(data.get("published"))

                    # Apply time filtering
                    if start_time and published and published < start_time:
                        continue
                    if end_time and published and published > end_time:
                        continue

                    entry = RSSEntry(
                        id=data["id"],
                        feed_name=data["feed_name"],
                        source_url=data["source_url"],
                        guid=data["guid"],
                        title=data["title"],
                        link=data["link"],
                        description=data["description"],
                        content=data["content"],
                        author=data["author"],
                        published=published,
                        updated=self._parse_datetime(data["updated"]),
                        tags=data["tags"],
                        enclosures=data["enclosures"],
                        created_at=self._parse_datetime(data["created_at"]),
                    )
                    entries.append(entry)
                except (json.JSONDecodeError, KeyError):
                    continue

        # Sort by published date (newest first)
        entries.sort(key=lambda e: e.published or datetime.min, reverse=True)

        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        return entries[start_idx:end_idx]

    def get_entry_count(
        self,
        feed_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """Get total entry count with optional time filtering."""
        count = 0

        # If no time filtering, use simple file count
        if start_time is None and end_time is None:
            if feed_name:
                feed_dir = self.entries_dir / feed_name
                if feed_dir.exists():
                    count = len(list(feed_dir.glob("*.json")))
            else:
                for feed_dir in self.entries_dir.iterdir():
                    if feed_dir.is_dir():
                        count += len(list(feed_dir.glob("*.json")))
            return count

        # With time filtering, need to check each entry
        search_dirs = []
        if feed_name:
            search_dirs = (
                [self.entries_dir / feed_name] if (self.entries_dir / feed_name).exists() else []
            )
        else:
            search_dirs = [d for d in self.entries_dir.iterdir() if d.is_dir()]

        for feed_dir in search_dirs:
            for entry_file in feed_dir.glob("*.json"):
                try:
                    with open(entry_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    published = self._parse_datetime(data.get("published"))

                    # Apply time filtering
                    if start_time and published and published < start_time:
                        continue
                    if end_time and published and published > end_time:
                        continue

                    count += 1
                except (json.JSONDecodeError, KeyError):
                    continue

        return count

    def get_feed_stats(self, feed_name: Optional[str] = None) -> FeedStats:
        """Get feed statistics."""
        if feed_name:
            feeds = [self.get_feed(feed_name)] if self.get_feed(feed_name) else []
        else:
            feeds = self.list_feeds()

        total_feeds = len(feeds)
        active_feeds = len([f for f in feeds if f and f.active])
        total_entries = self.get_entry_count(feed_name)

        # Calculate last update time
        last_update = None
        for feed in feeds:
            if feed and feed.last_success:
                if not last_update or feed.last_success > last_update:
                    last_update = feed.last_success

        # Calculate time-based entry counts
        now = datetime.now()
        entries_last_24h = self.get_entry_count(
            feed_name=feed_name, start_time=now - timedelta(days=1), end_time=now
        )
        entries_last_7d = self.get_entry_count(
            feed_name=feed_name, start_time=now - timedelta(days=7), end_time=now
        )

        # Calculate source counts for specific feed
        if feed_name:
            sources = self.get_sources_for_feed(feed_name)
            active_source_count = len([s for s in sources if s.active])
            healthy_source_count = len([s for s in sources if s.active and s.is_healthy])
        else:
            active_source_count = active_feeds
            healthy_source_count = active_feeds

        return FeedStats(
            feed_name=feed_name or "All Feeds",
            total_entries=total_entries,
            entries_last_24h=entries_last_24h,
            entries_last_7d=entries_last_7d,
            last_fetch=last_update,
            last_success=last_update,
            active_sources=active_source_count,
            healthy_sources=healthy_source_count,
        )

    def cleanup_old_entries(self, days: int = 90) -> int:
        """Remove entries older than specified days."""
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0

        for feed_dir in self.entries_dir.iterdir():
            if not feed_dir.is_dir():
                continue

            for entry_file in feed_dir.glob("*.json"):
                try:
                    with open(entry_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    published = self._parse_datetime(data.get("published"))
                    if published and published < cutoff_date:
                        entry_file.unlink()
                        deleted_count += 1
                except (json.JSONDecodeError, KeyError, OSError):
                    continue

        return deleted_count

    def _delete_entries_for_feed(self, feed_name: str):
        """Delete all entries for a specific feed."""
        feed_dir = self.entries_dir / feed_name
        if feed_dir.exists():
            for entry_file in feed_dir.glob("*.json"):
                try:
                    entry_file.unlink()
                except OSError:
                    pass
            # Try to remove empty directory
            try:
                feed_dir.rmdir()
            except OSError:
                pass

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    # URL-based caching methods
    def cache_feed_content(
        self,
        url: str,
        content: str,
        last_modified: Optional[datetime] = None,
        etag: Optional[str] = None,
    ) -> bool:
        """Cache RSS feed content by URL hash.

        Args:
            url: RSS feed URL
            content: Raw RSS content
            last_modified: Last modified timestamp
            etag: HTTP ETag value

        Returns:
            True if cached successfully
        """
        try:
            url_hash = self._get_url_hash(url)
            cache_dir = self.cache_path / url_hash
            cache_dir.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "url": url,
                "content": content,
                "cached_at": datetime.now().isoformat(),
                "last_modified": last_modified.isoformat() if last_modified else None,
                "etag": etag,
            }

            cache_file = cache_dir / "content.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            logger.warning(f"Failed to cache content for {url}: {e}")
            return False

    def get_cached_feed_content(self, url: str, max_age_hours: int = 1) -> Optional[Dict[str, Any]]:
        """Get cached RSS feed content by URL hash.

        Args:
            url: RSS feed URL
            max_age_hours: Maximum age of cache in hours

        Returns:
            Cached content data or None if not found/expired
        """
        try:
            url_hash = self._get_url_hash(url)
            cache_file = self.cache_path / url_hash / "content.json"

            if not cache_file.exists():
                return None

            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check cache age
            cached_at = self._parse_datetime(cache_data.get("cached_at"))
            if cached_at:
                age_hours = (datetime.now() - cached_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    return None

            return cache_data
        except Exception as e:
            logger.warning(f"Failed to get cached content for {url}: {e}")
            return None

    def clear_url_cache(self, url: str) -> bool:
        """Clear cached content for a specific URL.

        Args:
            url: RSS feed URL to clear cache for

        Returns:
            True if cleared successfully
        """
        try:
            url_hash = self._get_url_hash(url)
            cache_dir = self.cache_path / url_hash

            if cache_dir.exists():
                for file in cache_dir.glob("*"):
                    file.unlink()
                cache_dir.rmdir()

            return True
        except Exception as e:
            logger.warning(f"Failed to clear cache for {url}: {e}")
            return False

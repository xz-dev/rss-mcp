"""Cache storage for RSS entries and feed content."""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import RSSEntry

logger = logging.getLogger(__name__)


class CacheStorage:
    """File-based cache storage for RSS entries and feed content."""

    def __init__(self, cache_path: Path, user_id: str):
        """Initialize cache storage for a specific user.

        Args:
            cache_path: Base cache directory
            user_id: User identifier for isolation
        """
        self.cache_path = cache_path
        self.user_id = user_id
        self.user_cache_path = cache_path / "users" / user_id

        # Create user-specific directories
        self.user_cache_path.mkdir(parents=True, exist_ok=True)
        self.entries_dir = self.user_cache_path / "entries"
        self.feed_content_dir = self.user_cache_path / "feed_content"
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.feed_content_dir.mkdir(parents=True, exist_ok=True)

    def _get_url_hash(self, url: str) -> str:
        """Generate SHA256 hash of URL for cache key."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string with timezone handling."""
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    def store_entries(self, entries: List[RSSEntry]) -> int:
        """Store RSS entries, accumulating all entries including duplicates.

        Args:
            entries: List of RSS entries to store

        Returns:
            Number of entries stored
        """
        new_count = 0

        for entry in entries:
            # Create entry file based on feed name, guid hash, and timestamp
            guid_hash = hashlib.sha256(entry.guid.encode()).hexdigest()[:16]
            timestamp = int(entry.created_at.timestamp())
            entry_file = self.entries_dir / f"{entry.feed_name}_{guid_hash}_{timestamp}.json"

            # Always store entries (accumulate instead of skip duplicates)

            # Store entry data
            entry_data = {
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

            try:
                with open(entry_file, "w", encoding="utf-8") as f:
                    json.dump(entry_data, f, indent=2, ensure_ascii=False)
                new_count += 1
            except Exception as e:
                logger.error(f"Failed to store entry {entry.guid}: {e}")
                continue

        return new_count

    def get_entries(
        self,
        feed_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[RSSEntry]:
        """Retrieve RSS entries with optional filtering.

        Args:
            feed_name: Filter by specific feed name
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            since: Filter entries published after this date
            until: Filter entries published before this date

        Returns:
            List of RSS entries
        """
        entries = []

        # Get all entry files
        for entry_file in self.entries_dir.glob("*.json"):
            try:
                with open(entry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Apply feed name filter
                if feed_name and data.get("feed_name") != feed_name:
                    continue

                # Create RSSEntry object
                entry = RSSEntry(
                    feed_name=data["feed_name"],
                    source_url=data["source_url"],
                    guid=data["guid"],
                    title=data["title"],
                    link=data["link"],
                    description=data["description"],
                    content=data["content"],
                    author=data["author"],
                    published=self._parse_datetime(data.get("published")),
                    updated=self._parse_datetime(data.get("updated")),
                    tags=data.get("tags", []),
                    enclosures=data.get("enclosures", []),
                    created_at=self._parse_datetime(data["created_at"])
                    or datetime.now(timezone.utc),
                )

                # Apply date filters
                entry_date = entry.effective_published
                if since and entry_date < since:
                    continue
                if until and entry_date > until:
                    continue

                entries.append(entry)

            except Exception as e:
                logger.error(f"Failed to load entry {entry_file}: {e}")
                continue

        # Sort by publication date (newest first)
        entries.sort(key=lambda e: e.effective_published, reverse=True)

        # Apply pagination
        return entries[offset : offset + limit]

    def get_entry_count(self, feed_name: Optional[str] = None) -> int:
        """Get count of entries.

        Args:
            feed_name: Filter by specific feed name

        Returns:
            Number of entries
        """
        count = 0

        for entry_file in self.entries_dir.glob("*.json"):
            if feed_name:
                try:
                    with open(entry_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("feed_name") == feed_name:
                        count += 1
                except Exception:
                    continue
            else:
                count += 1

        return count

    def cleanup_old_entries(self, retention_seconds: int = 2592000) -> int:
        """Remove entries older than specified retention period.

        Args:
            retention_seconds: Number of seconds to keep entries (default: 30 days)

        Returns:
            Number of entries removed
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(seconds=retention_seconds)
        removed_count = 0

        for entry_file in self.entries_dir.glob("*.json"):
            try:
                with open(entry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                created_at = self._parse_datetime(data.get("created_at"))
                if created_at and created_at < cutoff_date:
                    entry_file.unlink()
                    removed_count += 1

            except Exception as e:
                logger.error(f"Failed to process entry {entry_file}: {e}")
                continue

        return removed_count

    def delete_feed_entries(self, feed_name: str) -> int:
        """Delete all entries for a specific feed.

        Args:
            feed_name: Name of the feed

        Returns:
            Number of entries deleted
        """
        deleted_count = 0

        # Handle both old format (feed_name_hash.json) and new format (feed_name_hash_timestamp.json)
        for entry_file in self.entries_dir.glob(f"{feed_name}_*.json"):
            try:
                entry_file.unlink()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete entry {entry_file}: {e}")
                continue

        return deleted_count

    def cleanup_duplicate_entries(self, feed_name: Optional[str] = None, keep_latest: int = 1) -> int:
        """Clean up duplicate entries, keeping only the most recent versions.

        Args:
            feed_name: Filter by specific feed name, None for all feeds
            keep_latest: Number of latest versions to keep for each GUID (default: 1)

        Returns:
            Number of entries removed
        """
        removed_count = 0
        
        # Group entries by feed_name and guid_hash
        entry_groups = {}
        pattern = f"{feed_name}_*.json" if feed_name else "*.json"
        
        for entry_file in self.entries_dir.glob(pattern):
            try:
                # Parse filename: feed_name_hash_timestamp.json or feed_name_hash.json (old format)
                filename = entry_file.stem
                parts = filename.split("_")
                
                if len(parts) >= 3:  # New format with timestamp
                    feed = "_".join(parts[:-2])  # Handle feed names with underscores
                    guid_hash = parts[-2]
                    timestamp = int(parts[-1])
                elif len(parts) >= 2:  # Old format without timestamp  
                    feed = "_".join(parts[:-1])
                    guid_hash = parts[-1]
                    timestamp = 0  # Old entries get timestamp 0
                else:
                    continue
                
                if feed_name and feed != feed_name:
                    continue
                    
                key = f"{feed}_{guid_hash}"
                if key not in entry_groups:
                    entry_groups[key] = []
                entry_groups[key].append((timestamp, entry_file))
                
            except (ValueError, IndexError):
                # Skip files with invalid format
                continue
        
        # For each group, keep only the latest entries
        for group_entries in entry_groups.values():
            if len(group_entries) <= keep_latest:
                continue
                
            # Sort by timestamp (newest first)
            group_entries.sort(key=lambda x: x[0], reverse=True)
            
            # Remove older entries
            for _, entry_file in group_entries[keep_latest:]:
                try:
                    entry_file.unlink()
                    removed_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete duplicate entry {entry_file}: {e}")
                    
        return removed_count

    # Feed content caching methods
    def cache_feed_content(
        self,
        url: str,
        content: str,
        last_modified: Optional[datetime] = None,
        etag: Optional[str] = None,
    ) -> None:
        """Cache feed content with metadata.

        Args:
            url: Feed URL
            content: Feed content
            last_modified: Last-Modified header value
            etag: ETag header value
        """
        url_hash = self._get_url_hash(url)
        cache_file = self.feed_content_dir / f"{url_hash}.json"

        cache_data = {
            "url": url,
            "content": content,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "last_modified": last_modified.isoformat() if last_modified else None,
            "etag": etag,
        }

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to cache content for {url}: {e}")

    def get_cached_feed_content(self, url: str, max_age_hours: int = 1) -> Optional[Dict[str, Any]]:
        """Get cached feed content if still valid.

        Args:
            url: Feed URL
            max_age_hours: Maximum age in hours

        Returns:
            Cached content data or None if not available/expired
        """
        url_hash = self._get_url_hash(url)
        cache_file = self.feed_content_dir / f"{url_hash}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check if cache is still valid
            cached_at = datetime.fromisoformat(cache_data["cached_at"])
            max_age = timedelta(hours=max_age_hours)

            if datetime.now(timezone.utc) - cached_at > max_age:
                return None

            return cache_data

        except Exception as e:
            logger.error(f"Failed to load cached content for {url}: {e}")
            return None

    def clear_feed_content_cache(self, url: Optional[str] = None) -> int:
        """Clear feed content cache.

        Args:
            url: Specific URL to clear, or None to clear all

        Returns:
            Number of cache files removed
        """
        removed_count = 0

        if url:
            # Clear specific URL
            url_hash = self._get_url_hash(url)
            cache_file = self.feed_content_dir / f"{url_hash}.json"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    removed_count = 1
                except Exception as e:
                    logger.error(f"Failed to remove cache for {url}: {e}")
        else:
            # Clear all cache
            for cache_file in self.feed_content_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                    removed_count += 1
                except Exception as e:
                    logger.error(f"Failed to remove cache file {cache_file}: {e}")
                    continue

        return removed_count

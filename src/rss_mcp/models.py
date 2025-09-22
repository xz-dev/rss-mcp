"""Data models for RSS MCP server."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse


@dataclass
class RSSSource:
    """Represents a single RSS source URL."""

    id: Optional[str] = None
    feed_name: str = ""
    url: str = ""
    priority: int = 0  # Lower values have higher priority
    active: bool = True
    last_fetch: Optional[datetime] = None
    last_success: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate the source URL."""
        if self.url:
            parsed = urlparse(self.url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid URL: {self.url}")

    @property
    def is_healthy(self) -> bool:
        """Check if the source is considered healthy."""
        # Consider unhealthy if more than 5 consecutive errors
        return self.error_count < 5
    
    @property
    def enabled(self) -> bool:
        """Alias for active property."""
        return self.active


@dataclass
class RSSFeed:
    """Represents an RSS feed with multiple sources."""

    name: str = ""
    title: str = ""
    remote_title: str = ""  # Title from RSS feed source
    description: str = ""
    link: str = ""
    sources: List[RSSSource] = field(default_factory=list)
    active: bool = True
    fetch_interval: int = 3600  # seconds
    last_fetch: Optional[datetime] = None
    last_success: Optional[datetime] = None
    entry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate the feed."""
        if not self.name:
            raise ValueError("Feed name cannot be empty")
        if not self.title:
            self.title = self.name

    @property
    def primary_source(self) -> Optional[RSSSource]:
        """Get the primary (highest priority) active source."""
        active_sources = [s for s in self.sources if s.active and s.is_healthy]
        if not active_sources:
            return None
        return min(active_sources, key=lambda s: s.priority)

    @property
    def healthy_sources(self) -> List[RSSSource]:
        """Get all healthy, active sources ordered by priority."""
        active_sources = [s for s in self.sources if s.active and s.is_healthy]
        return sorted(active_sources, key=lambda s: s.priority)
    
    @property
    def enabled(self) -> bool:
        """Alias for active property."""
        return self.active


@dataclass
class RSSEntry:
    """Represents an RSS entry/article."""

    id: Optional[str] = None
    feed_name: str = ""
    source_url: str = ""
    guid: str = ""  # Unique identifier from RSS
    title: str = ""
    link: str = ""
    description: str = ""
    content: str = ""  # Full content if available
    author: str = ""
    published: Optional[datetime] = None
    updated: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    enclosures: List[str] = field(default_factory=list)  # Media attachments
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate the entry."""
        if not self.feed_name:
            raise ValueError("Entry must belong to a feed")
        if not self.guid and not self.link:
            raise ValueError("Entry must have either GUID or link")

        # Use link as GUID if GUID is not provided
        if not self.guid:
            self.guid = self.link

    @property
    def effective_published(self) -> datetime:
        """Get the effective publication date (published or created_at)."""
        return self.published or self.created_at

    @property
    def summary(self) -> str:
        """Get a summary of the entry (content or description)."""
        return self.content or self.description

    def get_truncated_summary(self, max_length: int = 200) -> str:
        """Get a truncated summary of the entry."""
        summary = self.summary
        if len(summary) <= max_length:
            return summary

        # Find a good breaking point
        truncated = summary[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:  # If we can break at a word boundary
            truncated = truncated[:last_space]

        return truncated + "..."


@dataclass
class FeedStats:
    """Statistics for a feed."""

    feed_name: str = ""
    total_entries: int = 0
    entries_last_24h: int = 0
    entries_last_7d: int = 0
    last_fetch: Optional[datetime] = None
    last_success: Optional[datetime] = None
    active_sources: int = 0
    healthy_sources: int = 0
    avg_fetch_time: float = 0.0  # seconds

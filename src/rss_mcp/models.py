"""Data models for RSS MCP server."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


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
    last_updated: Optional[datetime] = None
    last_fetch_attempt: Optional[datetime] = None
    last_successful_fetch: Optional[datetime] = None
    fetch_success_rate: float = 0.0  # Percentage
    average_entries_per_day: float = 0.0

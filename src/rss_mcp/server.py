"""Unified RSS MCP Server with stdio, HTTP, and SSE support using FastMCP."""

import logging
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from dateutil import parser as date_parser
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

from .cache_storage import CacheStorage
from .config import RSSFeedConfig, UserConfigManager, config, get_user_id
from .feed_manager import FeedManager
from .user_rss_manager import UserRssManager

logger = logging.getLogger(__name__)

# Global storage for user-specific resources
_user_managers: Dict[str, UserRssManager] = {}
_user_cache_storages: Dict[str, CacheStorage] = {}
_user_feed_managers: Dict[str, FeedManager] = {}

# Context variable to store current user ID
current_user_id: ContextVar[str] = ContextVar("current_user_id")

# Create the unified FastMCP server
server = FastMCP("RSS MCP Server")


def get_current_user_id() -> str:
    """Get current user ID from FastMCP context or environment."""
    try:
        # Try context variable first (set by get_user_resources)
        return current_user_id.get()
    except LookupError:
        # Fall back to HTTP headers and environment
        headers = get_http_headers()
        return get_user_id(headers)


def get_user_resources(
    user_id: Optional[str] = None,
) -> Tuple[UserRssManager, FeedManager, CacheStorage]:
    """Get or create user-specific resources."""
    if user_id is None:
        user_id = get_current_user_id()

    # Set context variable for this request
    current_user_id.set(user_id)

    if user_id not in _user_managers:
        # Create user-specific resources
        user_config_manager = UserConfigManager(config, user_id)
        user_manager = UserRssManager(user_config_manager)
        cache_storage = CacheStorage(config.cache_path, user_id)
        feed_manager = FeedManager(user_manager, cache_storage, config)

        # Cache them
        _user_managers[user_id] = user_manager
        _user_cache_storages[user_id] = cache_storage
        _user_feed_managers[user_id] = feed_manager

        logger.info(f"Created resources for user: {user_id}")

    return _user_managers[user_id], _user_feed_managers[user_id], _user_cache_storages[user_id]


@server.tool()
def list_feeds() -> dict:
    """List all RSS feeds for the current user."""
    user_id = get_current_user_id()
    user_manager, _, _ = get_user_resources(user_id)

    feeds = user_manager.get_feeds()

    return {
        "user_id": user_id,
        "feeds": [
            {
                "name": feed.name,
                "title": feed.title,
                "description": feed.description,
                "sources": feed.sources,
                "fetch_interval": feed.fetch_interval,
            }
            for feed in feeds
        ],
    }


@server.tool()
def get_entries(
    feed_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """Get RSS entries with optional filtering.

    Args:
        feed_name: Name of specific feed (optional)
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        since: ISO datetime string to filter entries after
        until: ISO datetime string to filter entries before
    """
    user_id = get_current_user_id()
    _, _, cache_storage = get_user_resources(user_id)

    # Parse datetime filters
    since_dt = None
    until_dt = None
    if since:
        since_dt = date_parser.parse(since)
    if until:
        until_dt = date_parser.parse(until)

    entries = cache_storage.get_entries(
        feed_name=feed_name, limit=limit, offset=offset, since=since_dt, until=until_dt
    )

    return {
        "user_id": user_id,
        "feed_name": feed_name,
        "entries": [
            {
                "feed_name": entry.feed_name,
                "title": entry.title,
                "link": entry.link,
                "published": entry.effective_published.isoformat(),
                "author": entry.author,
                "tags": entry.tags,
                "guid": entry.guid,
                "summary": entry.get_truncated_summary(200),
            }
            for entry in entries
        ],
        "count": len(entries),
    }


@server.tool()
def add_feed(name: str, title: str, description: str = "", fetch_interval: int = 3600) -> dict:
    """Create a new RSS feed.

    Args:
        name: Unique name for the feed
        title: Display title for the feed
        description: Optional description
        fetch_interval: Fetch interval in seconds
    """
    user_id = get_current_user_id()
    user_manager, _, _ = get_user_resources(user_id)

    # Create new feed config
    feed_config = RSSFeedConfig(
        name=name,
        title=title,
        description=description,
        sources=[],  # Start with empty sources
        fetch_interval=fetch_interval,
    )

    success = user_manager.add_feed(feed_config)

    return {
        "user_id": user_id,
        "success": success,
        "feed_name": name,
        "message": (
            f"Successfully created feed '{name}'" if success else f"Feed '{name}' already exists"
        ),
    }


@server.tool()
def add_source(feed_name: str, url: str) -> dict:
    """Add a source URL to an existing feed.

    Args:
        feed_name: Name of the target feed
        url: RSS/Atom feed URL
    """
    user_id = get_current_user_id()
    user_manager, _, _ = get_user_resources(user_id)

    # Get current feeds
    feeds = user_manager.get_feeds()
    target_feed = None
    for feed in feeds:
        if feed.name == feed_name:
            target_feed = feed
            break

    if not target_feed:
        return {
            "user_id": user_id,
            "success": False,
            "error": f"Feed '{feed_name}' not found",
            "feed_name": feed_name,
        }

    # Add source URL if not already present
    if url not in target_feed.sources:
        target_feed.sources.append(url)
        success = user_manager.update_feed(feed_name, target_feed)
    else:
        success = False

    return {
        "user_id": user_id,
        "success": success,
        "feed_name": feed_name,
        "source_url": url,
        "message": (
            f"Successfully added source to '{feed_name}'"
            if success
            else f"Source already exists or feed not found"
        ),
    }


@server.tool()
async def refresh_feeds(feed_name: Optional[str] = None) -> dict:
    """Refresh RSS feeds by fetching latest entries.

    Args:
        feed_name: Specific feed name to refresh (optional, refreshes all if not provided)
    """
    user_id = get_current_user_id()
    user_manager, feed_manager, cache_storage = get_user_resources(user_id)

    if feed_name:
        # Refresh specific feed
        feeds = user_manager.get_feeds()
        if not any(feed.name == feed_name for feed in feeds):
            return {
                "user_id": user_id,
                "success": False,
                "error": f"Feed '{feed_name}' not found",
                "feed_name": feed_name,
            }

        feeds_to_refresh = [feed_name]
    else:
        # Refresh all feeds
        feeds = user_manager.get_feeds()
        feeds_to_refresh = [feed.name for feed in feeds]

    # Use feed manager to refresh feeds
    results = await feed_manager.refresh_all_feeds(feeds_to_refresh)

    total_feeds = len(results)
    feeds_processed = sum(1 for _, success, _ in results if success)
    total_entries = 0
    errors = []

    for feed_name_result, success, message in results:
        if success:
            # Extract new count from message
            import re

            match = re.search(r"(\d+) new entries", message)
            if match:
                total_entries += int(match.group(1))
        else:
            errors.append(f"{feed_name_result}: {message}")

    return {
        "user_id": user_id,
        "feed_name": feed_name,
        "feeds_total": total_feeds,
        "feeds_processed": feeds_processed,
        "total_new_entries": total_entries,
        "errors": errors,
        "success": feeds_processed > 0,
    }


@server.tool()
def delete_feed(feed_name: str) -> dict:
    """Delete a feed and all its entries.

    Args:
        feed_name: Name of the feed to delete
    """
    user_id = get_current_user_id()
    user_manager, _, cache_storage = get_user_resources(user_id)

    # Remove from user config
    config_success = user_manager.remove_feed(feed_name)

    # Remove entries from cache
    cache_entries_removed = 0
    if config_success:
        cache_entries_removed = cache_storage.delete_feed_entries(feed_name)

    return {
        "user_id": user_id,
        "success": config_success,
        "feed_name": feed_name,
        "entries_removed": cache_entries_removed,
        "message": (
            f"Successfully deleted feed '{feed_name}' and {cache_entries_removed} entries"
            if config_success
            else f"Feed '{feed_name}' not found"
        ),
    }


@server.tool()
def remove_source(feed_name: str, url: str) -> dict:
    """Remove a source URL from a feed.

    Args:
        feed_name: Name of the feed
        url: Source URL to remove
    """
    user_id = get_current_user_id()
    user_manager, _, _ = get_user_resources(user_id)

    # Get current feeds
    feeds = user_manager.get_feeds()
    target_feed = None
    for feed in feeds:
        if feed.name == feed_name:
            target_feed = feed
            break

    if not target_feed:
        return {
            "user_id": user_id,
            "success": False,
            "feed_name": feed_name,
            "source_url": url,
            "message": f"Feed '{feed_name}' not found",
        }

    # Remove source URL if present
    success = False
    if url in target_feed.sources:
        target_feed.sources.remove(url)
        success = user_manager.update_feed(feed_name, target_feed)

    return {
        "user_id": user_id,
        "success": success,
        "feed_name": feed_name,
        "source_url": url,
        "message": (
            f"Successfully removed source from '{feed_name}'" if success else "Source not found"
        ),
    }


@server.tool()
def get_feed_stats(feed_name: Optional[str] = None) -> dict:
    """Get statistics for feeds.

    Args:
        feed_name: Specific feed name (optional, returns overall stats if not provided)
    """
    user_id = get_current_user_id()
    user_manager, _, cache_storage = get_user_resources(user_id)

    if feed_name:
        # Specific feed stats
        feeds = user_manager.get_feeds()
        if not any(feed.name == feed_name for feed in feeds):
            return {
                "user_id": user_id,
                "success": False,
                "error": f"Feed '{feed_name}' not found",
                "feed_name": feed_name,
            }

        total_entries = cache_storage.get_entry_count(feed_name)

        # Get entries from last 24 hours and 7 days
        now = datetime.now()
        entries_24h = cache_storage.get_entries(
            feed_name=feed_name,
            since=now - timedelta(hours=24),
            limit=1000,  # High limit to count all
        )
        entries_7d = cache_storage.get_entries(
            feed_name=feed_name,
            since=now - timedelta(days=7),
            limit=1000,  # High limit to count all
        )

        return {
            "user_id": user_id,
            "feed_name": feed_name,
            "total_entries": total_entries,
            "entries_last_24h": len(entries_24h),
            "entries_last_7d": len(entries_7d),
        }
    else:
        # Overall stats
        feeds = user_manager.get_feeds()
        total_feeds = len(feeds)
        total_entries = cache_storage.get_entry_count()

        # Get recent entries
        now = datetime.now()
        entries_24h = cache_storage.get_entries(
            since=now - timedelta(hours=24), limit=1000  # High limit to count all
        )
        entries_7d = cache_storage.get_entries(
            since=now - timedelta(days=7), limit=1000  # High limit to count all
        )

        return {
            "user_id": user_id,
            "total_feeds": total_feeds,
            "total_entries": total_entries,
            "entries_last_24h": len(entries_24h),
            "entries_last_7d": len(entries_7d),
        }


# Server runners for different modes
async def run_stdio():
    """Run the server in stdio mode."""
    await server.run()


async def run_http(host: str = "0.0.0.0", port: int = 8000):
    """Run the server in HTTP mode."""
    await server.run_streamable_http_async(host=host, port=port)


async def run_sse(host: str = "0.0.0.0", port: int = 8000):
    """Run the server in SSE mode."""
    await server.run_sse_async(host=host, port=port)


async def run_http_with_sse(host: str = "0.0.0.0", port: int = 8000):
    """Run the server with both HTTP (/mcp) and SSE (/sse) endpoints."""
    # Use the modern FastMCP HTTP server (supports both streamable HTTP and SSE)
    await server.run_http_async(host=host, port=port)


# Cleanup function
async def cleanup():
    """Clean up resources."""
    for feed_manager in _user_feed_managers.values():
        await feed_manager.close()

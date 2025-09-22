"""FastMCP-based RSS MCP server implementation."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from dateutil import parser as date_parser
from mcp.server.fastmcp import FastMCP

from .config import get_config_manager, get_user_id
from .feed_manager import FeedFetcher
from .models import RSSFeed, RSSSource
from .storage import RSSStorage

logger = logging.getLogger(__name__)

# Global server instances per user
_servers: Dict[str, FastMCP] = {}
_storage_instances: Dict[str, RSSStorage] = {}
_feed_fetchers: Dict[str, FeedFetcher] = {}


def get_fastmcp_server(
    user_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Get or create a FastMCP server instance for a specific user."""
    effective_user_id = user_id or get_user_id(headers)

    if effective_user_id not in _servers:
        # Create user-specific server with custom host and port
        server = FastMCP(name=f"RSS MCP Server (User: {effective_user_id})", host=host, port=port)

        # Get user-specific config and storage
        config_manager = get_config_manager(user_id=effective_user_id, headers=headers)
        config = config_manager.config
        storage = RSSStorage(Path(config.cache_path))
        feed_fetcher = FeedFetcher(config, storage)

        # Store instances
        _servers[effective_user_id] = server
        _storage_instances[effective_user_id] = storage
        _feed_fetchers[effective_user_id] = feed_fetcher

        # Register tools
        _register_tools(server, storage, feed_fetcher, effective_user_id)

        # Register resources
        _register_resources(server, storage, effective_user_id)

    return _servers[effective_user_id]


def _register_tools(server: FastMCP, storage: RSSStorage, feed_fetcher: FeedFetcher, user_id: str):
    """Register MCP tools for the server."""

    @server.tool()
    def list_feeds() -> Dict[str, Any]:
        """List all RSS feeds."""
        try:
            feeds = storage.get_feeds()
            return {
                "feeds": [
                    {
                        "name": feed.name,
                        "title": feed.title,
                        "remote_title": feed.remote_title,
                        "description": feed.description,
                        "link": feed.link,
                        "enabled": feed.enabled,
                        "sources": [
                            {
                                "url": source.url,
                                "priority": source.priority,
                                "enabled": source.enabled,
                            }
                            for source in feed.sources
                        ],
                    }
                    for feed in feeds
                ]
            }
        except Exception as e:
            logger.error(f"Error listing feeds for user {user_id}: {e}")
            return {"error": str(e)}

    @server.tool()
    def add_feed(name: str, title: str, description: str = "", link: str = "") -> Dict[str, Any]:
        """Add a new RSS feed."""
        try:
            feed = RSSFeed(
                name=name,
                title=title,
                description=description,
                link=link,
            )
            result = storage.create_feed(feed)
            if result:
                return {"success": True, "message": f"Feed '{name}' added successfully"}
            else:
                return {"success": False, "error": "Feed already exists"}
        except Exception as e:
            logger.error(f"Error adding feed for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    def remove_feed(name: str) -> Dict[str, Any]:
        """Remove an RSS feed."""
        try:
            result = storage.delete_feed(name)
            if result:
                return {"success": True, "message": f"Feed '{name}' removed successfully"}
            else:
                return {"success": False, "error": "Feed not found"}
        except Exception as e:
            logger.error(f"Error removing feed for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    def update_feed(name: str, title: str = None, description: str = None, link: str = None, active: bool = None) -> Dict[str, Any]:
        """Update an RSS feed's properties."""
        try:
            feed = storage.get_feed(name)
            if not feed:
                return {"success": False, "error": "Feed not found"}
            
            # Update only the provided fields
            if title is not None:
                feed.title = title
            if description is not None:
                feed.description = description
            if link is not None:
                feed.link = link
            if active is not None:
                feed.active = active
            
            result = storage.update_feed(feed)
            if result:
                return {"success": True, "message": f"Feed '{name}' updated successfully"}
            else:
                return {"success": False, "error": "Failed to update feed"}
        except Exception as e:
            logger.error(f"Error updating feed for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    def add_source(feed_name: str, url: str, priority: int = 0) -> Dict[str, Any]:
        """Add a source URL to an RSS feed."""
        try:
            source = RSSSource(
                feed_name=feed_name,
                url=url,
                priority=priority,
            )
            result = storage.create_source(source)
            if result:
                return {"success": True, "message": f"Source added to feed '{feed_name}'"}
            else:
                return {"success": False, "error": "Source already exists or feed not found"}
        except Exception as e:
            logger.error(f"Error adding source for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    def remove_source(feed_name: str, url: str) -> Dict[str, Any]:
        """Remove a source URL from an RSS feed."""
        try:
            result = storage.delete_source(feed_name, url)
            if result:
                return {"success": True, "message": f"Source removed from feed '{feed_name}'"}
            else:
                return {"success": False, "error": "Source not found"}
        except Exception as e:
            logger.error(f"Error removing source for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    async def refresh_feeds(feed_name: Optional[str] = None) -> Dict[str, Any]:
        """Refresh RSS feeds to fetch new entries."""
        try:
            if feed_name:
                feeds = [storage.get_feed(feed_name)]
                if not feeds[0]:
                    return {"success": False, "error": f"Feed '{feed_name}' not found"}
            else:
                feeds = storage.get_feeds()

            total_new = 0
            for feed in feeds:
                if feed and feed.enabled:
                    new_count = await feed_fetcher.fetch_feed(feed.name)
                    total_new += new_count

            message = f"Fetched {total_new} new entries"
            if feed_name:
                message += f" for feed '{feed_name}'"

            return {"success": True, "message": message, "new_entries": total_new}
        except Exception as e:
            logger.error(f"Error refreshing feeds for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @server.tool()
    def get_entries(
        feed_name: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get RSS entries with optional filtering."""
        try:
            # Parse date filters if provided
            since_dt = None
            until_dt = None
            if since:
                since_dt = date_parser.parse(since)
            if until:
                until_dt = date_parser.parse(until)

            entries = storage.get_entries(
                feed_name=feed_name,
                limit=limit,
                offset=offset,
                since=since_dt,
                until=until_dt,
            )

            return {
                "entries": [
                    {
                        "feed_name": entry.feed_name,
                        "source_url": entry.source_url,
                        "guid": entry.guid,
                        "title": entry.title,
                        "link": entry.link,
                        "description": entry.description,
                        "content": entry.content,
                        "author": entry.author,
                        "published": entry.published.isoformat() if entry.published else None,
                        "tags": entry.tags,
                    }
                    for entry in entries
                ],
                "count": len(entries),
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            logger.error(f"Error getting entries for user {user_id}: {e}")
            return {"error": str(e)}

    @server.tool()
    def get_entry_summary(feed_name: str, entry_guid: str, max_length: int = 500) -> Dict[str, Any]:
        """Get a summary of a specific RSS entry."""
        try:
            entries = storage.get_entries(feed_name=feed_name, limit=1000)
            entry = next((e for e in entries if e.guid == entry_guid), None)

            if not entry:
                return {"error": "Entry not found"}

            # Create a summary by truncating content or description
            content = entry.content or entry.description or ""
            if len(content) > max_length:
                summary = content[:max_length] + "..."
            else:
                summary = content

            return {
                "title": entry.title,
                "link": entry.link,
                "published": entry.published.isoformat() if entry.published else None,
                "author": entry.author,
                "summary": summary,
                "tags": entry.tags,
            }
        except Exception as e:
            logger.error(f"Error getting entry summary for user {user_id}: {e}")
            return {"error": str(e)}

    @server.tool()
    def get_feed_stats(feed_name: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for RSS feeds."""
        try:
            stats = storage.get_feed_stats(feed_name)
            return {"stats": stats}
        except Exception as e:
            logger.error(f"Error getting feed stats for user {user_id}: {e}")
            return {"error": str(e)}


def _register_resources(server: FastMCP, storage: RSSStorage, user_id: str):
    """Register MCP resources for the server."""

    @server.resource("rss://feeds")
    def get_feeds_resource() -> str:
        """Get all feeds as a resource."""
        try:
            feeds = storage.get_feeds()
            return json.dumps(
                [
                    {
                        "name": feed.name,
                        "title": feed.title,
                        "remote_title": feed.remote_title,
                        "description": feed.description,
                        "enabled": feed.enabled,
                        "source_count": len(feed.sources),
                    }
                    for feed in feeds
                ],
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.resource("rss://feed/{feed_name}")
    def get_feed_resource(feed_name: str) -> str:
        """Get a specific feed as a resource."""
        try:
            feed = storage.get_feed(feed_name)
            if not feed:
                return json.dumps({"error": "Feed not found"})

            return json.dumps(
                {
                    "name": feed.name,
                    "title": feed.title,
                    "description": feed.description,
                    "link": feed.link,
                    "enabled": feed.enabled,
                    "sources": [
                        {
                            "url": source.url,
                            "priority": source.priority,
                            "enabled": source.enabled,
                        }
                        for source in feed.sources
                    ],
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})


async def run_fastmcp_stdio(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastMCP server in stdio mode."""
    server = get_fastmcp_server(host=host, port=port)
    await server.run_stdio_async()


async def run_fastmcp_http(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastMCP server in HTTP mode."""
    server = get_fastmcp_server(host=host, port=port)
    await server.run_streamable_http_async()


def run_fastmcp_server(mode: str = "stdio", host: str = "127.0.0.1", port: int = 8000):
    """Run the FastMCP server in specified mode."""
    import asyncio

    if mode == "stdio":
        asyncio.run(run_fastmcp_stdio(host, port))
    elif mode == "http":
        asyncio.run(run_fastmcp_http(host, port))
    else:
        # Default to stdio for MCP compatibility
        server = get_fastmcp_server(host=host, port=port)
        server.run()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "http":
        run_fastmcp_server("http")
    else:
        run_fastmcp_server("stdio")

"""FastMCP-based RSS MCP server with HTTP headers support and multi-user isolation."""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextvars import ContextVar

from dateutil import parser as date_parser
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .config import RSSConfig, get_config_manager, get_user_id_safe
from .feed_manager import FeedFetcher
from .models import RSSEntry, RSSFeed, RSSSource
from .storage import RSSStorage

logger = logging.getLogger(__name__)

# Global storage for user-specific resources
_user_storages: Dict[str, RSSStorage] = {}
_user_fetchers: Dict[str, FeedFetcher] = {}
_user_configs: Dict[str, RSSConfig] = {}

# Context variable to store current user ID
current_user_id: ContextVar[str] = ContextVar('current_user_id', default="default")


def get_current_user_id() -> str:
    """Get current user ID from context or fallback."""
    try:
        return current_user_id.get()
    except LookupError:
        # Fallback for contexts where no user ID is set (stdio mode)
        fallback_user = os.getenv("RSS_MCP_USER", "default")
        logger.debug(f"Using fallback user ID: {fallback_user}")
        return fallback_user


def get_user_resources(user_id: str) -> tuple[RSSStorage, FeedFetcher, RSSConfig]:
    """Get or create user-specific storage, fetcher, and config."""
    if user_id not in _user_storages:
        # Get user-specific config
        config_manager = get_config_manager(user_id=user_id)
        config = config_manager.config
        
        # Create user-specific storage and fetcher
        storage = RSSStorage(Path(config.cache_path))
        fetcher = FeedFetcher(config, storage)
        
        # Cache them
        _user_storages[user_id] = storage
        _user_fetchers[user_id] = fetcher
        _user_configs[user_id] = config
        
        logger.info(f"Created resources for user: {user_id}")
    
    return _user_storages[user_id], _user_fetchers[user_id], _user_configs[user_id]


# Create the FastMCP server
server = FastMCP("RSS MCP Multi-User Server v2")


@server.tool()
def list_feeds(active_only: bool = False) -> dict:
    """List all RSS feeds for the current user.
    
    Args:
        active_only: If True, only return active feeds
    
    Returns:
        Dictionary containing user_id and list of feeds
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    feeds = storage.list_feeds(active_only=active_only)
    
    return {
        "user_id": user_id,
        "feeds": [
            {
                "name": feed.name,
                "title": feed.title,
                "remote_title": feed.remote_title,
                "description": feed.description,
                "active": feed.active,
                "entry_count": feed.entry_count,
                "sources": [
                    {
                        "url": source.url,
                        "priority": source.priority,
                        "active": source.active,
                        "is_healthy": source.is_healthy,
                        "error_count": source.error_count,
                    }
                    for source in feed.sources
                ],
                "last_success": feed.last_success.isoformat() if feed.last_success else None,
                "fetch_interval": feed.fetch_interval,
            }
            for feed in feeds
        ]
    }


@server.tool()
def get_entries(
    feed_name: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """Get RSS entries for the current user.
    
    Args:
        feed_name: Filter by specific feed name (optional)
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        since: Start time filter (ISO format or relative like '1 day ago')
        until: End time filter (ISO format)
    
    Returns:
        Dictionary containing user_id and list of entries
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    # Parse time filters
    since_dt = None
    until_dt = None
    
    if since:
        try:
            since_dt = date_parser.parse(since)
        except Exception as e:
            logger.warning(f"Could not parse since time '{since}': {e}")
    
    if until:
        try:
            until_dt = date_parser.parse(until)
        except Exception as e:
            logger.warning(f"Could not parse until time '{until}': {e}")
    
    entries = storage.get_entries(
        feed_name=feed_name,
        limit=limit,
        offset=offset,
        start_time=since_dt,
        end_time=until_dt,
    )
    
    return {
        "user_id": user_id,
        "entries": [
            {
                "feed_name": entry.feed_name,
                "title": entry.title,
                "link": entry.link,
                "description": entry.description[:300] if entry.description else None,
                "content": entry.content[:500] if entry.content else None,
                "published": entry.published.isoformat() if entry.published else None,
                "effective_published": entry.effective_published.isoformat(),
                "author": entry.author,
                "tags": entry.tags,
                "guid": entry.guid,
            }
            for entry in entries
        ]
    }


@server.tool()
def add_feed(
    name: str, 
    title: str, 
    description: Optional[str] = None,
    fetch_interval: Optional[int] = None
) -> dict:
    """Add a new RSS feed for the current user.
    
    Args:
        name: Unique name for the feed
        title: Display title for the feed
        description: Optional description
        fetch_interval: Fetch interval in seconds (optional, uses config default)
    
    Returns:
        Dictionary with operation result
    """
    user_id = get_current_user_id()
    storage, _, config = get_user_resources(user_id)
    
    # Check if feed already exists
    existing_feed = storage.get_feed(name)
    if existing_feed:
        return {
            "user_id": user_id,
            "success": False,
            "error": f"Feed '{name}' already exists",
            "feed_name": name
        }
    
    # Create new feed
    feed = RSSFeed(
        name=name,
        title=title,
        description=description or "",
        fetch_interval=fetch_interval or config.default_fetch_interval,
    )
    
    success = storage.create_feed(feed)
    
    return {
        "user_id": user_id,
        "success": success,
        "feed_name": name,
        "message": f"Successfully created feed '{name}'" if success else f"Failed to create feed '{name}'"
    }


@server.tool()
def add_source(feed_name: str, url: str, priority: int = 0) -> dict:
    """Add a source URL to an existing feed for the current user.
    
    Args:
        feed_name: Name of the feed to add source to
        url: RSS/Atom feed URL
        priority: Priority level (lower = higher priority)
    
    Returns:
        Dictionary with operation result
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    # Check if feed exists
    feed = storage.get_feed(feed_name)
    if not feed:
        return {
            "user_id": user_id,
            "success": False,
            "error": f"Feed '{feed_name}' not found",
            "source_url": url
        }
    
    # Create source
    source = RSSSource(
        feed_name=feed_name,
        url=url,
        priority=priority,
    )
    
    success = storage.create_source(source)
    
    return {
        "user_id": user_id,
        "success": success,
        "source_url": url,
        "feed_name": feed_name,
        "message": f"Successfully added source to '{feed_name}'" if success else f"Failed to add source (may already exist)"
    }


@server.tool()
async def refresh_feeds(feed_name: Optional[str] = None) -> dict:
    """Refresh RSS feeds for the current user.
    
    Args:
        feed_name: Specific feed to refresh (optional, refreshes all active feeds if not specified)
    
    Returns:
        Dictionary with refresh results
    """
    user_id = get_current_user_id()
    storage, fetcher, _ = get_user_resources(user_id)
    
    if feed_name:
        # Refresh specific feed
        success, message = await fetcher.refresh_feed(feed_name)
        
        return {
            "user_id": user_id,
            "success": success,
            "message": message,
            "feeds_processed": 1 if success else 0,
            "feeds_total": 1
        }
    else:
        # Refresh all active feeds
        results = await fetcher.refresh_all_feeds()
        
        success_count = sum(1 for _, success, _ in results if success)
        total_count = len(results)
        
        messages = [message for _, _, message in results]
        
        return {
            "user_id": user_id,
            "success": success_count > 0,
            "message": f"Refreshed {success_count}/{total_count} feeds successfully",
            "feeds_processed": success_count,
            "feeds_total": total_count,
            "details": messages
        }


@server.tool()
def delete_feed(feed_name: str) -> dict:
    """Delete a feed and all its entries for the current user.
    
    Args:
        feed_name: Name of the feed to delete
    
    Returns:
        Dictionary with operation result
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    success = storage.delete_feed(feed_name)
    
    return {
        "user_id": user_id,
        "success": success,
        "deleted_feed": feed_name,
        "message": f"Successfully deleted feed '{feed_name}'" if success else f"Feed '{feed_name}' not found"
    }


@server.tool()
def get_feed_stats(feed_name: Optional[str] = None) -> dict:
    """Get statistics about feeds for the current user.
    
    Args:
        feed_name: Specific feed name (optional, gets overall stats if not specified)
    
    Returns:
        Dictionary with statistics
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    if feed_name:
        # Get stats for specific feed
        stats = storage.get_feed_stats(feed_name)
        
        return {
            "user_id": user_id,
            "feed_name": feed_name,
            "total_entries": stats.total_entries,
            "entries_last_24h": stats.entries_last_24h,
            "entries_last_7d": stats.entries_last_7d,
            "active_sources": stats.active_sources,
            "healthy_sources": stats.healthy_sources,
            "last_success": stats.last_success.isoformat() if stats.last_success else None,
        }
    else:
        # Get overall stats
        feeds = storage.list_feeds()
        active_feeds = [f for f in feeds if f.active]
        total_entries = sum(f.entry_count for f in feeds)
        
        return {
            "user_id": user_id,
            "total_feeds": len(feeds),
            "active_feeds": len(active_feeds),
            "total_entries": total_entries,
            "top_feeds": [
                {
                    "name": feed.name,
                    "title": feed.title,
                    "entry_count": feed.entry_count,
                    "active": feed.active
                }
                for feed in sorted(feeds, key=lambda f: f.entry_count, reverse=True)[:5]
            ]
        }


@server.tool()
def remove_source(feed_name: str, url: str) -> dict:
    """Remove a source URL from a feed for the current user.
    
    Args:
        feed_name: Name of the feed
        url: Source URL to remove
    
    Returns:
        Dictionary with operation result
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    success = storage.delete_source(feed_name, url)
    
    return {
        "user_id": user_id,
        "success": success,
        "feed_name": feed_name,
        "source_url": url,
        "message": f"Successfully removed source from '{feed_name}'" if success else "Source not found"
    }


@server.tool()
def get_entry_summary(feed_name: str, entry_guid: str, max_length: int = 500) -> dict:
    """Get a summary of a specific RSS entry.
    
    Args:
        feed_name: Name of the feed
        entry_guid: GUID/ID of the entry
        max_length: Maximum length of summary
    
    Returns:
        Dictionary with entry details
    """
    user_id = get_current_user_id()
    storage, _, _ = get_user_resources(user_id)
    
    # Find entry by GUID
    entries = storage.get_entries(feed_name=feed_name, limit=1000)
    entry = None
    for e in entries:
        if e.guid == entry_guid:
            entry = e
            break
    
    if not entry:
        return {
            "user_id": user_id,
            "success": False,
            "error": f"Entry not found in feed '{feed_name}'",
            "entry_guid": entry_guid
        }
    
    summary = entry.get_truncated_summary(max_length)
    
    return {
        "user_id": user_id,
        "success": True,
        "entry": {
            "feed_name": entry.feed_name,
            "title": entry.title,
            "link": entry.link,
            "published": entry.effective_published.isoformat(),
            "author": entry.author,
            "tags": entry.tags,
            "guid": entry.guid,
            "summary": summary
        }
    }


class UserContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract user ID from headers and set it in context."""
    
    async def dispatch(self, request: Request, call_next):
        # Extract user ID from headers
        headers = dict(request.headers)
        user_id, error_msg = get_user_id_safe(headers)
        
        # For non-MCP paths, we can return 401 directly
        if request.url.path.startswith("/mcp") and error_msg:
            return JSONResponse(
                status_code=401,
                content={"error": error_msg}
            )
        
        # Set user ID in context (use fallback if no error but no user ID)
        effective_user_id = user_id if not error_msg else os.getenv("RSS_MCP_USER", "default")
        
        # Set context and process request
        token = current_user_id.set(effective_user_id)
        try:
            response = await call_next(request)
            return response
        finally:
            current_user_id.reset(token)


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "RSS MCP FastMCP Server"})


async def user_info(request: Request):
    """Get user information from headers."""
    headers = dict(request.headers)
    user_id, error_msg = get_user_id_safe(headers)
    
    if error_msg:
        return JSONResponse(
            status_code=401,
            content={"error": error_msg}
        )
    
    return JSONResponse({
        "user_id": user_id,
        "headers_provided": True
    })


def create_starlette_app() -> Starlette:
    """Create Starlette app with FastMCP server and user context middleware."""
    # Create the FastMCP app (use http_app instead of deprecated streamable_http_app)
    fastmcp_app = server.http_app()
    
    # Create main Starlette app
    app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/user-info", user_info),
            Mount("/mcp", app=fastmcp_app),  # Mount FastMCP at /mcp
            Mount("/", app=fastmcp_app),     # Also mount at root for compatibility
        ]
    )
    
    # Add user context middleware
    app.add_middleware(UserContextMiddleware)
    
    return app


async def run_fastmcp_http(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastMCP server in HTTP mode with custom middleware."""
    import uvicorn
    
    logger.info(f"Starting FastMCP RSS server on {host}:{port}")
    logger.info(f"MCP endpoint will be available at http://{host}:{port}/mcp")
    logger.info("Send X-User-ID header to identify different users")
    
    # Create the Starlette app with middleware
    app = create_starlette_app()
    
    # Configure and run server
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info"
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


async def run_fastmcp_stdio():
    """Run the FastMCP server in stdio mode."""
    # In stdio mode, user is determined by environment variable
    user_id = os.getenv("RSS_MCP_USER", "default")
    logger.info(f"Starting FastMCP server in stdio mode for user: {user_id}")
    
    # Set user context for stdio mode
    token = current_user_id.set(user_id)
    
    try:
        # Pre-create resources for this user
        get_user_resources(user_id)
        
        # Run in stdio mode
        await server.run_stdio_async()
    finally:
        current_user_id.reset(token)


# Cleanup function for graceful shutdown
async def cleanup_resources():
    """Clean up all user resources."""
    for user_id, fetcher in _user_fetchers.items():
        try:
            await fetcher.close()
            logger.info(f"Cleaned up resources for user: {user_id}")
        except Exception as e:
            logger.error(f"Error cleaning up resources for user {user_id}: {e}")
    
    _user_storages.clear()
    _user_fetchers.clear()
    _user_configs.clear()


if __name__ == "__main__":
    import sys
    
    async def main():
        try:
            if len(sys.argv) > 1 and sys.argv[1] == "http":
                port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
                await run_fastmcp_http(port=port)
            else:
                await run_fastmcp_stdio()
        finally:
            await cleanup_resources()
    
    asyncio.run(main())
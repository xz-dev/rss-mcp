"""Multi-user FastMCP server implementation using Starlette with context-aware tools."""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from .config import get_config_manager, get_user_id_safe
from .feed_manager import FeedFetcher
from .models import RSSFeed, RSSSource
from .storage import RSSStorage

logger = logging.getLogger(__name__)

# Global storage for user-specific resources
_user_storages: Dict[str, RSSStorage] = {}
_user_fetchers: Dict[str, FeedFetcher] = {}


def get_user_resources(user_id: str) -> tuple[RSSStorage, FeedFetcher]:
    """Get or create user-specific storage and fetcher."""
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
        
        logger.info(f"Created resources for user: {user_id}")
    
    return _user_storages[user_id], _user_fetchers[user_id]


def get_user_id_from_context() -> str:
    """Get user ID from the current request context using FastMCP's context."""
    try:
        # FastMCP provides access to the current context during tool execution
        context = mcp.get_context()
        
        # Get the request from context
        if hasattr(context, 'request'):
            request = context.request
            headers = dict(request.headers) if hasattr(request, 'headers') else {}
            
            # Get user ID from headers
            user_id, error_msg = get_user_id_safe(headers)
            
            if error_msg:
                logger.debug(f"No valid user ID in headers: {error_msg}")
                # Fall through to use default
            else:
                return user_id
    except Exception as e:
        logger.debug(f"Could not get user from context: {e}")
    
    # Fallback for non-HTTP contexts (like stdio) or when no header provided
    user_id = os.getenv("RSS_MCP_USER", "default")
    logger.debug(f"Using fallback user ID: {user_id}")
    return user_id


# Create the main FastMCP server
mcp = FastMCP(
    name="RSS MCP Multi-User Server",
    streamable_http_path="/mcp"
)


@mcp.tool()
def list_feeds() -> dict:
    """List all RSS feeds for the current user."""
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    feeds = storage.get_feeds()
    return {
        "user_id": user_id,
        "feeds": [
            {
                "name": feed.name,
                "title": feed.title,
                "enabled": feed.enabled,
                "source_count": len(feed.sources),
            }
            for feed in feeds
        ]
    }


@mcp.tool()
def get_entries(
    feed_name: Optional[str] = None,
    limit: int = 20,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> dict:
    """Get RSS entries for the current user."""
    from dateutil import parser as date_parser
    
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    since_dt = date_parser.parse(since) if since else None
    until_dt = date_parser.parse(until) if until else None
    
    entries = storage.get_entries(
        feed_name=feed_name,
        limit=limit,
        since=since_dt,
        until=until_dt
    )
    
    return {
        "user_id": user_id,
        "entries": [
            {
                "feed_name": entry.feed_name,
                "title": entry.title,
                "link": entry.link,
                "description": entry.description[:200] if entry.description else None,
                "published": entry.published.isoformat() if entry.published else None,
            }
            for entry in entries
        ]
    }


@mcp.tool()
def add_feed(name: str, title: str, description: Optional[str] = None) -> dict:
    """Add a new RSS feed for the current user."""
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    feed = RSSFeed(name=name, title=title, description=description)
    success = storage.create_feed(feed)
    
    return {
        "user_id": user_id,
        "success": success,
        "feed_name": name
    }


@mcp.tool()
def add_source(feed_name: str, url: str, priority: int = 0) -> dict:
    """Add a source URL to a feed for the current user."""
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    source = RSSSource(feed_name=feed_name, url=url, priority=priority)
    success = storage.create_source(source)
    
    return {
        "user_id": user_id,
        "success": success,
        "source_url": url
    }


@mcp.tool()
async def refresh_feeds(feed_name: Optional[str] = None) -> dict:
    """Refresh RSS feeds for the current user."""
    user_id = get_user_id_from_context()
    storage, fetcher = get_user_resources(user_id)
    
    if feed_name:
        feeds = [storage.get_feed(feed_name)]
    else:
        feeds = storage.get_feeds()
    
    success_count = 0
    error_count = 0
    
    for feed in feeds:
        if feed and feed.enabled:
            try:
                await fetcher.fetch_feed(feed)
                success_count += 1
            except Exception as e:
                logger.error(f"Error fetching feed {feed.name} for user {user_id}: {e}")
                error_count += 1
    
    return {
        "user_id": user_id,
        "success_count": success_count,
        "error_count": error_count,
        "message": f"Refreshed {success_count} feeds, {error_count} errors"
    }


@mcp.tool()
def delete_feed(feed_name: str) -> dict:
    """Delete a feed and all its entries for the current user."""
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    success = storage.delete_feed(feed_name)
    
    return {
        "user_id": user_id,
        "success": success,
        "deleted_feed": feed_name
    }


@mcp.tool()
def get_feed_stats(feed_name: Optional[str] = None) -> dict:
    """Get statistics about feeds for the current user."""
    user_id = get_user_id_from_context()
    storage, _ = get_user_resources(user_id)
    
    stats = storage.get_feed_stats(feed_name)
    
    return {
        "user_id": user_id,
        "total_feeds": stats.total_feeds,
        "total_entries": stats.total_entries,
        "total_sources": stats.total_sources,
        "last_refresh": stats.last_refresh.isoformat() if stats.last_refresh else None,
    }


class UserAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to validate user authentication for HTTP requests."""
    
    async def dispatch(self, request: Request, call_next):
        # Store the request in a place where FastMCP context can access it
        # This is a workaround since FastMCP doesn't expose direct context access
        request.state.original_request = request
        
        # For non-MCP paths, validate authentication
        if not request.url.path.startswith("/mcp"):
            headers = dict(request.headers)
            user_id, error_msg = get_user_id_safe(headers)
            
            if error_msg:
                return JSONResponse(
                    status_code=401,
                    content={"error": error_msg}
                )
        
        response = await call_next(request)
        return response


# Health check endpoint
async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "RSS MCP Multi-User Server"})


# User info endpoint
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


def create_app() -> Starlette:
    """Create the Starlette application with mounted FastMCP server."""
    app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/user-info", user_info),
            # Mount the FastMCP StreamableHTTP server
            Mount("/", app=mcp.streamable_http_app()),
        ]
    )
    
    # Add authentication middleware
    app.add_middleware(UserAuthMiddleware)
    
    return app


async def run_multiuser_fastmcp_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the multi-user FastMCP server in HTTP mode."""
    import uvicorn
    
    app = create_app()
    
    logger.info(f"Starting multi-user FastMCP server on {host}:{port}")
    logger.info(f"MCP endpoint will be available at http://{host}:{port}/mcp")
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_multiuser_fastmcp_stdio():
    """Run the multi-user FastMCP server in stdio mode."""
    # In stdio mode, user is determined by environment variable
    user_id = os.getenv("RSS_MCP_USER", "default")
    logger.info(f"Starting FastMCP server in stdio mode for user: {user_id}")
    
    # Pre-create resources for this user
    get_user_resources(user_id)
    
    # Run in stdio mode
    await mcp.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_multiuser_fastmcp_server())
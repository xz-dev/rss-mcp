"""Multi-user FastMCP server implementation using Starlette."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from .config import get_config_manager, get_user_id_safe
from .feed_manager import FeedFetcher
from .models import RSSFeed, RSSSource
from .storage import RSSStorage

logger = logging.getLogger(__name__)

# Global storage for user-specific FastMCP instances
_user_servers: Dict[str, FastMCP] = {}
_user_storages: Dict[str, RSSStorage] = {}
_user_fetchers: Dict[str, FeedFetcher] = {}


def create_user_fastmcp_server(user_id: str) -> FastMCP:
    """Create a FastMCP server instance for a specific user."""
    if user_id in _user_servers:
        return _user_servers[user_id]
    
    logger.info(f"Creating FastMCP server for user: {user_id}")
    
    # Create user-specific server
    server = FastMCP(
        name=f"RSS MCP Server (User: {user_id})",
        streamable_http_path="/"  # Mount at root of user path
    )
    
    # Get user-specific config and storage
    config_manager = get_config_manager(user_id=user_id)
    config = config_manager.config
    storage = RSSStorage(Path(config.cache_path))
    feed_fetcher = FeedFetcher(config, storage)
    
    # Store instances
    _user_servers[user_id] = server
    _user_storages[user_id] = storage
    _user_fetchers[user_id] = feed_fetcher
    
    # Register tools for this user's server
    register_user_tools(server, storage, feed_fetcher, user_id)
    
    return server


def register_user_tools(server: FastMCP, storage: RSSStorage, feed_fetcher: FeedFetcher, user_id: str):
    """Register tools for a user-specific FastMCP server."""
    
    @server.tool()
    def list_feeds() -> dict:
        """List all RSS feeds."""
        feeds = storage.get_feeds()
        return {
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
    
    @server.tool()
    def get_entries(
        feed_name: Optional[str] = None,
        limit: int = 20,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> dict:
        """Get RSS entries."""
        from dateutil import parser as date_parser
        
        since_dt = date_parser.parse(since) if since else None
        until_dt = date_parser.parse(until) if until else None
        
        entries = storage.get_entries(
            feed_name=feed_name,
            limit=limit,
            since=since_dt,
            until=until_dt
        )
        
        return {
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
    
    @server.tool()
    def add_feed(name: str, title: str, description: Optional[str] = None) -> dict:
        """Add a new RSS feed."""
        feed = RSSFeed(name=name, title=title, description=description)
        success = storage.create_feed(feed)
        return {"success": success, "feed_name": name}
    
    @server.tool()
    def add_source(feed_name: str, url: str, priority: int = 0) -> dict:
        """Add a source URL to a feed."""
        source = RSSSource(feed_name=feed_name, url=url, priority=priority)
        success = storage.create_source(source)
        return {"success": success, "source_url": url}
    
    @server.tool()
    async def refresh_feeds(feed_name: Optional[str] = None) -> dict:
        """Refresh RSS feeds."""
        if feed_name:
            feeds = [storage.get_feed(feed_name)]
        else:
            feeds = storage.get_feeds()
        
        success_count = 0
        error_count = 0
        
        for feed in feeds:
            if feed and feed.enabled:
                try:
                    await feed_fetcher.fetch_feed(feed)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error fetching feed {feed.name}: {e}")
                    error_count += 1
        
        return {
            "success_count": success_count,
            "error_count": error_count,
            "message": f"Refreshed {success_count} feeds, {error_count} errors"
        }
    
    @server.tool()
    def delete_feed(feed_name: str) -> dict:
        """Delete a feed and all its entries."""
        success = storage.delete_feed(feed_name)
        return {"success": success, "deleted_feed": feed_name}
    
    @server.tool()
    def get_feed_stats(feed_name: Optional[str] = None) -> dict:
        """Get statistics about feeds."""
        stats = storage.get_feed_stats(feed_name)
        return {
            "total_feeds": stats.total_feeds,
            "total_entries": stats.total_entries,
            "total_sources": stats.total_sources,
            "last_refresh": stats.last_refresh.isoformat() if stats.last_refresh else None,
        }
    
    # FastMCP doesn't expose tools list directly, just log that registration is complete
    logger.info(f"Registered tools for user {user_id}")


class UserRoutingMiddleware(BaseHTTPMiddleware):
    """Middleware to route requests to user-specific FastMCP servers."""
    
    async def dispatch(self, request: Request, call_next):
        # Check if this is an MCP request
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)
        
        # Get user ID from headers
        headers = dict(request.headers)
        user_id, error_msg = get_user_id_safe(headers)
        
        if error_msg:
            # No valid user ID, return 401
            logger.warning(f"Request denied - {error_msg}")
            return JSONResponse(
                status_code=401,
                content={"error": error_msg}
            )
        
        # Store user ID in request state for downstream use
        request.state.user_id = user_id
        
        # Continue processing
        response = await call_next(request)
        return response


async def health_check(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "RSS MCP Multi-User Server"})


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


async def handle_mcp_request(request: Request):
    """Handle MCP requests by routing to user-specific server."""
    # Get user ID from request state (set by middleware)
    user_id = getattr(request.state, "user_id", None)
    
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"error": "User ID not found in request"}
        )
    
    # Get or create user-specific server
    server = create_user_fastmcp_server(user_id)
    
    # Get the streamable HTTP app for this user's server
    user_app = server.streamable_http_app()
    
    # Forward the request to the user's server
    # Note: This is a simplified approach. In production, you'd want
    # to properly handle the ASGI protocol
    response = await user_app(request.scope, request.receive, request.send)
    return response


def create_multiuser_app() -> Starlette:
    """Create the multi-user Starlette application."""
    app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/user-info", user_info),
            # All /mcp/* requests will be handled dynamically
            Mount("/mcp", app=create_dynamic_mcp_handler()),
        ]
    )
    
    # Add user routing middleware
    app.add_middleware(UserRoutingMiddleware)
    
    return app


def create_dynamic_mcp_handler():
    """Create a dynamic handler that routes to user-specific MCP servers."""
    class DynamicMCPHandler:
        def __init__(self):
            self.user_apps = {}
            self.initialization_lock = asyncio.Lock()
        
        async def __call__(self, scope, receive, send):
            # Extract user ID from scope (should be set by middleware)
            request = Request(scope, receive)
            headers = dict(request.headers)
            user_id, error_msg = get_user_id_safe(headers)
            
            if error_msg:
                response = JSONResponse(
                    status_code=401,
                    content={"error": error_msg}
                )
                await response(scope, receive, send)
                return
            
            # Get or create user-specific server and app
            async with self.initialization_lock:
                if user_id not in self.user_apps:
                    # Get or create user-specific server
                    server = create_user_fastmcp_server(user_id)
                    
                    # Create the streamable HTTP app for this user's server
                    # This needs to be created once and reused
                    user_app = server.streamable_http_app()
                    self.user_apps[user_id] = user_app
                    
                    # Initialize the app if needed
                    # The app needs to be started properly for the task group to be initialized
                    if hasattr(user_app, 'lifespan'):
                        # Handle lifespan events
                        pass
            
            # Get the cached app for this user
            user_app = self.user_apps[user_id]
            
            # Forward to user's server
            await user_app(scope, receive, send)
    
    return DynamicMCPHandler()


async def run_multiuser_fastmcp_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the multi-user FastMCP server in HTTP mode."""
    import uvicorn
    
    app = create_multiuser_app()
    
    logger.info(f"Starting multi-user FastMCP server on {host}:{port}")
    
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_multiuser_fastmcp_stdio():
    """Run the multi-user FastMCP server in stdio mode.
    
    In stdio mode, the user ID is determined from the RSS_MCP_USER environment variable.
    """
    import os
    
    # Get user ID from environment for stdio mode
    user_id = os.getenv("RSS_MCP_USER", "default")
    logger.info(f"Starting FastMCP server in stdio mode for user: {user_id}")
    
    # Create or get user-specific server
    server = create_user_fastmcp_server(user_id)
    
    # Run in stdio mode
    await server.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_multiuser_fastmcp_server())
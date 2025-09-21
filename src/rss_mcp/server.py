"""MCP server implementation for RSS management."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    GetPromptRequest,
    ListToolsRequest,
    ServerCapabilities,
    ToolsCapability,
    Tool,
    TextContent,
)
from dateutil import parser as date_parser
from pydantic import BaseModel

from .config import get_config_manager, RSSConfig, get_user_id
from .feed_manager import FeedFetcher
from .models import RSSFeed, RSSSource
from .storage import RSSStorage


logger = logging.getLogger(__name__)


class RSSMCPServer:
    """RSS MCP Server with both stdio and HTTP transports."""
    
    def __init__(self, user_id: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        """Initialize the server.
        
        Args:
            user_id: User ID for per-user configuration
            headers: Optional HTTP headers for extracting user ID
        """
        self.server = Server("rss-mcp")
        self.current_user_id = user_id or get_user_id(headers)
        self.config_manager = get_config_manager(user_id=self.current_user_id, headers=headers)
        self.config = self.config_manager.config
        self.storage = RSSStorage(Path(self.config.cache_path))
        self.fetcher = FeedFetcher(self.config, self.storage)
        
        # Register handlers
        self._register_handlers()
        
        # Watch config changes
        self.config_manager.add_change_callback(self._on_config_changed)
    
    def _on_config_changed(self, new_config: RSSConfig):
        """Handle configuration changes."""
        logger.info("Configuration changed, updating server")
        self.config = new_config
        # Recreate storage and fetcher with new config
        self.storage = RSSStorage(Path(new_config.cache_path))
        self.fetcher = FeedFetcher(new_config, self.storage)
    
    def _register_handlers(self):
        """Register MCP handlers."""
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="list_feeds",
                    description="List all RSS feeds with their sources and status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "active_only": {
                                "type": "boolean",
                                "description": "Only return active feeds",
                                "default": False
                            }
                        }
                    }
                ),
                Tool(
                    name="add_feed",
                    description="Add a new RSS feed with source URLs",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Unique name for the feed"
                            },
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of RSS source URLs"
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional feed title"
                            },
                            "description": {
                                "type": "string", 
                                "description": "Optional feed description"
                            },
                            "fetch_interval": {
                                "type": "integer",
                                "description": "Fetch interval in seconds",
                                "default": 3600
                            }
                        },
                        "required": ["name", "urls"]
                    }
                ),
                Tool(
                    name="remove_feed",
                    description="Remove an RSS feed and all its data",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the feed to remove"
                            }
                        },
                        "required": ["name"]
                    }
                ),
                Tool(
                    name="add_source",
                    description="Add a source URL to an existing feed",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Name of the feed"
                            },
                            "url": {
                                "type": "string",
                                "description": "RSS source URL"
                            },
                            "priority": {
                                "type": "integer",
                                "description": "Source priority (lower = higher priority)",
                                "default": 0
                            }
                        },
                        "required": ["feed_name", "url"]
                    }
                ),
                Tool(
                    name="remove_source",
                    description="Remove a source URL from a feed",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Name of the feed"
                            },
                            "url": {
                                "type": "string",
                                "description": "RSS source URL to remove"
                            }
                        },
                        "required": ["feed_name", "url"]
                    }
                ),
                Tool(
                    name="get_entries",
                    description="Get RSS entries with optional filtering and pagination",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Filter by feed name (optional)"
                            },
                            "start_time": {
                                "type": "string",
                                "description": "Start time filter (ISO format or relative like '1 day ago')"
                            },
                            "end_time": {
                                "type": "string",
                                "description": "End time filter (ISO format)"
                            },
                            "page": {
                                "type": "integer",
                                "description": "Page number (1-based)",
                                "default": 1
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Number of entries per page",
                                "default": 20,
                                "maximum": 100
                            }
                        }
                    }
                ),
                Tool(
                    name="get_entry_summary",
                    description="Get a summary of a specific RSS entry",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Name of the feed"
                            },
                            "entry_guid": {
                                "type": "string",
                                "description": "GUID/ID of the entry"
                            },
                            "max_length": {
                                "type": "integer",
                                "description": "Maximum length of summary",
                                "default": 500
                            }
                        },
                        "required": ["feed_name", "entry_guid"]
                    }
                ),
                Tool(
                    name="refresh_feeds",
                    description="Refresh RSS feeds to fetch new entries",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Specific feed to refresh (optional, refreshes all if not specified)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_feed_stats",
                    description="Get statistics for RSS feeds",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "feed_name": {
                                "type": "string",
                                "description": "Specific feed name (optional, gets overall stats if not specified)"
                            }
                        }
                    }
                ),
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> Sequence[TextContent]:
            """Handle tool calls."""
            try:
                if name == "list_feeds":
                    return await self._handle_list_feeds(arguments)
                elif name == "add_feed":
                    return await self._handle_add_feed(arguments)
                elif name == "remove_feed":
                    return await self._handle_remove_feed(arguments)
                elif name == "add_source":
                    return await self._handle_add_source(arguments)
                elif name == "remove_source":
                    return await self._handle_remove_source(arguments)
                elif name == "get_entries":
                    return await self._handle_get_entries(arguments)
                elif name == "get_entry_summary":
                    return await self._handle_get_entry_summary(arguments)
                elif name == "refresh_feeds":
                    return await self._handle_refresh_feeds(arguments)
                elif name == "get_feed_stats":
                    return await self._handle_get_feed_stats(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                    
            except Exception as e:
                logger.error(f"Error handling tool {name}: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _handle_list_feeds(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle list_feeds tool call."""
        active_only = args.get("active_only", False)
        feeds = self.storage.list_feeds(active_only=active_only)
        
        if not feeds:
            return [TextContent(type="text", text="No feeds found")]
        
        result = []
        result.append("RSS Feeds:\n")
        
        for feed in feeds:
            status = "🟢 Active" if feed.active else "🔴 Inactive"
            result.append(f"**{feed.name}** ({status})")
            result.append(f"  Title: {feed.title}")
            result.append(f"  Entries: {feed.entry_count}")
            result.append(f"  Sources: {len(feed.sources)}")
            
            for source in feed.sources:
                src_status = "🟢" if source.active and source.is_healthy else "🔴"
                result.append(f"    {src_status} [{source.priority}] {source.url}")
                if source.error_count > 0:
                    result.append(f"        Errors: {source.error_count}")
            
            if feed.last_success:
                result.append(f"  Last Success: {feed.last_success}")
            result.append("")
        
        return [TextContent(type="text", text="\n".join(result))]
    
    async def _handle_add_feed(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle add_feed tool call."""
        name = args["name"]
        urls = args["urls"]
        title = args.get("title", name)
        description = args.get("description", "")
        fetch_interval = args.get("fetch_interval", self.config.default_fetch_interval)
        
        # Check if feed already exists
        if self.storage.get_feed(name):
            return [TextContent(type="text", text=f"Error: Feed '{name}' already exists")]
        
        # Create feed
        feed = RSSFeed(
            name=name,
            title=title,
            description=description,
            fetch_interval=fetch_interval,
        )
        
        # Save feed to storage
        if not self.storage.create_feed(feed):
            return [TextContent(type="text", text=f"Error: Failed to create feed '{name}'")]
        
        # Create sources separately  
        sources_created = 0
        for i, url in enumerate(urls):
            source = RSSSource(
                feed_name=name,
                url=url,
                priority=i,  # Use order as priority
            )
            if self.storage.create_source(source):
                sources_created += 1
        
        return [TextContent(type="text", text=f"✓ Added feed '{name}' with {sources_created} source(s)")]
    
    async def _handle_remove_feed(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle remove_feed tool call."""
        name = args["name"]
        
        if self.storage.delete_feed(name):
            return [TextContent(type="text", text=f"✓ Removed feed '{name}' and all its data")]
        else:
            return [TextContent(type="text", text=f"Error: Feed '{name}' not found")]
    
    async def _handle_add_source(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle add_source tool call."""
        feed_name = args["feed_name"]
        url = args["url"]
        priority = args.get("priority", 0)
        
        # Check if feed exists
        if not self.storage.get_feed(feed_name):
            return [TextContent(type="text", text=f"Error: Feed '{feed_name}' not found")]
        
        # Create source
        source = RSSSource(
            feed_name=feed_name,
            url=url,
            priority=priority,
        )
        
        if self.storage.create_source(source):
            return [TextContent(type="text", text=f"✓ Added source {url} to feed '{feed_name}'")]
        else:
            return [TextContent(type="text", text="Error: Source already exists or failed to create")]
    
    async def _handle_remove_source(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle remove_source tool call."""
        feed_name = args["feed_name"]
        url = args["url"]
        
        if self.storage.delete_source(feed_name, url):
            return [TextContent(type="text", text=f"✓ Removed source {url} from feed '{feed_name}'")]
        else:
            return [TextContent(type="text", text="Error: Source not found")]
    
    async def _handle_get_entries(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle get_entries tool call."""
        feed_name = args.get("feed_name")
        start_time_str = args.get("start_time")
        end_time_str = args.get("end_time")
        page = max(1, args.get("page", 1))
        page_size = min(100, max(1, args.get("page_size", 20)))
        
        # Parse time filters
        start_time = self._parse_time_filter(start_time_str) if start_time_str else None
        end_time = self._parse_time_filter(end_time_str) if end_time_str else None
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get entries
        entries = self.storage.get_entries(
            feed_name=feed_name,
            start_time=start_time,
            end_time=end_time,
            limit=page_size,
            offset=offset
        )
        
        if not entries:
            return [TextContent(type="text", text="No entries found")]
        
        # Get total count for pagination info
        total_count = self.storage.get_entry_count(
            feed_name=feed_name,
            start_time=start_time,
            end_time=end_time
        )
        
        result = []
        total_pages = (total_count + page_size - 1) // page_size
        result.append(f"RSS Entries (Page {page}/{total_pages}, {len(entries)} of {total_count})\n")
        
        for entry in entries:
            pub_date = entry.effective_published.strftime('%Y-%m-%d %H:%M')
            result.append(f"**{entry.title}**")
            result.append(f"  Feed: {entry.feed_name}")
            result.append(f"  Published: {pub_date}")
            result.append(f"  Link: {entry.link}")
            if entry.author:
                result.append(f"  Author: {entry.author}")
            if entry.tags:
                result.append(f"  Tags: {', '.join(entry.tags)}")
            result.append(f"  Summary: {entry.get_truncated_summary(150)}")
            result.append("")
        
        return [TextContent(type="text", text="\n".join(result))]
    
    async def _handle_get_entry_summary(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle get_entry_summary tool call."""
        feed_name = args["feed_name"]
        entry_guid = args["entry_guid"]
        max_length = args.get("max_length", 500)
        
        # Find entry by GUID
        entries = self.storage.get_entries(feed_name=feed_name, limit=1000)  # Get many to search
        entry = None
        for e in entries:
            if e.guid == entry_guid:
                entry = e
                break
        
        if not entry:
            return [TextContent(type="text", text=f"Error: Entry not found in feed '{feed_name}'")]
        
        summary = entry.get_truncated_summary(max_length)
        
        result = []
        result.append(f"**{entry.title}**")
        result.append(f"Feed: {entry.feed_name}")
        result.append(f"Published: {entry.effective_published}")
        result.append(f"Link: {entry.link}")
        if entry.author:
            result.append(f"Author: {entry.author}")
        result.append(f"\nSummary:\n{summary}")
        
        return [TextContent(type="text", text="\n".join(result))]
    
    async def _handle_refresh_feeds(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle refresh_feeds tool call."""
        feed_name = args.get("feed_name")
        
        if feed_name:
            # Refresh specific feed
            success, message = await self.fetcher.refresh_feed(feed_name)
            status = "✓" if success else "✗"
            return [TextContent(type="text", text=f"{status} {message}")]
        else:
            # Refresh all active feeds
            results = await self.fetcher.refresh_all_feeds()
            
            result_lines = ["Feed Refresh Results:\n"]
            success_count = 0
            
            for feed_name, success, message in results:
                status = "✓" if success else "✗"
                result_lines.append(f"{status} {message}")
                if success:
                    success_count += 1
            
            result_lines.append(f"\n{success_count}/{len(results)} feeds updated successfully")
            
            return [TextContent(type="text", text="\n".join(result_lines))]
    
    async def _handle_get_feed_stats(self, args: Dict[str, Any]) -> Sequence[TextContent]:
        """Handle get_feed_stats tool call."""
        feed_name = args.get("feed_name")
        
        if feed_name:
            # Get stats for specific feed
            stats = self.storage.get_feed_stats(feed_name)
            
            result = []
            result.append(f"📊 Statistics for feed '{feed_name}':")
            result.append(f"  Total entries: {stats.total_entries}")
            result.append(f"  Last 24h: {stats.entries_last_24h}")
            result.append(f"  Last 7 days: {stats.entries_last_7d}")
            result.append(f"  Active sources: {stats.active_sources}")
            result.append(f"  Healthy sources: {stats.healthy_sources}")
            if stats.last_success:
                result.append(f"  Last success: {stats.last_success}")
            
            return [TextContent(type="text", text="\n".join(result))]
        else:
            # Get overall stats
            feeds = self.storage.list_feeds()
            active_feeds = [f for f in feeds if f.active]
            total_entries = sum(f.entry_count for f in feeds)
            
            result = []
            result.append("📊 Overall Statistics:")
            result.append(f"  Total feeds: {len(feeds)}")
            result.append(f"  Active feeds: {len(active_feeds)}")
            result.append(f"  Total entries: {total_entries}")
            
            # Show top feeds
            if feeds:
                top_feeds = sorted(feeds, key=lambda f: f.entry_count, reverse=True)[:5]
                result.append("\n  Top feeds by entry count:")
                for feed in top_feeds:
                    status = "🟢" if feed.active else "🔴"
                    result.append(f"    {status} {feed.name}: {feed.entry_count} entries")
            
            return [TextContent(type="text", text="\n".join(result))]
    
    def _parse_time_filter(self, time_str: str) -> Optional[datetime]:
        """Parse time filter string."""
        if not time_str:
            return None
        
        time_str = time_str.strip().lower()
        
        # Handle relative times
        if 'ago' in time_str:
            from datetime import timedelta
            parts = time_str.replace('ago', '').strip().split()
            if len(parts) == 2:
                try:
                    num = int(parts[0])
                    unit = parts[1].rstrip('s')  # Remove plural 's'
                    
                    now = datetime.now()
                    if unit in ('day', 'days'):
                        return now - timedelta(days=num)
                    elif unit in ('hour', 'hours'):
                        return now - timedelta(hours=num)
                    elif unit in ('week', 'weeks'):
                        return now - timedelta(weeks=num)
                    elif unit in ('month', 'months'):
                        return now - timedelta(days=num * 30)
                except ValueError:
                    pass
        
        # Parse absolute time
        try:
            return date_parser.parse(time_str)
        except Exception:
            return None
    
    async def cleanup(self):
        """Clean up resources."""
        await self.fetcher.close()
        self.config_manager.stop_watching()


# Global server instances per user
_server_instances: Dict[str, RSSMCPServer] = {}


def get_server(user_id: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> RSSMCPServer:
    """Get the server instance for a specific user."""
    effective_user_id = user_id or get_user_id(headers)
    
    if effective_user_id not in _server_instances:
        _server_instances[effective_user_id] = RSSMCPServer(effective_user_id, headers)
    
    return _server_instances[effective_user_id]


async def run_stdio_server():
    """Run the MCP server in stdio mode."""
    server = get_server()
    
    # Start config watching
    server.config_manager.start_watching()
    
    try:
        async with stdio_server(server.server) as streams:
            await server.server.run(*streams, InitializationOptions(
                server_name="rss-mcp",
                server_version="1.0.0",
                capabilities=ServerCapabilities(
                    tools=ToolsCapability(listChanged=False)
                )
            ))
    finally:
        await server.cleanup()


async def run_http_server(host: str = "localhost", port: int = 8080):
    """Run the MCP server in HTTP mode."""
    # Create FastAPI app
    app = FastAPI(title="RSS MCP Server", version="1.0.0")
    
    class ToolCallRequest(BaseModel):
        name: str
        arguments: Dict[str, Any]
    
    @app.get("/")
    async def root():
        return {
            "message": "RSS MCP Server", 
            "version": "1.0.0",
            "endpoints": {
                "mcp": {
                    "tools": "/mcp/tools",
                    "call-tool": "/mcp/call-tool",
                    "health": "/mcp/health",
                    "user-info": "/mcp/user-info"
                },
                "sse": {
                    "feed-updates": "/sse/feed-updates",
                    "tool-calls": "/sse/tool-calls"
                }
            }
        }
    
    # MCP HTTP Routes
    @app.get("/mcp/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    @app.get("/mcp/user-info")
    async def user_info(request: Request):
        """Get current user information."""
        headers = dict(request.headers)
        user_id = get_user_id(headers)
        return {"user_id": user_id, "headers_provided": bool(headers.get("X-User-ID"))}
    
    @app.get("/mcp/tools")
    async def list_tools(request: Request):
        """List available MCP tools."""
        # Get user-specific server instance
        headers = dict(request.headers)
        server = get_server(headers=headers)
        
        # Get the list tools handler function
        list_tools_handler = None
        for handler in server.server._tool_list_handlers:
            list_tools_handler = handler
            break
        
        if list_tools_handler:
            tools = await list_tools_handler()
            return {"tools": [tool.model_dump() for tool in tools]}
        else:
            return {"tools": []}
    
    @app.post("/mcp/call-tool")
    async def call_tool(request: ToolCallRequest, http_request: Request):
        """Call an MCP tool."""
        try:
            # Get user-specific server instance
            headers = dict(http_request.headers)
            server = get_server(headers=headers)
            
            # Get the call tool handler function
            call_tool_handler = None
            for handler in server.server._tool_call_handlers:
                call_tool_handler = handler
                break
            
            if call_tool_handler:
                results = await call_tool_handler(request.name, request.arguments)
                return {"results": [result.model_dump() for result in results]}
            else:
                raise HTTPException(status_code=404, detail="No tool handler found")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    # SSE Routes
    @app.get("/sse/feed-updates")
    async def sse_feed_updates(request: Request):
        """Server-Sent Events for real-time feed updates."""
        headers = dict(request.headers)
        user_id = get_user_id(headers)
        
        async def event_generator():
            """Generate SSE events for feed updates."""
            try:
                # Send initial connection event
                yield {
                    "event": "connected",
                    "data": f'{{"user_id": "{user_id}", "message": "Connected to RSS MCP feed updates"}}'
                }
                
                # Get user-specific server instance
                server = get_server(headers=headers)
                
                # Simulate feed update monitoring
                # In a real implementation, this would listen to feed changes
                import asyncio
                counter = 0
                while True:
                    await asyncio.sleep(30)  # Check every 30 seconds
                    counter += 1
                    
                    # Get feed stats as an example
                    feed_stats = server.storage.get_feed_stats()
                    
                    yield {
                        "event": "feed-update",
                        "data": f'{{"user_id": "{user_id}", "timestamp": "{datetime.now().isoformat()}", "total_entries": {feed_stats.total_entries}, "check_number": {counter}}}'
                    }
                    
            except Exception as e:
                yield {
                    "event": "error",
                    "data": f'{{"error": "{str(e)}"}}'
                }
        
        return EventSourceResponse(event_generator())
    
    @app.get("/sse/tool-calls")  
    async def sse_tool_calls(request: Request):
        """Server-Sent Events for tool call notifications."""
        headers = dict(request.headers)
        user_id = get_user_id(headers)
        
        async def event_generator():
            """Generate SSE events for tool calls."""
            try:
                yield {
                    "event": "connected", 
                    "data": f'{{"user_id": "{user_id}", "message": "Connected to RSS MCP tool call notifications"}}'
                }
                
                # This would be implemented with a proper event system
                # For now, just keep the connection alive
                import asyncio
                while True:
                    await asyncio.sleep(60)  # Keep alive ping
                    yield {
                        "event": "ping",
                        "data": f'{{"timestamp": "{datetime.now().isoformat()}"}}'
                    }
                    
            except Exception as e:
                yield {
                    "event": "error",
                    "data": f'{{"error": "{str(e)}"}}'
                }
        
        return EventSourceResponse(event_generator())
    
    # Configure server
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info"
    )
    
    server_instance = uvicorn.Server(config)
    
    try:
        await server_instance.serve()
    finally:
        # Cleanup all server instances
        for server in _server_instances.values():
            await server.cleanup()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "http":
        asyncio.run(run_http_server())
    else:
        asyncio.run(run_stdio_server())
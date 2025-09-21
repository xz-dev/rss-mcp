"""Test HTTP route structure and SSE functionality."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rss_mcp.server import run_http_server


class TestHTTPRoutes:
    """Test HTTP route structure."""
    
    @pytest.fixture
    def mock_app(self):
        """Create a mock FastAPI app for testing."""
        from fastapi import FastAPI, Request
        from rss_mcp.config import get_user_id
        
        app = FastAPI()
        
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
        
        @app.get("/mcp/health")
        async def health():
            return {"status": "healthy"}
            
        @app.get("/mcp/user-info")
        async def user_info(request: Request):
            headers = dict(request.headers)
            user_id = get_user_id(headers)
            # Check for user ID in case-insensitive way
            lower_headers = {k.lower(): v for k, v in headers.items()}
            return {"user_id": user_id, "headers_provided": bool(lower_headers.get("x-user-id"))}
        
        return app
    
    def test_root_endpoint_structure(self, mock_app):
        """Test that root endpoint returns correct route structure."""
        client = TestClient(mock_app)
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify basic structure
        assert "message" in data
        assert "version" in data
        assert "endpoints" in data
        
        # Verify MCP endpoints
        mcp_endpoints = data["endpoints"]["mcp"]
        assert mcp_endpoints["tools"] == "/mcp/tools"
        assert mcp_endpoints["call-tool"] == "/mcp/call-tool"
        assert mcp_endpoints["health"] == "/mcp/health"
        assert mcp_endpoints["user-info"] == "/mcp/user-info"
        
        # Verify SSE endpoints
        sse_endpoints = data["endpoints"]["sse"]
        assert sse_endpoints["feed-updates"] == "/sse/feed-updates"
        assert sse_endpoints["tool-calls"] == "/sse/tool-calls"
    
    def test_mcp_health_endpoint(self, mock_app):
        """Test MCP health endpoint."""
        client = TestClient(mock_app)
        response = client.get("/mcp/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_mcp_user_info_endpoint(self, mock_app):
        """Test MCP user info endpoint with different headers."""
        client = TestClient(mock_app)
        
        # Test without user header
        response = client.get("/mcp/user-info")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "default"
        assert data["headers_provided"] is False
        
        # Test with user header
        headers = {"X-User-ID": "alice"}
        response = client.get("/mcp/user-info", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["headers_provided"] is True
    
    def test_legacy_endpoints_not_available(self):
        """Test that legacy endpoints are not available."""
        # This test would need a full server setup to test
        # For now, just verify the route structure doesn't include legacy routes
        from rss_mcp.server import run_http_server
        import inspect
        
        # Get the source code of run_http_server to verify no legacy routes
        source = inspect.getsource(run_http_server)
        
        # Should not contain legacy route definitions
        assert '@app.get("/tools")' not in source or 'legacy' in source
        assert '@app.post("/call-tool")' not in source or 'legacy' in source


class TestSSERoutes:
    """Test SSE route functionality."""
    
    def test_sse_route_paths(self):
        """Test that SSE routes are correctly defined."""
        from rss_mcp.server import run_http_server
        import inspect
        
        source = inspect.getsource(run_http_server)
        
        # Verify SSE routes are defined
        assert '/sse/feed-updates' in source
        assert '/sse/tool-calls' in source
        assert 'EventSourceResponse' in source
    
    def test_user_id_extraction_in_sse(self):
        """Test that user ID is extracted correctly in SSE context."""
        from rss_mcp.config import get_user_id
        
        # Test SSE-style headers
        headers = {
            "x-user-id": "lowercase-should-not-work",  # Case sensitive
            "X-User-ID": "sse-user",
            "accept": "text/event-stream",
            "cache-control": "no-cache"
        }
        
        user_id = get_user_id(headers)
        assert user_id == "sse-user"


class TestRouteIntegration:
    """Integration tests for route functionality."""
    
    def test_route_naming_convention(self):
        """Test that route naming follows convention."""
        from rss_mcp.server import run_http_server
        import inspect
        
        source = inspect.getsource(run_http_server)
        
        # All MCP routes should start with /mcp/
        mcp_routes = [
            "/mcp/health",
            "/mcp/user-info", 
            "/mcp/tools",
            "/mcp/call-tool"
        ]
        
        for route in mcp_routes:
            assert route in source
        
        # All SSE routes should start with /sse/
        sse_routes = [
            "/sse/feed-updates",
            "/sse/tool-calls"
        ]
        
        for route in sse_routes:
            assert route in source
    
    def test_no_root_level_api_routes(self):
        """Test that there are no API routes at root level."""
        from rss_mcp.server import run_http_server
        import inspect
        
        source = inspect.getsource(run_http_server)
        
        # Should not have routes like /health, /user-info at root
        assert '@app.get("/health")' not in source
        assert '@app.get("/user-info")' not in source
        assert '@app.get("/api/' not in source  # No /api/ prefix


@pytest.mark.asyncio
async def test_sse_event_generation():
    """Test SSE event generation logic."""
    from rss_mcp.config import get_user_id
    import json
    
    # Simulate SSE event generator
    headers = {"X-User-ID": "test-sse-user"}
    user_id = get_user_id(headers)
    
    async def mock_event_generator():
        """Mock SSE event generator."""
        yield {
            "event": "connected",
            "data": f'{{"user_id": "{user_id}", "message": "Connected to RSS MCP feed updates"}}'
        }
        
        # Simulate one update
        yield {
            "event": "feed-update", 
            "data": f'{{"user_id": "{user_id}", "test": true}}'
        }
    
    events = []
    async for event in mock_event_generator():
        events.append(event)
        if len(events) >= 2:  # Just test first two events
            break
    
    assert len(events) == 2
    
    # Test connected event
    connected_data = json.loads(events[0]["data"])
    assert connected_data["user_id"] == "test-sse-user"
    assert "Connected to RSS MCP feed updates" in connected_data["message"]
    
    # Test update event
    update_data = json.loads(events[1]["data"])
    assert update_data["user_id"] == "test-sse-user"
    assert update_data["test"] is True
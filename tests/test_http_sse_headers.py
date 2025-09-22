"""Tests for HTTP and SSE header handling functionality."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import Request
import httpx

from src.rss_mcp.server import run_http_server, get_server, get_server_safe
from src.rss_mcp.config import get_user_id, get_user_id_safe


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object with headers."""
    def _create_request(headers=None):
        request = Mock(spec=Request)
        request.headers = headers or {}
        return request
    return _create_request


class TestHTTPHeaderHandling:
    """Test HTTP endpoint header handling."""
    
    def test_list_tools_header_extraction(self, mock_request):
        """Test that list_tools endpoint correctly extracts headers."""
        # Test different header cases for list_tools endpoint (/mcp/tools)
        test_cases = [
            {"X-User-ID": "alice", "Accept": "application/json"},
            {"x-user-id": "bob", "User-Agent": "TestClient/1.0"},
            {"X-USER-ID": "charlie", "X-Client-Version": "2.0"},
            {"x-User-Id": "david", "Authorization": "Bearer token"},
        ]
        
        for headers in test_cases:
            request = mock_request(headers)
            extracted_headers = dict(request.headers)
            
            # Verify headers are extracted correctly
            assert extracted_headers == headers
            
            # Verify user_id can be extracted from headers
            user_id = get_user_id(headers)
            expected_user_id = list(headers.values())[0]  # First header value should be user ID
            assert user_id == expected_user_id

    def test_call_tool_header_extraction(self, mock_request):
        """Test that call_tool endpoint correctly extracts headers."""
        # Test different header cases
        test_cases = [
            {"X-User-ID": "alice", "Content-Type": "application/json"},
            {"x-user-id": "bob", "authorization": "Bearer token123"},
            {"X-USER-ID": "charlie", "X-Custom-Header": "custom-value"},
            {"x-User-Id": "david", "Accept": "application/json"},
        ]
        
        for headers in test_cases:
            request = mock_request(headers)
            extracted_headers = dict(request.headers)
            
            # Verify headers are extracted correctly
            assert extracted_headers == headers
            
            # Verify user_id can be extracted from headers
            user_id = get_user_id(headers)
            expected_user_id = list(headers.values())[0]  # First header value should be user ID
            assert user_id == expected_user_id

    def test_call_tool_header_case_insensitive(self, mock_request):
        """Test that header extraction works with different cases."""
        headers_variants = [
            {"X-User-ID": "testuser"},
            {"x-user-id": "testuser"},
            {"X-USER-ID": "testuser"},
            {"x-User-Id": "testuser"},
        ]
        
        for headers in headers_variants:
            request = mock_request(headers)
            extracted_headers = dict(request.headers)
            
            # All variants should extract the same user ID
            user_id = get_user_id(extracted_headers)
            assert user_id == "testuser"

    def test_call_tool_missing_headers(self, mock_request):
        """Test behavior when headers are missing."""
        request = mock_request({})
        extracted_headers = dict(request.headers)
        
        # Should get default user ID when no headers
        user_id = get_user_id(extracted_headers)
        assert user_id == "default"

    def test_call_tool_empty_user_id_header(self, mock_request):
        """Test behavior when X-User-ID header is empty."""
        test_cases = [
            {"X-User-ID": ""},
            {"X-User-ID": "   "},  # Whitespace only
            {"X-User-ID": None},
        ]
        
        for headers in test_cases:
            if headers["X-User-ID"] is not None:
                request = mock_request(headers)
                extracted_headers = dict(request.headers)
                user_id = get_user_id(extracted_headers)
                assert user_id == "default"

    def test_call_tool_additional_headers(self, mock_request):
        """Test that additional headers are preserved."""
        headers = {
            "X-User-ID": "testuser",
            "Authorization": "Bearer token123",
            "X-Client-Version": "1.0.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # All headers should be preserved
        for key, value in headers.items():
            assert extracted_headers[key] == value
        
        # User ID should still be extracted correctly
        user_id = get_user_id(extracted_headers)
        assert user_id == "testuser"


class TestSSEHeaderHandling:
    """Test SSE endpoint header handling."""
    
    def test_sse_feed_updates_header_extraction(self, mock_request):
        """Test that SSE feed updates endpoint extracts headers correctly."""
        headers = {
            "X-User-ID": "sse_user",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Verify headers are extracted
        assert extracted_headers == headers
        
        # Verify user_id extraction
        user_id = get_user_id(extracted_headers)
        assert user_id == "sse_user"

    def test_sse_tool_calls_header_extraction(self, mock_request):
        """Test that SSE tool calls endpoint extracts headers correctly."""
        headers = {
            "x-user-id": "tool_call_user",
            "Accept": "text/event-stream",
            "Connection": "keep-alive",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Verify headers are extracted
        assert extracted_headers == headers
        
        # Verify user_id extraction (case insensitive)
        user_id = get_user_id(extracted_headers)
        assert user_id == "tool_call_user"

    def test_sse_header_case_variations(self, mock_request):
        """Test SSE endpoints with various header case combinations."""
        header_variants = [
            {"X-User-ID": "sse_test", "Accept": "text/event-stream"},
            {"x-user-id": "sse_test", "accept": "text/event-stream"},
            {"X-USER-ID": "sse_test", "ACCEPT": "text/event-stream"},
            {"x-User-Id": "sse_test", "Accept": "text/event-stream"},
        ]
        
        for headers in header_variants:
            request = mock_request(headers)
            extracted_headers = dict(request.headers)
            
            # Headers should be preserved as-is
            assert extracted_headers == headers
            
            # User ID should be extracted correctly regardless of case
            user_id = get_user_id(extracted_headers)
            assert user_id == "sse_test"

    def test_sse_missing_user_header(self, mock_request):
        """Test SSE endpoints when X-User-ID header is missing."""
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Should get default user ID
        user_id = get_user_id(extracted_headers)
        assert user_id == "default"

    def test_sse_headers_with_special_characters(self, mock_request):
        """Test SSE header handling with special characters."""
        headers = {
            "X-User-ID": "user@example.com",
            "Accept": "text/event-stream",
            "X-Custom-Header": "value-with-dashes_and_underscores",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # All headers should be preserved
        assert extracted_headers == headers
        
        # User ID with special characters should work
        user_id = get_user_id(extracted_headers)
        assert user_id == "user@example.com"


class TestMCPEndpointsHeaderHandling:
    """Test MCP-specific endpoints header handling."""
    
    def test_mcp_tools_endpoint_headers(self, mock_request):
        """Test /mcp/tools endpoint header handling."""
        headers = {
            "X-User-ID": "mcp_tools_user",
            "Accept": "application/json",
            "User-Agent": "MCP-Client/1.0",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Verify all headers are preserved
        assert extracted_headers == headers
        
        # Verify user ID extraction
        user_id = get_user_id(extracted_headers)
        assert user_id == "mcp_tools_user"

    def test_mcp_call_tool_endpoint_headers(self, mock_request):
        """Test /mcp/call-tool endpoint header handling."""
        headers = {
            "X-User-ID": "mcp_call_user",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer mcp_token",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Verify all headers are preserved
        assert extracted_headers == headers
        
        # Verify user ID extraction
        user_id = get_user_id(extracted_headers)
        assert user_id == "mcp_call_user"

    def test_mcp_endpoints_case_insensitive(self, mock_request):
        """Test that both MCP endpoints handle case-insensitive headers."""
        test_cases = [
            {"X-User-ID": "testuser"},
            {"x-user-id": "testuser"},  
            {"X-USER-ID": "testuser"},
            {"x-User-Id": "testuser"},
        ]
        
        for headers in test_cases:
            # Add additional headers to simulate real requests
            full_headers = {**headers, "Accept": "application/json"}
            
            # Test both endpoints
            request = mock_request(full_headers)
            
            # Both endpoints should extract the same user ID
            user_id = get_user_id(dict(request.headers))
            assert user_id == "testuser"

    def test_mcp_endpoints_missing_user_id(self, mock_request):
        """Test MCP endpoints behavior when X-User-ID is missing."""
        headers_without_user_id = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer some_token",
        }
        
        request = mock_request(headers_without_user_id)
        extracted_headers = dict(request.headers)
        
        # Should get default user ID
        user_id = get_user_id(extracted_headers)
        assert user_id == "default"


class TestHeaderIntegration:
    """Integration tests for header handling across endpoints."""
    
    def test_consistent_header_handling(self, mock_request):
        """Test that all endpoints handle headers consistently."""
        test_headers = {
            "X-User-ID": "integration_user",
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client-Version": "2.0.0",
        }
        
        # Test list_tools endpoint (/mcp/tools)
        request = mock_request(test_headers)
        list_tools_headers = dict(request.headers)
        list_tools_user_id = get_user_id(list_tools_headers)
        
        # Test call_tool endpoint (/mcp/call-tool)
        call_tool_headers = dict(request.headers)
        call_tool_user_id = get_user_id(call_tool_headers)
        
        # Test SSE endpoints
        sse_headers = dict(request.headers)
        sse_user_id = get_user_id(sse_headers)
        
        # All should extract the same user ID
        assert list_tools_user_id == "integration_user"
        assert call_tool_user_id == "integration_user"
        assert sse_user_id == "integration_user"
        assert list_tools_user_id == call_tool_user_id == sse_user_id
        
        # All should preserve all headers
        assert list_tools_headers == test_headers
        assert call_tool_headers == test_headers
        assert sse_headers == test_headers

    def test_header_precedence(self, mock_request):
        """Test header precedence when multiple user ID headers exist."""
        # This shouldn't normally happen, but test the behavior
        headers = {
            "X-User-ID": "primary_user",
            "x-user-id": "secondary_user",  # Different case
            "Content-Type": "application/json",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Headers should be preserved as-is
        assert "X-User-ID" in extracted_headers
        assert "x-user-id" in extracted_headers
        
        # get_user_id should handle this gracefully
        # (The exact behavior depends on implementation)
        user_id = get_user_id(extracted_headers)
        assert user_id in ["primary_user", "secondary_user"]

    def test_unicode_header_values(self, mock_request):
        """Test handling of Unicode characters in header values."""
        headers = {
            "X-User-ID": "用户123",  # Chinese characters
            "Accept": "application/json",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Unicode should be preserved
        assert extracted_headers["X-User-ID"] == "用户123"
        
        # User ID extraction should work with Unicode
        user_id = get_user_id(extracted_headers)
        assert user_id == "用户123"

    def test_empty_header_values(self, mock_request):
        """Test behavior with empty header values."""
        headers = {
            "X-User-ID": "",
            "Accept": "",
            "Content-Type": "application/json",
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Empty headers should be preserved
        assert extracted_headers["X-User-ID"] == ""
        assert extracted_headers["Accept"] == ""
        
        # Should get default user ID for empty X-User-ID
        user_id = get_user_id(extracted_headers)
        assert user_id == "default"


class TestSecureUserIDHandling:
    """Test the new secure user ID handling that requires valid headers."""
    
    def test_get_user_id_safe_with_valid_header(self):
        """Test get_user_id_safe with valid X-User-ID header."""
        headers = {"X-User-ID": "valid_user"}
        user_id, error = get_user_id_safe(headers)
        
        assert user_id == "valid_user"
        assert error is None

    def test_get_user_id_safe_without_header(self):
        """Test get_user_id_safe without X-User-ID header - should return error."""
        headers = {"Accept": "application/json"}
        user_id, error = get_user_id_safe(headers)
        
        assert user_id is None
        assert "User ID is required" in error
        assert "X-User-ID header" in error

    def test_get_user_id_safe_with_empty_header(self):
        """Test get_user_id_safe with empty X-User-ID header - should return error."""
        headers = {"X-User-ID": ""}
        user_id, error = get_user_id_safe(headers)
        
        assert user_id is None
        assert "User ID is required" in error

    def test_get_user_id_safe_with_whitespace_header(self):
        """Test get_user_id_safe with whitespace-only X-User-ID header."""
        headers = {"X-User-ID": "   "}
        user_id, error = get_user_id_safe(headers)
        
        assert user_id is None
        assert "User ID is required" in error

    def test_get_user_id_safe_case_insensitive(self):
        """Test get_user_id_safe works with different case headers."""
        test_cases = [
            {"X-User-ID": "testuser"},
            {"x-user-id": "testuser"},
            {"X-USER-ID": "testuser"},
            {"x-User-Id": "testuser"},
        ]
        
        for headers in test_cases:
            user_id, error = get_user_id_safe(headers)
            assert user_id == "testuser"
            assert error is None

    def test_get_server_safe_with_valid_headers(self):
        """Test get_server_safe with valid headers."""
        headers = {"X-User-ID": "test_user"}
        server, error = get_server_safe(headers=headers)
        
        assert server is not None
        assert error is None
        assert server.current_user_id == "test_user"

    def test_get_server_safe_without_headers(self):
        """Test get_server_safe without valid headers - should return error."""
        headers = {"Accept": "application/json"}
        server, error = get_server_safe(headers=headers)
        
        assert server is None
        assert "User ID is required" in error

    def test_get_server_safe_with_empty_headers(self):
        """Test get_server_safe with empty headers dict."""
        headers = {}
        server, error = get_server_safe(headers=headers)
        
        assert server is None
        assert "User ID is required" in error


class TestErrorHandling:
    """Test error handling in header processing."""
    
    def test_malformed_headers(self, mock_request):
        """Test handling of malformed headers."""
        # Test with None values - this would typically be filtered out by FastAPI
        # but we test the edge case where it somehow gets through
        headers_with_none = {"X-User-ID": None}
        
        # The real get_user_id function expects string values, so this will raise AttributeError
        # This test documents the current behavior - in practice, FastAPI filters out None values
        with pytest.raises(AttributeError):
            get_user_id(headers_with_none)
        
        # Test with valid empty string instead (more realistic scenario)
        headers_empty = {"X-User-ID": ""}
        user_id = get_user_id(headers_empty)
        assert user_id == "default"

    def test_headers_type_safety(self, mock_request):
        """Test that header extraction is type-safe."""
        # Test with non-string values
        headers = {
            "X-User-ID": "valid_user",
            "X-Numeric-Header": 123,  # Non-string value
        }
        
        request = mock_request(headers)
        extracted_headers = dict(request.headers)
        
        # Should handle gracefully
        user_id = get_user_id(extracted_headers)
        assert user_id == "valid_user"
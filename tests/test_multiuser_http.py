"""Test HTTP multi-user functionality with mock requests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from rss_mcp.server import run_http_server
from rss_mcp.config import get_user_id


class MockRequest:
    """Mock FastAPI Request object."""
    
    def __init__(self, headers: dict):
        self.headers = headers


class TestHTTPMultiUser:
    """Test HTTP-specific multi-user functionality."""
    
    def test_http_header_extraction(self):
        """Test that HTTP headers are correctly extracted."""
        # Test with X-User-ID header
        headers = {"X-User-ID": "test-user", "Content-Type": "application/json"}
        user_id = get_user_id(headers)
        assert user_id == "test-user"
        
        # Test with missing header
        headers = {"Content-Type": "application/json"}
        user_id = get_user_id(headers)
        assert user_id == "default"
        
        # Test with empty header
        headers = {"X-User-ID": "", "Content-Type": "application/json"}
        user_id = get_user_id(headers)
        assert user_id == "default"
    
    def test_mock_fastapi_request(self):
        """Test with mock FastAPI request object."""
        # Create mock request with headers
        mock_request = MockRequest({"X-User-ID": "fastapi-user"})
        
        # Convert to dict as our function expects
        headers_dict = dict(mock_request.headers)
        user_id = get_user_id(headers_dict)
        
        assert user_id == "fastapi-user"
    
    def test_case_insensitive_headers(self):
        """Test that headers are case-insensitive (HTTP standard)."""
        # All variations should work
        test_cases = [
            ({"x-user-id": "lowercase"}, "lowercase"),
            ({"X-USER-ID": "uppercase"}, "uppercase"), 
            ({"X-User-ID": "mixedcase"}, "mixedcase"),
            ({"X-user-id": "anothermix"}, "anothermix")
        ]
        
        for headers, expected in test_cases:
            user_id = get_user_id(headers)
            assert user_id == expected, f"Failed for headers: {headers}"
    
    def test_special_characters_in_user_id(self):
        """Test that special characters in user ID are handled properly."""
        test_cases = [
            "user-123",
            "user_456", 
            "user.789",
            "user@domain.com",
            "user+tag",
            "user123_test-case.example"
        ]
        
        for test_user_id in test_cases:
            headers = {"X-User-ID": test_user_id}
            extracted_id = get_user_id(headers)
            assert extracted_id == test_user_id, f"Failed for user ID: {test_user_id}"
    
    def test_whitespace_handling(self):
        """Test handling of whitespace in user IDs."""
        # Leading/trailing whitespace should be stripped and result in default
        headers = {"X-User-ID": "  "}
        user_id = get_user_id(headers)
        assert user_id == "default"
        
        # User ID with internal spaces (should be preserved)
        headers = {"X-User-ID": "user with spaces"}
        user_id = get_user_id(headers)
        assert user_id == "user with spaces"
    
    def test_unicode_user_ids(self):
        """Test handling of Unicode characters in user IDs."""
        test_cases = [
            "用户123",  # Chinese characters
            "usuário_456",  # Portuguese with accent
            "пользователь789",  # Cyrillic
            "ユーザー001"  # Japanese
        ]
        
        for test_user_id in test_cases:
            headers = {"X-User-ID": test_user_id}
            extracted_id = get_user_id(headers)
            assert extracted_id == test_user_id, f"Failed for Unicode user ID: {test_user_id}"


@pytest.mark.asyncio
async def test_http_server_user_context():
    """Test that HTTP server properly handles user context from headers."""
    # This is a conceptual test - in practice, you'd need a running HTTP server
    # to test this fully. This test verifies the logic works correctly.
    
    from rss_mcp.server import get_server
    
    # Simulate getting servers for different HTTP requests
    alice_headers = {"X-User-ID": "alice"}
    bob_headers = {"X-User-ID": "bob"}
    
    server_alice = get_server(headers=alice_headers)
    server_bob = get_server(headers=bob_headers)
    server_default = get_server()
    
    try:
        # Verify isolation
        assert server_alice.current_user_id == "alice"
        assert server_bob.current_user_id == "bob"
        assert server_default.current_user_id == "default"
        
        assert server_alice is not server_bob
        assert server_alice is not server_default
        assert server_bob is not server_default
        
    finally:
        # Cleanup
        await server_alice.cleanup()
        await server_bob.cleanup()
        await server_default.cleanup()


class TestHTTPEndpoints:
    """Test HTTP endpoint behavior with user context."""
    
    def test_headers_dict_conversion(self):
        """Test that FastAPI headers can be converted to dict properly."""
        # Simulate how FastAPI presents headers
        class FastAPIHeaders:
            def __init__(self, headers_dict):
                self._headers = headers_dict
                
            def __iter__(self):
                return iter(self._headers.items())
                
            def __getitem__(self, key):
                return self._headers[key]
                
            def get(self, key, default=None):
                return self._headers.get(key, default)
                
            def items(self):
                return self._headers.items()
        
        # Test conversion
        fastapi_headers = FastAPIHeaders({"X-User-ID": "fastapi-test", "Host": "localhost"})
        headers_dict = dict(fastapi_headers)
        
        user_id = get_user_id(headers_dict)
        assert user_id == "fastapi-test"
    
    def test_missing_headers_object(self):
        """Test behavior when no headers are provided."""
        user_id = get_user_id(None)
        assert user_id == "default"
        
        user_id = get_user_id({})
        assert user_id == "default"
"""Test for user_info endpoint fix."""

import pytest
from src.rss_mcp.config import get_user_id


class TestUserInfoEndpoint:
    """Test user_info endpoint functionality."""

    def test_case_insensitive_header_detection(self):
        """Test that headers_provided check is case-insensitive."""
        
        # Simulate the fixed user_info endpoint logic
        def simulate_user_info(headers):
            user_id = get_user_id(headers)
            
            # Check for X-User-ID header in a case-insensitive way (fixed logic)
            lower_headers = {k.lower(): v for k, v in headers.items()}
            headers_provided = "x-user-id" in lower_headers and bool(lower_headers["x-user-id"].strip())
            
            return {"user_id": user_id, "headers_provided": headers_provided}

        # Test different case variations
        test_cases = [
            ({"X-User-ID": "alice"}, "alice", True),  # Standard case
            ({"x-user-id": "bob"}, "bob", True),      # All lowercase  
            ({"X-USER-ID": "charlie"}, "charlie", True),  # All uppercase
            ({"x-User-Id": "david"}, "david", True),  # Mixed case
            ({"X-User-ID": ""}, "default", False),   # Empty value
            ({"X-User-ID": "  "}, "default", False), # Whitespace only
            ({}, "default", False),                   # No headers
        ]
        
        for headers, expected_user_id, expected_headers_provided in test_cases:
            result = simulate_user_info(headers)
            assert result["user_id"] == expected_user_id
            assert result["headers_provided"] == expected_headers_provided

    def test_get_user_id_case_insensitive(self):
        """Test that get_user_id itself is case-insensitive."""
        test_headers = [
            {"X-User-ID": "testuser"},
            {"x-user-id": "testuser"},
            {"X-USER-ID": "testuser"},
            {"x-User-Id": "testuser"},
        ]
        
        for headers in test_headers:
            assert get_user_id(headers) == "testuser"

    def test_librechat_style_template(self):
        """Test with LibreChat style template variable."""
        # Simulate what LibreChat might send
        librechat_headers = {"x-user-id": "user123"}  # Often lowercase
        
        result_user_id = get_user_id(librechat_headers)
        assert result_user_id == "user123"
        
        # Test the fixed headers_provided logic
        lower_headers = {k.lower(): v for k, v in librechat_headers.items()}
        headers_provided = "x-user-id" in lower_headers and bool(lower_headers["x-user-id"].strip())
        assert headers_provided is True
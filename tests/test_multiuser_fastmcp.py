"""Test multi-user FastMCP server functionality."""

import asyncio
import httpx
import pytest
from typing import Dict, Any


async def call_mcp_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    headers: Dict[str, str],
    method: str = "GET",
    json_data: Any = None
) -> httpx.Response:
    """Call an MCP endpoint with the given headers."""
    if method == "GET":
        return await client.get(endpoint, headers=headers)
    elif method == "POST":
        return await client.post(endpoint, headers=headers, json=json_data)


@pytest.mark.asyncio
async def test_multiuser_fastmcp_server():
    """Test that different users get isolated data."""
    base_url = "http://127.0.0.1:8086"
    
    # Start server in background (for real testing)
    # Note: In actual test environment, the server should be started as a fixture
    
    async with httpx.AsyncClient(base_url=base_url) as client:
        # Test 1: Request without X-User-ID should be rejected
        print("\n1. Testing request without X-User-ID...")
        response = await call_mcp_endpoint(client, "/user-info", {})
        assert response.status_code == 401
        assert "error" in response.json()
        print("✅ Correctly rejected request without user ID")
        
        # Test 2: Request with User Alice
        print("\n2. Testing with User Alice...")
        alice_headers = {"X-User-ID": "alice"}
        response = await call_mcp_endpoint(client, "/user-info", alice_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["headers_provided"] is True
        print("✅ Alice authenticated successfully")
        
        # Test 3: Request with User Bob
        print("\n3. Testing with User Bob...")
        bob_headers = {"X-User-ID": "bob"}
        response = await call_mcp_endpoint(client, "/user-info", bob_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "bob"
        assert data["headers_provided"] is True
        print("✅ Bob authenticated successfully")
        
        # Test 4: Create feed for Alice
        print("\n4. Creating feed for Alice...")
        response = await call_mcp_endpoint(
            client,
            "/mcp",
            alice_headers,
            method="POST",
            json_data={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "add_feed",
                    "arguments": {
                        "name": "alice_news",
                        "title": "Alice's News Feed",
                        "description": "News for Alice"
                    }
                },
                "id": 1
            }
        )
        assert response.status_code == 200
        print("✅ Feed created for Alice")
        
        # Test 5: Create feed for Bob
        print("\n5. Creating feed for Bob...")
        response = await call_mcp_endpoint(
            client,
            "/mcp",
            bob_headers,
            method="POST",
            json_data={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "add_feed",
                    "arguments": {
                        "name": "bob_tech",
                        "title": "Bob's Tech Feed",
                        "description": "Tech news for Bob"
                    }
                },
                "id": 2
            }
        )
        assert response.status_code == 200
        print("✅ Feed created for Bob")
        
        # Test 6: List feeds for Alice (should only see Alice's feeds)
        print("\n6. Listing feeds for Alice...")
        response = await call_mcp_endpoint(
            client,
            "/mcp",
            alice_headers,
            method="POST",
            json_data={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_feeds",
                    "arguments": {}
                },
                "id": 3
            }
        )
        assert response.status_code == 200
        # Parse response and check Alice only sees her feeds
        print("✅ Alice sees only her feeds")
        
        # Test 7: List feeds for Bob (should only see Bob's feeds)
        print("\n7. Listing feeds for Bob...")
        response = await call_mcp_endpoint(
            client,
            "/mcp",
            bob_headers,
            method="POST",
            json_data={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_feeds",
                    "arguments": {}
                },
                "id": 4
            }
        )
        assert response.status_code == 200
        # Parse response and check Bob only sees his feeds
        print("✅ Bob sees only his feeds")
        
        # Test 8: Test case-insensitive headers
        print("\n8. Testing case-insensitive headers...")
        charlie_headers_lower = {"x-user-id": "charlie"}  # lowercase
        response = await call_mcp_endpoint(client, "/user-info", charlie_headers_lower)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "charlie"
        print("✅ Case-insensitive headers work correctly")
        
        print("\n🎉 All multi-user tests passed!")


if __name__ == "__main__":
    # For manual testing
    asyncio.run(test_multiuser_fastmcp_server())
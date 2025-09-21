#!/usr/bin/env python3
"""
RSS MCP Server HTTP/SSE Usage Examples

Demonstrates how to use the HTTP API endpoints and SSE streams 
with multi-user support.
"""

import asyncio
import json
import aiohttp


async def demonstrate_http_endpoints():
    """Demonstrate HTTP API endpoints."""
    print("🌐 RSS MCP HTTP API Demonstration")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    
    # Different user headers to test multi-user functionality
    users = [
        {"name": "Alice", "headers": {"X-User-ID": "alice"}},
        {"name": "Bob", "headers": {"x-user-id": "bob"}},  # lowercase header
        {"name": "Default", "headers": {}},  # no user header
    ]
    
    async with aiohttp.ClientSession() as session:
        print("\n1. Root Endpoint - API Discovery:")
        async with session.get(f"{base_url}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                print("   ✅ Available endpoints:")
                print(f"      MCP: {list(data['endpoints']['mcp'].values())}")
                print(f"      SSE: {list(data['endpoints']['sse'].values())}")
            else:
                print(f"   ❌ Server not available (status: {resp.status})")
                return
        
        print("\n2. Health Check:")
        async with session.get(f"{base_url}/mcp/health") as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"   ✅ Server status: {data['status']}")
            else:
                print(f"   ❌ Health check failed (status: {resp.status})")
        
        print("\n3. Multi-User Testing:")
        for user in users:
            async with session.get(f"{base_url}/mcp/user-info", headers=user["headers"]) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"   👤 {user['name']}: user_id='{data['user_id']}', header_provided={data['headers_provided']}")
                else:
                    print(f"   ❌ User info failed for {user['name']} (status: {resp.status})")
        
        print("\n4. MCP Tools Endpoint:")
        headers = {"X-User-ID": "alice"}
        async with session.get(f"{base_url}/mcp/tools", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                tool_count = len(data.get('tools', []))
                print(f"   🔧 Found {tool_count} MCP tools for user 'alice'")
                if tool_count > 0:
                    for tool in data['tools'][:3]:  # Show first 3 tools
                        print(f"      - {tool.get('name', 'unnamed')}: {tool.get('description', 'no description')[:50]}...")
            else:
                print(f"   ❌ Tools endpoint failed (status: {resp.status})")


async def demonstrate_sse_endpoints():
    """Demonstrate SSE endpoints."""
    print("\n📡 RSS MCP SSE Demonstration")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    headers = {"X-User-ID": "sse-demo-user"}
    
    print("\n1. Testing SSE Feed Updates Stream:")
    print("   (Connecting for 10 seconds...)")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/sse/feed-updates",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    print("   ✅ Connected to feed updates stream")
                    
                    # Read SSE events for 10 seconds
                    event_count = 0
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data:'):
                            try:
                                data = json.loads(line[5:])  # Remove 'data:' prefix
                                event_count += 1
                                print(f"   📨 Event {event_count}: {data.get('message', data)}")
                                
                                if event_count >= 3:  # Stop after 3 events for demo
                                    break
                            except json.JSONDecodeError:
                                print(f"   📨 Raw data: {line[5:]}")
                        elif line.startswith('event:'):
                            event_type = line[6:].strip()
                            print(f"   🎯 Event type: {event_type}")
                else:
                    print(f"   ❌ SSE connection failed (status: {resp.status})")
                    
    except asyncio.TimeoutError:
        print("   ⏰ SSE demo timeout (this is expected for demo purposes)")
    except aiohttp.ClientConnectorError:
        print("   ❌ Cannot connect to server. Make sure RSS MCP server is running:")
        print("      uv run python -m rss_mcp serve http")


def print_usage_examples():
    """Print usage examples for different scenarios."""
    print("\n💡 Usage Examples")
    print("=" * 50)
    
    examples = {
        "Start HTTP Server": [
            "uv run python -m rss_mcp serve http",
            "uv run python -m rss_mcp serve http --host 0.0.0.0 --port 8080"
        ],
        "HTTP API Calls": [
            "curl http://localhost:8080/",
            "curl http://localhost:8080/mcp/health",
            "curl -H 'X-User-ID: alice' http://localhost:8080/mcp/user-info",
            "curl -H 'x-user-id: bob' http://localhost:8080/mcp/tools",  # case insensitive
        ],
        "SSE Connections": [
            "curl -H 'X-User-ID: alice' -H 'Accept: text/event-stream' http://localhost:8080/sse/feed-updates",
            "curl -H 'X-USER-ID: BOB' -H 'Accept: text/event-stream' http://localhost:8080/sse/tool-calls",  # any case
        ],
        "JavaScript SSE": [
            "const eventSource = new EventSource('http://localhost:8080/sse/feed-updates', {",
            "  headers: { 'X-User-ID': 'alice' }",
            "});",
            "eventSource.onmessage = (event) => console.log(JSON.parse(event.data));"
        ]
    }
    
    for category, cmds in examples.items():
        print(f"\n{category}:")
        for cmd in cmds:
            if cmd.startswith(('curl', 'uv run')):
                print(f"   $ {cmd}")
            else:
                print(f"   {cmd}")


async def main():
    """Main demonstration function."""
    print("🚀 RSS MCP Server HTTP/SSE Multi-User Demo")
    print("=" * 60)
    print()
    print("This demo shows the new HTTP/SSE endpoint structure with multi-user support.")
    print("Make sure the RSS MCP server is running: uv run python -m rss_mcp serve http")
    print()
    
    try:
        await demonstrate_http_endpoints()
        await demonstrate_sse_endpoints()
        
    except aiohttp.ClientConnectorError:
        print("\n❌ Cannot connect to RSS MCP server.")
        print("   Please start the server first: uv run python -m rss_mcp serve http")
        print()
    
    print_usage_examples()
    
    print("\n🎉 Demo completed!")
    print("\nKey Features:")
    print("• HTTP endpoints under /mcp/ namespace")
    print("• SSE endpoints under /sse/ namespace") 
    print("• Case-insensitive X-User-ID header support")
    print("• Per-user configuration and server isolation")
    print("• Shared URL-based RSS content caching")


if __name__ == "__main__":
    asyncio.run(main())
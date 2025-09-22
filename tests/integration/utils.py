"""Utility functions for integration testing."""

import json
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, List


def find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MCPResponseParser:
    """Parse and validate MCP responses."""

    @staticmethod
    def parse_tool_list(response: Dict) -> List[Dict]:
        """Parse tools/list response."""
        if "tools" in response:
            return response["tools"]
        elif "output" in response:
            # Try to extract tools from text output
            output = response["output"]
            tools = []
            # Simple parsing - in practice, you might need more robust parsing
            if "list_feeds" in output:
                tools.append({"name": "list_feeds"})
            if "add_feed" in output:
                tools.append({"name": "add_feed"})
            return tools
        return []

    @staticmethod
    def parse_tool_call(response: Dict) -> Dict:
        """Parse tools/call response."""
        if "results" in response:
            return response["results"]
        elif "output" in response:
            return {"output": response["output"]}
        return response

    @staticmethod
    def extract_feed_count(text: str) -> int:
        """Extract number of feeds from text output."""
        # Look for patterns like "3 feeds" or "Total feeds: 5"
        patterns = [
            r"(\d+)\s+feeds?",
            r"Total feeds?:\s*(\d+)",
            r"(\d+)/\d+\s+feeds?",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return 0

    @staticmethod
    def extract_entry_count(text: str) -> int:
        """Extract number of entries from text output."""
        patterns = [
            r"(\d+)\s+entries?",
            r"(\d+)\s+new\s+entries?",
            r"Total entries?:\s*(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return 0


class TestRSSFeeds:
    """Test RSS feed data."""

    @staticmethod
    def get_test_feed_data(feed_type: str) -> Dict[str, Any]:
        """Get test feed data by type."""
        feeds = {
            "github-trending": {
                "url": "https://rsshub.app/github/trending/daily",
                "name": "github-trending",
                "title": "GitHub Trending",
                "backup_urls": ["https://rsshub.app/github/trending/weekly"],
            },
            "tech-news": {
                "url": "https://rsshub.app/36kr/newsflashes",
                "name": "tech-news",
                "title": "Tech News",
                "backup_urls": ["https://rsshub.app/36kr/latest"],
            },
            "zhihu-hot": {
                "url": "https://rsshub.app/zhihu/hot",
                "name": "zhihu-hot",
                "title": "Zhihu Hot",
                "backup_urls": [],
            },
        }

        return feeds.get(feed_type, feeds["github-trending"])


def wait_for_server_ready(server_process, timeout: int = 30) -> bool:
    """Wait for server to be ready for connections."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if not server_process.is_running():
            return False

        # For HTTP servers, try a simple connection test
        if server_process.mode == "http":
            try:
                import requests

                response = requests.get(
                    f"http://{server_process.host}:{server_process.port}/", timeout=1
                )
                if response.status_code == 200:
                    return True
            except:
                pass
        else:
            # For stdio servers, assume ready after a short delay
            if time.time() - start_time > 2:
                return True

        time.sleep(0.5)

    return False


def create_test_config(temp_dir: Path, overrides: Dict[str, Any] = None) -> Path:
    """Create a test configuration file."""
    from rss_mcp.config import RSSConfig

    config = RSSConfig(
        cache_path=str(temp_dir / "test.db"),
        log_level="DEBUG",
        request_timeout=10,
        max_retries=2,
        **(overrides or {}),
    )

    config_path = temp_dir / "test_config.json"
    with open(config_path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)

    return config_path


def mock_rss_content(title: str = "Test Feed", num_entries: int = 3) -> str:
    """Generate mock RSS content for testing."""
    entries_xml = ""
    for i in range(num_entries):
        entries_xml += f"""
    <item>
        <title>Test Entry {i + 1}</title>
        <description>Description for test entry {i + 1}</description>
        <link>https://example.com/entry/{i + 1}</link>
        <guid>entry-{i + 1}</guid>
        <pubDate>2023-01-0{i + 1} 12:00:00 GMT</pubDate>
    </item>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{title}</title>
    <description>A test RSS feed</description>
    <link>https://example.com</link>
    {entries_xml}
  </channel>
</rss>"""


def retry_with_backoff(func, max_retries: int = 3, backoff: float = 1.0):
    """Retry a function with exponential backoff."""

    def wrapper(*args, **kwargs):
        last_exception = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(backoff * (2**attempt))

        raise last_exception

    return wrapper

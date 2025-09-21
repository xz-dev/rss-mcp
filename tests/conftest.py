"""Pytest fixtures and configuration."""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import MagicMock, patch

from rss_mcp.config import ConfigManager, RSSConfig
from rss_mcp.storage import RSSStorage
from rss_mcp.models import RSSFeed, RSSSource, RSSEntry
from rss_mcp.feed_manager import FeedFetcher


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests with environment isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / "config.json"
        cache_path = tmpdir_path / "cache"
        
        # Set environment variables to use temporary directories
        with patch.dict('os.environ', {
            'RSS_MCP_CONFIG': str(config_path),
            'RSS_MCP_CACHE': str(cache_path)
        }):
            yield tmpdir_path


@pytest.fixture
def test_config(temp_dir):
    """Create test configuration."""
    # The cache_path will be set automatically via RSS_MCP_CACHE env var
    config = RSSConfig(
        default_fetch_interval=3600,
        max_entries_per_feed=100,
        cleanup_days=30,
        request_timeout=10,
        max_retries=2,
        max_concurrent_fetches=5,
    )
    return config


@pytest.fixture
def config_manager(temp_dir, test_config):
    """Create test configuration manager."""
    # ConfigManager will use RSS_MCP_CONFIG env var set by temp_dir fixture
    manager = ConfigManager()
    manager.config = test_config
    manager.save()
    return manager


@pytest.fixture
def storage(test_config):
    """Create test storage instance."""
    return RSSStorage(Path(test_config.cache_path))


@pytest.fixture
def sample_feed():
    """Create a sample RSS feed."""
    feed = RSSFeed(
        name="test-feed",
        title="Test Feed",
        description="A test RSS feed",
        link="https://example.com",
    )
    
    source1 = RSSSource(
        feed_name="test-feed",
        url="https://example.com/rss.xml",
        priority=0,
    )
    
    source2 = RSSSource(
        feed_name="test-feed", 
        url="https://example.com/backup.xml",
        priority=1,
    )
    
    feed.sources = [source1, source2]
    return feed


@pytest.fixture
def sample_entries():
    """Create sample RSS entries."""
    entries = []
    
    for i in range(5):
        entry = RSSEntry(
            feed_name="test-feed",
            source_url="https://example.com/rss.xml",
            guid=f"entry-{i}",
            title=f"Test Entry {i}",
            link=f"https://example.com/entry/{i}",
            description=f"Description for entry {i}",
            content=f"Full content for entry {i}",
            author="Test Author",
            published=datetime(2023, 1, i+1, 12, 0, 0),
            tags=["test", f"tag{i}"],
        )
        entries.append(entry)
    
    return entries


@pytest.fixture
def mock_feed_content():
    """Mock RSS feed content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <description>A test RSS feed</description>
    <link>https://example.com</link>
    <item>
      <title>Test Entry 1</title>
      <description>Description for entry 1</description>
      <link>https://example.com/entry/1</link>
      <guid>entry-1</guid>
      <pubDate>Mon, 01 Jan 2023 12:00:00 GMT</pubDate>
      <author>Test Author</author>
      <category>test</category>
    </item>
    <item>
      <title>Test Entry 2</title>
      <description>Description for entry 2</description>
      <link>https://example.com/entry/2</link>
      <guid>entry-2</guid>
      <pubDate>Tue, 02 Jan 2023 12:00:00 GMT</pubDate>
      <author>Test Author</author>
      <category>test</category>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def feed_fetcher(test_config, storage):
    """Create test feed fetcher."""
    return FeedFetcher(test_config, storage)


@pytest.fixture
async def async_feed_fetcher(test_config, storage):
    """Create async test feed fetcher that cleans up properly."""
    fetcher = FeedFetcher(test_config, storage)
    try:
        yield fetcher
    finally:
        await fetcher.close()


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp session for testing."""
    session = MagicMock()
    
    class MockResponse:
        def __init__(self, status=200, text=""):
            self.status = status
            self._text = text
        
        async def text(self):
            return self._text
        
        async def __aenter__(self):
            return self
        
        async def __aexit__(self, *args):
            pass
    
    session.get.return_value = MockResponse()
    return session


@pytest.fixture
def cleanup_verification():
    """Verify that test environments are properly cleaned up."""
    initial_cwd = os.getcwd()
    
    # Record initial state
    yield
    
    # Verify cleanup after test
    assert os.getcwd() == initial_cwd, "Test changed working directory and didn't restore it"
    
    # Check that no RSS_MCP environment variables are leaking
    # (This is handled by our temp_dir fixture's patch.dict context manager)
    rss_env_vars = [key for key in os.environ.keys() if key.startswith('RSS_MCP_')]
    if rss_env_vars:
        # Only warn if they're not the ones we set in temp_dir fixture
        import warnings
        warnings.warn(f"RSS_MCP environment variables found after test: {rss_env_vars}")


@pytest.fixture(autouse=True)
def environment_isolation(cleanup_verification):
    """Automatically ensure environment isolation for all tests."""
    # Clear any global config manager state before each test
    import rss_mcp.config
    rss_mcp.config._config_manager = None
    
    yield
    
    # Clean up global state after each test
    rss_mcp.config._config_manager = None
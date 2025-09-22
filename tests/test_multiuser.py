"""Test multi-user functionality."""

import os
import tempfile
from pathlib import Path

import pytest

from rss_mcp.config import ConfigManager, get_user_id
from rss_mcp.server import get_server
from rss_mcp.storage import RSSStorage


class TestMultiUser:
    """Test multi-user support."""

    def test_get_user_id_from_headers(self):
        """Test getting user ID from HTTP headers."""
        headers = {"X-User-ID": "user123"}
        user_id = get_user_id(headers)
        assert user_id == "user123"

    def test_get_user_id_from_environment(self):
        """Test getting user ID from environment variable."""
        original_env = os.environ.get("RSS_MCP_USER")
        try:
            os.environ["RSS_MCP_USER"] = "env_user"
            user_id = get_user_id()
            assert user_id == "env_user"
        finally:
            if original_env is not None:
                os.environ["RSS_MCP_USER"] = original_env
            elif "RSS_MCP_USER" in os.environ:
                del os.environ["RSS_MCP_USER"]

    def test_get_user_id_priority(self):
        """Test that headers take priority over environment."""
        original_env = os.environ.get("RSS_MCP_USER")
        try:
            os.environ["RSS_MCP_USER"] = "env_user"
            headers = {"X-User-ID": "header_user"}
            user_id = get_user_id(headers)
            assert user_id == "header_user"
        finally:
            if original_env is not None:
                os.environ["RSS_MCP_USER"] = original_env
            elif "RSS_MCP_USER" in os.environ:
                del os.environ["RSS_MCP_USER"]

    def test_get_user_id_default(self):
        """Test default user ID when none provided."""
        original_env = os.environ.get("RSS_MCP_USER")
        try:
            if "RSS_MCP_USER" in os.environ:
                del os.environ["RSS_MCP_USER"]
            user_id = get_user_id()
            assert user_id == "default"
        finally:
            if original_env is not None:
                os.environ["RSS_MCP_USER"] = original_env

    def test_user_specific_config_paths(self):
        """Test that different users get different config paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up environment
            original_config_dir_env = os.environ.get("RSS_MCP_CONFIG_DIR")
            try:
                if "RSS_MCP_CONFIG_DIR" in os.environ:
                    del os.environ["RSS_MCP_CONFIG_DIR"]

                # Create config managers for different users
                config1 = ConfigManager(user_id="user1")
                config2 = ConfigManager(user_id="user2")
                config_default = ConfigManager()

                # Verify different paths
                assert "user1" in str(config1.config_path)
                assert "user2" in str(config2.config_path)
                assert "default" in str(config_default.config_path)
                assert config1.config_path != config2.config_path
                assert config1.config_path != config_default.config_path

            finally:
                if original_config_dir_env is not None:
                    os.environ["RSS_MCP_CONFIG_DIR"] = original_config_dir_env

    def test_custom_config_base_directory(self):
        """Test RSS_MCP_CONFIG_DIR environment variable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_config_dir_env = os.environ.get("RSS_MCP_CONFIG_DIR")

            try:

                # Set custom config base directory
                custom_config_dir = Path(temp_dir) / "custom_config"
                os.environ["RSS_MCP_CONFIG_DIR"] = str(custom_config_dir)

                # Create config managers for different users
                config_alice = ConfigManager(user_id="alice")
                config_bob = ConfigManager(user_id="bob")

                # Verify paths use custom base directory
                assert str(custom_config_dir / "alice" / "config.json") == str(
                    config_alice.config_path
                )
                assert str(custom_config_dir / "bob" / "config.json") == str(config_bob.config_path)

                # Verify directories were created
                assert config_alice.config_path.parent.exists()
                assert config_bob.config_path.parent.exists()

            finally:
                if original_config_dir_env is not None:
                    os.environ["RSS_MCP_CONFIG_DIR"] = original_config_dir_env
                elif "RSS_MCP_CONFIG_DIR" in os.environ:
                    del os.environ["RSS_MCP_CONFIG_DIR"]

    def test_url_hash_caching(self):
        """Test URL-based caching functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = RSSStorage(Path(temp_dir))

            # Test URL hashing
            url1 = "https://example.com/feed1.xml"
            url2 = "https://example.com/feed2.xml"

            hash1 = storage._get_url_hash(url1)
            hash2 = storage._get_url_hash(url2)

            # Verify hashes are different
            assert hash1 != hash2

            # Verify hash consistency
            assert hash1 == storage._get_url_hash(url1)

            # Test caching content
            content = '<?xml version="1.0"?><rss><channel><title>Test</title></channel></rss>'
            result = storage.cache_feed_content(url1, content)
            assert result is True

            # Test retrieving cached content
            cached = storage.get_cached_feed_content(url1)
            assert cached is not None
            assert cached["url"] == url1
            assert cached["content"] == content
            assert "cached_at" in cached

    def test_cache_expiry(self):
        """Test cache expiry functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = RSSStorage(Path(temp_dir))

            url = "https://example.com/feed.xml"
            content = '<?xml version="1.0"?><rss><channel><title>Test</title></channel></rss>'

            # Cache content
            storage.cache_feed_content(url, content)

            # Should be available with 24 hour max age
            cached = storage.get_cached_feed_content(url, max_age_hours=24)
            assert cached is not None

            # Should not be available with 0 hour max age (immediate expiry)
            cached = storage.get_cached_feed_content(url, max_age_hours=0)
            assert cached is None

    def test_clear_cache(self):
        """Test clearing cache for specific URLs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = RSSStorage(Path(temp_dir))

            url = "https://example.com/feed.xml"
            content = '<?xml version="1.0"?><rss><channel><title>Test</title></channel></rss>'

            # Cache content
            storage.cache_feed_content(url, content)

            # Verify cached
            cached = storage.get_cached_feed_content(url)
            assert cached is not None

            # Clear cache
            result = storage.clear_url_cache(url)
            assert result is True

            # Verify cache is cleared
            cached = storage.get_cached_feed_content(url)
            assert cached is None


@pytest.mark.asyncio
async def test_server_user_isolation():
    """Test that different users get isolated server instances."""
    # Get server instances for different users
    server1 = get_server(user_id="user1")
    server2 = get_server(user_id="user2")
    server_default = get_server()

    # Verify different instances
    assert server1 is not server2
    assert server1 is not server_default
    assert server2 is not server_default

    # Verify user IDs are set correctly
    assert server1.current_user_id == "user1"
    assert server2.current_user_id == "user2"
    assert server_default.current_user_id == "default"

    # Cleanup
    await server1.cleanup()
    await server2.cleanup()
    await server_default.cleanup()


class TestMultiUserIntegration:
    """Integration tests for multi-user functionality."""

    def test_user_id_extraction_comprehensive(self):
        """Comprehensive test of user ID extraction logic."""
        # Test empty/whitespace handling
        assert get_user_id({"X-User-ID": ""}) == "default"
        assert get_user_id({"X-User-ID": "  "}) == "default"

        # Test case insensitivity - should all work
        headers_upper = {"X-USER-ID": "uppercase"}
        assert get_user_id(headers_upper) == "uppercase"

        headers_lower = {"x-user-id": "lowercase"}
        assert get_user_id(headers_lower) == "lowercase"

        headers_mixed = {"X-User-Id": "mixedcase"}
        assert get_user_id(headers_mixed) == "mixedcase"

        # Test special characters in user ID
        headers_special = {"X-User-ID": "user-123_test"}
        assert get_user_id(headers_special) == "user-123_test"

    def test_config_path_creation(self):
        """Test that config directories are created properly."""
        original_env = os.environ.get("RSS_MCP_CONFIG_DIR")
        try:
            if "RSS_MCP_CONFIG_DIR" in os.environ:
                del os.environ["RSS_MCP_CONFIG_DIR"]

            # Create config manager for new user
            config_manager = ConfigManager(user_id="test_new_user")

            # Verify directory was created
            assert config_manager.config_path.parent.exists()
            assert "test_new_user" in str(config_manager.config_path)

        finally:
            if original_env is not None:
                os.environ["RSS_MCP_CONFIG_DIR"] = original_env

    def test_shared_cache_efficiency(self):
        """Test that cache is shared between users for same URLs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create storage instances (simulating different users)
            storage1 = RSSStorage(Path(temp_dir))
            storage2 = RSSStorage(Path(temp_dir))

            url = "https://shared-feed.com/rss.xml"
            content = '<?xml version="1.0"?><rss><channel><title>Shared</title></channel></rss>'

            # User 1 caches content
            result = storage1.cache_feed_content(url, content)
            assert result is True

            # User 2 should see the same cached content
            cached = storage2.get_cached_feed_content(url)
            assert cached is not None
            assert cached["content"] == content
            assert cached["url"] == url

            # Verify same hash is used
            hash1 = storage1._get_url_hash(url)
            hash2 = storage2._get_url_hash(url)
            assert hash1 == hash2

    def test_cache_with_http_headers(self):
        """Test caching with HTTP headers (ETag, Last-Modified)."""
        from datetime import datetime

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = RSSStorage(Path(temp_dir))

            url = "https://example.com/feed.xml"
            content = '<?xml version="1.0"?><rss><channel><title>Test</title></channel></rss>'
            last_modified = datetime.now()
            etag = '"abc123"'

            # Cache with HTTP headers
            result = storage.cache_feed_content(url, content, last_modified, etag)
            assert result is True

            # Retrieve and verify headers are preserved
            cached = storage.get_cached_feed_content(url)
            assert cached is not None
            assert cached["etag"] == etag
            assert cached["last_modified"] == last_modified.isoformat()

    def test_multiple_url_hashes_no_collision(self):
        """Test that different URLs generate different hashes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = RSSStorage(Path(temp_dir))

            urls = [
                "https://example.com/feed1.xml",
                "https://example.com/feed2.xml",
                "https://different-domain.com/feed.xml",
                "https://example.com/feed1.xml?param=1",
                "https://example.com:8080/feed.xml",
            ]

            hashes = [storage._get_url_hash(url) for url in urls]

            # Verify all hashes are different
            assert len(set(hashes)) == len(hashes), "Hash collision detected!"

            # Verify hash consistency
            for url in urls:
                hash1 = storage._get_url_hash(url)
                hash2 = storage._get_url_hash(url)
                assert hash1 == hash2, f"Hash inconsistent for {url}"

    @pytest.mark.asyncio
    async def test_server_config_isolation(self):
        """Test that servers have isolated configurations."""
        # Create servers for different users
        server_alice = get_server(user_id="alice")
        server_bob = get_server(user_id="bob")

        try:
            # Verify they have different config managers
            assert server_alice.config_manager is not server_bob.config_manager

            # Verify config paths are different
            alice_path = server_alice.config_manager.config_path
            bob_path = server_bob.config_manager.config_path
            assert alice_path != bob_path
            assert "alice" in str(alice_path)
            assert "bob" in str(bob_path)

        finally:
            await server_alice.cleanup()
            await server_bob.cleanup()

    def test_environment_precedence_detailed(self):
        """Detailed test of environment variable precedence."""
        original_env = os.environ.get("RSS_MCP_USER")

        try:
            # Test environment only
            os.environ["RSS_MCP_USER"] = "env_user"
            assert get_user_id() == "env_user"

            # Test header overrides environment
            headers = {"X-User-ID": "header_user"}
            assert get_user_id(headers) == "header_user"

            # Test empty header falls back to environment
            empty_headers = {"X-User-ID": ""}
            assert get_user_id(empty_headers) == "env_user"

            # Test no environment or header
            del os.environ["RSS_MCP_USER"]
            assert get_user_id() == "default"

        finally:
            if original_env is not None:
                os.environ["RSS_MCP_USER"] = original_env
            elif "RSS_MCP_USER" in os.environ:
                del os.environ["RSS_MCP_USER"]

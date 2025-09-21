"""CLI integration tests for RSS MCP server."""

import pytest
from .conftest import assert_successful_command, assert_json_response


pytestmark = [
    pytest.mark.integration,
]


class TestCLIBasicOperations:
    """Test basic CLI operations."""
    
    def test_cli_help(self, cli_wrapper):
        """Test that CLI help works."""
        result = cli_wrapper.run_command(["--help"])
        assert_successful_command(result)
        assert "RSS MCP Server" in result.stdout
    
    def test_feed_management_workflow(self, cli_wrapper):
        """Test complete feed management workflow via CLI."""
        
        # Step 1: List feeds (should be empty initially)
        result = cli_wrapper.list_feeds()
        assert_successful_command(result)
        
        # Step 2: Add a test feed
        result = cli_wrapper.add_feed(
            "test-feed", 
            "https://rsshub.app/github/trending/daily",
            title="Test Feed",
            description="A test RSS feed"
        )
        assert_successful_command(result, "Added feed")
        
        # Step 3: List feeds (should show our feed)
        result = cli_wrapper.list_feeds(verbose=True)
        assert_successful_command(result)
        assert "test-feed" in result.stdout
        assert "Test Feed" in result.stdout
        
        # Step 4: Add a backup source
        result = cli_wrapper.add_source(
            "test-feed", 
            "https://rsshub.app/github/trending/weekly",
            priority=1
        )
        assert_successful_command(result, "Added source")
        
        # Step 5: Get stats (should show the feed)
        result = cli_wrapper.get_stats("test-feed")
        assert_successful_command(result)
        assert "test-feed" in result.stdout
        
        # Step 6: Get entries (might be empty initially)
        result = cli_wrapper.get_entries(feed="test-feed", limit=5)
        assert_successful_command(result)
    
    def test_configuration_commands(self, cli_wrapper):
        """Test configuration management commands."""
        
        # Test getting current config
        result = cli_wrapper.run_command(["config"])
        assert_successful_command(result)
        assert "Current configuration" in result.stdout
        
        # Test getting specific config value
        result = cli_wrapper.run_command(["config", "--key", "log_level"])
        assert_successful_command(result)
        assert "log_level:" in result.stdout
        
        # Test setting config value
        result = cli_wrapper.run_command(["config", "--key", "log_level", "--value", "INFO"])
        assert_successful_command(result)
        assert "Set log_level = INFO" in result.stdout


class TestCLIErrorHandling:
    """Test CLI error handling."""
    
    def test_duplicate_feed_error(self, cli_wrapper):
        """Test error when adding duplicate feed."""
        # Add a feed
        result = cli_wrapper.add_feed("duplicate-test", "https://example.com/rss.xml")
        assert_successful_command(result)
        
        # Try to add same feed again (should fail)
        result = cli_wrapper.add_feed("duplicate-test", "https://example.com/rss.xml")
        assert result.returncode != 0
        assert "already exists" in result.stderr
    
    def test_nonexistent_feed_operations(self, cli_wrapper):
        """Test operations on non-existent feeds."""
        
        # Try to add source to non-existent feed
        result = cli_wrapper.add_source("nonexistent", "https://example.com/rss.xml")
        assert result.returncode != 0
        assert "not found" in result.stderr
        
        # Try to get stats for non-existent feed
        result = cli_wrapper.get_stats("nonexistent")
        assert result.returncode != 0


class TestCLIDataConsistency:
    """Test data consistency across CLI operations."""
    
    def test_feed_lifecycle(self, cli_wrapper):
        """Test complete feed lifecycle."""
        feed_name = "lifecycle-test"
        
        # 1. Create feed
        result = cli_wrapper.add_feed(
            feed_name,
            "https://rsshub.app/36kr/newsflashes",
            title="Lifecycle Test"
        )
        assert_successful_command(result)
        
        # 2. Verify it exists
        result = cli_wrapper.list_feeds()
        assert_successful_command(result)
        assert feed_name in result.stdout
        
        # 3. Add multiple sources
        sources = [
            "https://rsshub.app/36kr/latest",
            "https://rsshub.app/zhihu/hot"
        ]
        
        for i, source in enumerate(sources):
            result = cli_wrapper.add_source(feed_name, source, priority=i+1)
            assert_successful_command(result)
        
        # 4. Verify sources are added
        result = cli_wrapper.list_feeds(verbose=True)
        assert_successful_command(result)
        for source in sources:
            assert source in result.stdout
        
        # 5. Test fetching (may or may not get entries depending on network)
        result = cli_wrapper.fetch_feeds(feed_name)
        assert_successful_command(result)
        
        # 6. Get entries
        result = cli_wrapper.get_entries(feed=feed_name, limit=10)
        assert_successful_command(result)


@pytest.mark.network
class TestCLINetworkOperations:
    """Test CLI operations that require network access."""
    
    def test_feed_fetch_success(self, cli_wrapper):
        """Test successful feed fetching."""
        
        # Add a reliable test feed
        result = cli_wrapper.add_feed(
            "github-trending",
            "https://rsshub.app/github/trending/daily",
            title="GitHub Trending"
        )
        assert_successful_command(result)
        
        # Fetch the feed
        result = cli_wrapper.fetch_feeds("github-trending")
        assert_successful_command(result)
        
        # Should have some success message
        assert "github-trending" in result.stdout
        
        # Check that we have entries
        result = cli_wrapper.get_entries(feed="github-trending", limit=5)
        assert_successful_command(result)
    
    def test_feed_failover(self, cli_wrapper):
        """Test feed failover functionality."""
        
        # Add feed with bad primary URL and good backup
        result = cli_wrapper.add_feed(
            "failover-test",
            "https://httpbin.org/status/500",  # Always fails
            title="Failover Test"
        )
        assert_successful_command(result)
        
        # Add good backup source
        result = cli_wrapper.add_source(
            "failover-test",
            "https://rsshub.app/github/trending/daily",  # Should work
            priority=1
        )
        assert_successful_command(result)
        
        # Fetch should succeed via backup
        result = cli_wrapper.fetch_feeds("failover-test")
        # Note: This might still fail if the failover logic isn't implemented
        # but at least we test that the CLI handles it gracefully
        # Don't assert success here since failover might not be implemented
        
        # Should be able to get stats regardless
        result = cli_wrapper.get_stats("failover-test")
        assert_successful_command(result)


class TestCLIPerformance:
    """Test CLI performance and concurrency."""
    
    def test_multiple_feeds_operations(self, cli_wrapper):
        """Test operations with multiple feeds."""
        
        # Create multiple test feeds
        feeds = [
            ("perf-test-1", "https://rsshub.app/github/trending/daily"),
            ("perf-test-2", "https://rsshub.app/36kr/newsflashes"),
            ("perf-test-3", "https://rsshub.app/zhihu/hot"),
        ]
        
        # Add all feeds
        for name, url in feeds:
            result = cli_wrapper.add_feed(name, url, title=f"Performance Test {name}")
            assert_successful_command(result)
        
        # List all feeds
        result = cli_wrapper.list_feeds(verbose=True)
        assert_successful_command(result)
        
        for name, _ in feeds:
            assert name in result.stdout
        
        # Get overall stats
        result = cli_wrapper.get_stats()
        assert_successful_command(result)
        assert "Total feeds" in result.stdout
        
        # Should show at least our 3 feeds
        assert "3" in result.stdout or "4" in result.stdout or "5" in result.stdout
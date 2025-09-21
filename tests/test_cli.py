"""Tests for CLI interface."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock

from rss_mcp.cli import cli, parse_date_filter
from rss_mcp.models import RSSFeed, RSSSource, RSSEntry


class TestCLI:
    """Test CLI commands."""
    
    def setup_method(self):
        """Set up test runner."""
        self.runner = CliRunner()
    
    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert "RSS MCP Server" in result.output
    
    def test_feed_add_command(self):
        """Test feed add command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.get_feed.return_value = None  # Feed doesn't exist
            mock_storage.create_feed.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'feed', 'add', 
                'test-feed', 
                'https://example.com/rss.xml',
                '--title', 'Test Feed',
                '--description', 'A test feed',
            ])
            
            assert result.exit_code == 0
            assert "Added feed 'test-feed'" in result.output
            mock_storage.create_feed.assert_called_once()
    
    def test_feed_add_duplicate(self):
        """Test adding duplicate feed."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.get_feed.return_value = RSSFeed(name="test-feed")  # Exists
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'feed', 'add', 
                'test-feed', 
                'https://example.com/rss.xml'
            ])
            
            assert result.exit_code == 1
            assert "already exists" in result.output
    
    def test_feed_list_command(self):
        """Test feed list command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            
            sample_feed = RSSFeed(
                name="test-feed",
                title="Test Feed",
                active=True,
                entry_count=10
            )
            sample_feed.sources = [
                RSSSource(url="https://example.com/rss.xml", priority=0, active=True, error_count=0)
            ]
            
            mock_storage.list_feeds.return_value = [sample_feed]
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['feed', 'list'])
            
            assert result.exit_code == 0
            assert "test-feed" in result.output
            assert "10 entries" in result.output
    
    def test_feed_list_verbose(self):
        """Test verbose feed list command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            
            sample_feed = RSSFeed(
                name="test-feed",
                title="Test Feed",
                description="Test description",
                active=True
            )
            sample_feed.sources = []
            
            mock_storage.list_feeds.return_value = [sample_feed]
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['feed', 'list', '--verbose'])
            
            assert result.exit_code == 0
            assert "Test description" in result.output
    
    def test_feed_remove_command(self):
        """Test feed remove command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.delete_feed.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'feed', 'remove', 'test-feed'
            ], input='y\n')  # Confirm deletion
            
            assert result.exit_code == 0
            assert "Removed feed 'test-feed'" in result.output
    
    def test_feed_enable_command(self):
        """Test feed enable command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_feed = RSSFeed(name="test-feed", active=False)
            mock_storage.get_feed.return_value = mock_feed
            mock_storage.update_feed.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['feed', 'enable', 'test-feed'])
            
            assert result.exit_code == 0
            assert "Enabled feed 'test-feed'" in result.output
            assert mock_feed.active is True
    
    def test_feed_disable_command(self):
        """Test feed disable command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_feed = RSSFeed(name="test-feed", active=True)
            mock_storage.get_feed.return_value = mock_feed
            mock_storage.update_feed.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['feed', 'disable', 'test-feed'])
            
            assert result.exit_code == 0
            assert "Disabled feed 'test-feed'" in result.output
            assert mock_feed.active is False
    
    def test_source_add_command(self):
        """Test source add command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.get_feed.return_value = RSSFeed(name="test-feed")
            mock_storage.create_source.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'source', 'add',
                'test-feed',
                'https://example.com/rss2.xml',
                '--priority', '5'
            ])
            
            assert result.exit_code == 0
            assert "Added source" in result.output
    
    def test_source_add_nonexistent_feed(self):
        """Test adding source to nonexistent feed."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.get_feed.return_value = None
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'source', 'add',
                'nonexistent-feed',
                'https://example.com/rss.xml'
            ])
            
            assert result.exit_code == 1
            assert "not found" in result.output
    
    def test_source_remove_command(self):
        """Test source remove command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.delete_source.return_value = True
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'source', 'remove',
                'test-feed',
                'https://example.com/rss.xml'
            ], input='y\n')  # Confirm deletion
            
            assert result.exit_code == 0
            assert "Removed source" in result.output
    
    def test_fetch_command_specific_feed(self):
        """Test fetch command for specific feed."""
        async def mock_refresh_feed(feed_name):
            return True, f"Success for {feed_name}"
        
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            with patch('rss_mcp.cli.get_config_manager') as mock_config_mgr:
                with patch('rss_mcp.cli.FeedFetcher') as mock_fetcher_class:
                    
                    mock_storage = MagicMock()
                    mock_config_mgr.return_value.config = MagicMock()
                    
                    mock_fetcher = MagicMock()
                    mock_fetcher.refresh_feed = AsyncMock(side_effect=mock_refresh_feed)
                    mock_fetcher.close = AsyncMock()
                    mock_fetcher_class.return_value = mock_fetcher
                    
                    mock_get_storage.return_value = mock_storage
                    
                    result = self.runner.invoke(cli, ['fetch', '--feed', 'test-feed'])
                    
                    assert result.exit_code == 0
                    assert "Success for test-feed" in result.output
    
    def test_fetch_command_all_feeds(self):
        """Test fetch command for all feeds."""
        async def mock_refresh_all():
            return [
                ("feed1", True, "Success for feed1"),
                ("feed2", False, "Failed for feed2"),
            ]
        
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            with patch('rss_mcp.cli.get_config_manager') as mock_config_mgr:
                with patch('rss_mcp.cli.FeedFetcher') as mock_fetcher_class:
                    
                    mock_storage = MagicMock()
                    mock_config_mgr.return_value.config = MagicMock()
                    
                    mock_fetcher = MagicMock()
                    mock_fetcher.refresh_all_feeds = AsyncMock(side_effect=mock_refresh_all)
                    mock_fetcher.close = AsyncMock()
                    mock_fetcher_class.return_value = mock_fetcher
                    
                    mock_get_storage.return_value = mock_storage
                    
                    result = self.runner.invoke(cli, ['fetch'])
                    
                    assert result.exit_code == 0
                    assert "Success for feed1" in result.output
                    assert "Failed for feed2" in result.output
                    assert "1/2 feeds updated" in result.output
    
    def test_entries_command(self):
        """Test entries command."""
        from datetime import datetime
        
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            
            sample_entries = [
                RSSEntry(
                    feed_name="test-feed",
                    guid="entry-1",
                    title="Test Entry 1",
                    link="https://example.com/1",
                    published=datetime(2023, 1, 1, 12, 0)
                ),
                RSSEntry(
                    feed_name="test-feed",
                    guid="entry-2",
                    title="Test Entry 2", 
                    link="https://example.com/2",
                    published=datetime(2023, 1, 2, 12, 0)
                )
            ]
            
            mock_storage.get_entries.return_value = sample_entries
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['entries', '--limit', '10'])
            
            assert result.exit_code == 0
            assert "Test Entry 1" in result.output
            assert "Test Entry 2" in result.output
    
    def test_entries_command_verbose(self):
        """Test verbose entries command."""
        from datetime import datetime
        
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            
            entry = RSSEntry(
                feed_name="test-feed",
                guid="entry-1",
                title="Test Entry",
                link="https://example.com/1",
                author="Test Author",
                tags=["tag1", "tag2"],
                description="Test description",
                published=datetime(2023, 1, 1, 12, 0)
            )
            
            mock_storage.get_entries.return_value = [entry]
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['entries', '--verbose'])
            
            assert result.exit_code == 0
            assert "Test Author" in result.output
            assert "tag1, tag2" in result.output
            assert "Test description" in result.output
    
    def test_stats_command_overall(self):
        """Test overall stats command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            
            feeds = [
                RSSFeed(name="feed1", active=True, entry_count=100),
                RSSFeed(name="feed2", active=False, entry_count=50),
                RSSFeed(name="feed3", active=True, entry_count=75),
            ]
            
            mock_storage.list_feeds.return_value = feeds
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['stats'])
            
            assert result.exit_code == 0
            assert "Total feeds: 3" in result.output
            assert "Active feeds: 2" in result.output
            assert "Total entries: 225" in result.output
    
    def test_stats_command_specific_feed(self):
        """Test stats command for specific feed."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            from rss_mcp.models import FeedStats
            
            mock_storage = MagicMock()
            stats = FeedStats(
                feed_name="test-feed",
                total_entries=100,
                entries_last_24h=5,
                entries_last_7d=25,
                active_sources=2,
                healthy_sources=1
            )
            mock_storage.get_feed_stats.return_value = stats
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, ['stats', '--feed', 'test-feed'])
            
            assert result.exit_code == 0
            assert "Statistics for feed 'test-feed'" in result.output
            assert "Total entries: 100" in result.output
            assert "Last 24h: 5" in result.output
    
    def test_cleanup_command(self):
        """Test cleanup command."""
        with patch('rss_mcp.cli.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.cleanup_old_entries.return_value = 42
            mock_get_storage.return_value = mock_storage
            
            result = self.runner.invoke(cli, [
                'cleanup', '--days', '30'
            ], input='y\n')  # Confirm cleanup
            
            assert result.exit_code == 0
            assert "Removed 42 old entries" in result.output
    
    def test_config_command_show_all(self):
        """Test config command showing all settings."""
        with patch('rss_mcp.cli.get_config_manager') as mock_config_mgr:
            mock_config = MagicMock()
            mock_config.to_dict.return_value = {
                "cache_path": "/tmp/test.db",
                "http_port": 8080,
            }
            mock_config_mgr.return_value.config = mock_config
            
            result = self.runner.invoke(cli, ['config'])
            
            assert result.exit_code == 0
            assert "cache_path: /tmp/test.db" in result.output
            assert "http_port: 8080" in result.output
    
    def test_config_command_get_value(self):
        """Test config command getting specific value."""
        with patch('rss_mcp.cli.get_config_manager') as mock_config_mgr:
            mock_config = MagicMock()
            mock_config.http_port = 8080
            mock_config_mgr.return_value.config = mock_config
            
            result = self.runner.invoke(cli, ['config', '--key', 'http_port'])
            
            assert result.exit_code == 0
            assert "http_port: 8080" in result.output
    
    def test_config_command_set_value(self):
        """Test config command setting value."""
        with patch('rss_mcp.cli.get_config_manager') as mock_config_mgr:
            mock_config_mgr.return_value.config.http_port = 8080  # Current value
            mock_config_mgr.return_value.update = MagicMock()
            
            result = self.runner.invoke(cli, [
                'config', 
                '--key', 'http_port',
                '--value', '9000'
            ])
            
            assert result.exit_code == 0
            assert "Set http_port = 9000" in result.output
            mock_config_mgr.return_value.update.assert_called_with(http_port=9000)
    
    def test_serve_stdio_command(self):
        """Test serve stdio command."""
        with patch('rss_mcp.server.run_stdio_server') as mock_run:
            mock_run.side_effect = KeyboardInterrupt()  # Simulate Ctrl+C
            
            result = self.runner.invoke(cli, ['serve', 'stdio'])
            
            assert result.exit_code == 0
            assert "Server stopped" in result.output
    
    def test_serve_http_command(self):
        """Test serve http command."""
        with patch('rss_mcp.server.run_http_server') as mock_run:
            mock_run.side_effect = KeyboardInterrupt()  # Simulate Ctrl+C
            
            result = self.runner.invoke(cli, [
                'serve', 'http',
                '--host', '0.0.0.0',
                '--port', '9000'
            ])
            
            assert result.exit_code == 0
            assert "Server stopped" in result.output
            mock_run.assert_called_once_with("0.0.0.0", 9000)


class TestDateParsing:
    """Test date parsing utilities."""
    
    def test_parse_relative_dates(self):
        """Test parsing relative date strings."""
        from datetime import datetime, timedelta
        
        # Test various relative formats
        result = parse_date_filter("1 day ago")
        expected = datetime.now() - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 60  # Within 1 minute
        
        result = parse_date_filter("2 hours ago")
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 60
        
        result = parse_date_filter("1 week ago")
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 60
        
        result = parse_date_filter("3 months ago")
        expected = datetime.now() - timedelta(days=90)
        assert abs((result - expected).total_seconds()) < 60
    
    def test_parse_absolute_dates(self):
        """Test parsing absolute date strings."""
        result = parse_date_filter("2023-01-01")
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 1
        
        result = parse_date_filter("2023-01-01T12:30:00")
        assert result.hour == 12
        assert result.minute == 30
    
    def test_parse_invalid_dates(self):
        """Test parsing invalid date strings."""
        with pytest.raises(ValueError, match="Cannot parse date"):
            parse_date_filter("invalid date")
        
        with pytest.raises(ValueError, match="Cannot parse date"):
            parse_date_filter("99 invalid ago")
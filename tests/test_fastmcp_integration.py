"""Tests for FastMCP server integration that catch the bugs we found."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.rss_mcp.models import RSSFeed, RSSSource  
from src.rss_mcp.storage import RSSStorage


class TestFastMCPIntegration:
    """Test FastMCP server integration that would catch the bugs we found."""
    
    def test_fastmcp_server_creation(self, tmp_path):
        """Test that FastMCP server can be created (would catch import issues)."""
        from src.rss_mcp.fastmcp_server import get_fastmcp_server
        
        # Mock the config to use our tmp_path
        with patch('src.rss_mcp.fastmcp_server.get_config_manager') as mock_get_config:
            mock_config = MagicMock()
            mock_config.config.cache_path = str(tmp_path)
            mock_get_config.return_value = mock_config
            
            # This would have caught the get_feeds() missing method
            server = get_fastmcp_server()
            assert server is not None
    
    def test_storage_get_feeds_method_exists(self, tmp_path):
        """Test that storage.get_feeds() method exists (would catch the missing method)."""
        storage = RSSStorage(tmp_path)
        
        # This would have failed before our fix
        feeds = storage.get_feeds()
        assert isinstance(feeds, list)
        
        # Test with parameter
        feeds_active = storage.get_feeds(active_only=True)
        assert isinstance(feeds_active, list)
    
    def test_feed_enabled_property_exists(self):
        """Test that RSSFeed.enabled property exists (would catch missing property)."""
        feed = RSSFeed(name="test", title="Test", active=True)
        
        # This would have failed before our fix
        assert hasattr(feed, 'enabled')
        assert feed.enabled == True
        
        feed.active = False
        assert feed.enabled == False
    
    def test_source_enabled_property_exists(self):
        """Test that RSSSource.enabled property exists (would catch missing property)."""
        source = RSSSource(feed_name="test", url="https://example.com", active=True)
        
        # This would have failed before our fix  
        assert hasattr(source, 'enabled')
        assert source.enabled == True
        
        source.active = False
        assert source.enabled == False
    
    def test_get_entries_since_until_parameters(self, tmp_path):
        """Test that get_entries supports since/until parameters (would catch parameter error)."""
        from datetime import datetime, timedelta
        
        storage = RSSStorage(tmp_path)
        
        # This would have failed before our fix
        since_time = datetime.now() - timedelta(hours=1)
        until_time = datetime.now()
        
        # These calls should not raise TypeError
        entries1 = storage.get_entries(since=since_time)
        entries2 = storage.get_entries(until=until_time)
        entries3 = storage.get_entries(since=since_time, until=until_time)
        
        assert isinstance(entries1, list)
        assert isinstance(entries2, list)
        assert isinstance(entries3, list)
    
    def test_fastmcp_tools_would_use_fixed_methods(self, tmp_path):
        """Test that the methods/properties used by FastMCP tools exist and work."""
        storage = RSSStorage(tmp_path)
        
        # Test the methods that FastMCP server uses
        # This would catch the get_feeds() missing method
        feeds = storage.get_feeds()
        assert isinstance(feeds, list)
        
        # Test enabled properties that FastMCP uses in JSON serialization
        feed = RSSFeed(name="test", title="Test", active=True)
        assert feed.enabled == True  # Would catch missing property
        
        source = RSSSource(feed_name="test", url="https://example.com", active=True)
        assert source.enabled == True  # Would catch missing property
        
        # Test get_entries with parameters FastMCP passes
        from datetime import datetime
        entries = storage.get_entries(since=datetime.now())  # Would catch missing parameter
        assert isinstance(entries, list)
    

class TestBugPreventionTests:
    """Tests specifically designed to catch the types of bugs we found."""
    
    def test_all_model_properties_accessible(self):
        """Test that all properties used by FastMCP are accessible on models."""
        # Test RSSFeed properties
        feed = RSSFeed(name="test", title="Test", active=True)
        
        # Properties that FastMCP server uses
        properties_to_test = ['name', 'title', 'description', 'active', 'enabled']
        for prop in properties_to_test:
            assert hasattr(feed, prop), f"RSSFeed missing property: {prop}"
            # Try to access (would catch property errors)
            value = getattr(feed, prop)
            assert value is not None or prop in ['description']
        
        # Test RSSSource properties  
        source = RSSSource(feed_name="test", url="https://example.com", active=True)
        
        source_properties = ['url', 'active', 'enabled', 'priority']
        for prop in source_properties:
            assert hasattr(source, prop), f"RSSSource missing property: {prop}"
            value = getattr(source, prop)
            assert value is not None
    
    def test_storage_method_signatures_match_fastmcp_usage(self, tmp_path):
        """Test that storage methods have signatures that match FastMCP usage."""
        storage = RSSStorage(tmp_path)
        
        # Test get_feeds method exists and works
        assert hasattr(storage, 'get_feeds')
        feeds = storage.get_feeds()
        assert isinstance(feeds, list)
        
        # Test get_entries accepts all parameters that FastMCP uses
        from datetime import datetime
        
        # These should all work without TypeError
        entries1 = storage.get_entries(limit=10)
        entries2 = storage.get_entries(feed_name="test", limit=5)
        entries3 = storage.get_entries(since=datetime.now())
        entries4 = storage.get_entries(until=datetime.now())
        entries5 = storage.get_entries(offset=0, limit=10)
        
        for entries in [entries1, entries2, entries3, entries4, entries5]:
            assert isinstance(entries, list)
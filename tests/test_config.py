"""Tests for configuration management."""

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

from rss_mcp.config import RSSConfig, ConfigManager, get_config_manager


class TestRSSConfig:
    """Test RSS configuration."""
    
    def test_create_config(self):
        """Test creating configuration with defaults."""
        config = RSSConfig()
        
        assert config.default_fetch_interval == 3600
        assert config.max_entries_per_feed == 1000
        assert config.cleanup_days == 90
        assert config.http_host == "localhost"
        assert config.http_port == 8080
        assert config.request_timeout == 30
        assert config.max_retries == 3
        assert config.max_concurrent_fetches == 10
        assert config.log_level == "INFO"
        assert config.cache_path  # Should be set by __post_init__
    
    def test_custom_config(self):
        """Test creating configuration with custom values."""
        config = RSSConfig(
            cache_path="/tmp/test.db",
            default_fetch_interval=1800,
            http_port=9000,
        )
        
        assert config.cache_path == "/tmp/test.db"
        assert config.default_fetch_interval == 1800
        assert config.http_port == 9000
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = RSSConfig(
            cache_path="/tmp/test.db",
            http_port=9000,
        )
        
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert config_dict["cache_path"] == "/tmp/test.db"
        assert config_dict["http_port"] == 9000
        assert config_dict["default_fetch_interval"] == 3600
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "cache_path": "/tmp/test.db",
            "http_port": 9000,
            "unknown_field": "ignored",  # Should be filtered out
        }
        
        config = RSSConfig.from_dict(data)
        assert config.cache_path == "/tmp/test.db"
        assert config.http_port == 9000
        assert config.default_fetch_interval == 3600  # Default value
        assert not hasattr(config, "unknown_field")


class TestConfigManager:
    """Test configuration manager."""
    
    def test_create_manager(self, temp_dir):
        """Test creating configuration manager."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        assert manager.config_path == config_path
        assert isinstance(manager.config, RSSConfig)
    
    def test_default_config_path(self):
        """Test using default configuration path."""
        with patch('rss_mcp.config.user_config_dir') as mock_config_dir:
            mock_config_dir.return_value = "/tmp/rss-mcp"
            
            # Clear environment variables to use default behavior
            with patch.dict('os.environ', {}, clear=True):
                manager = ConfigManager()
                assert manager.config_path == Path("/tmp/rss-mcp/default/config.json")
    
    def test_save_and_load(self, temp_dir):
        """Test saving and loading configuration."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        # Modify config
        manager.config.http_port = 9000
        manager.config.log_level = "DEBUG"
        
        # Save
        manager.save()
        assert config_path.exists()
        
        # Create new manager and load
        new_manager = ConfigManager(config_path)
        assert new_manager.config.http_port == 9000
        assert new_manager.config.log_level == "DEBUG"
    
    def test_update_config(self, temp_dir):
        """Test updating configuration."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        callback_called = False
        new_config = None
        
        def callback(config):
            nonlocal callback_called, new_config
            callback_called = True
            new_config = config
        
        manager.add_change_callback(callback)
        
        # Update config
        manager.update(http_port=9000, log_level="DEBUG")
        
        assert manager.config.http_port == 9000
        assert manager.config.log_level == "DEBUG"
        assert callback_called
        assert new_config.http_port == 9000
    
    def test_callback_management(self, temp_dir):
        """Test adding and removing callbacks."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        callback1_called = False
        callback2_called = False
        
        def callback1(config):
            nonlocal callback1_called
            callback1_called = True
        
        def callback2(config):
            nonlocal callback2_called
            callback2_called = True
        
        # Add callbacks
        manager.add_change_callback(callback1)
        manager.add_change_callback(callback2)
        
        # Update config
        manager.update(http_port=9000)
        assert callback1_called
        assert callback2_called
        
        # Reset flags
        callback1_called = False
        callback2_called = False
        
        # Remove one callback
        manager.remove_change_callback(callback1)
        
        # Update config again
        manager.update(http_port=8080)
        assert not callback1_called
        assert callback2_called
    
    def test_load_invalid_json(self, temp_dir):
        """Test loading invalid JSON configuration."""
        config_path = temp_dir / "config.json"
        
        # Write invalid JSON
        with open(config_path, 'w') as f:
            f.write("invalid json content")
        
        # Should fall back to defaults
        manager = ConfigManager(config_path)
        assert isinstance(manager.config, RSSConfig)
        assert manager.config.http_port == 8080  # Default value
    
    def test_unknown_config_key(self, temp_dir):
        """Test updating with unknown configuration key."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        # Should not raise error but log warning
        manager.update(unknown_key="value")
        
        # Config should be unchanged
        assert not hasattr(manager.config, "unknown_key")
    
    @pytest.mark.asyncio
    async def test_context_manager(self, temp_dir):
        """Test using ConfigManager as context manager."""
        config_path = temp_dir / "config.json"
        
        with patch.object(ConfigManager, 'start_watching') as mock_start:
            with patch.object(ConfigManager, 'stop_watching') as mock_stop:
                async with ConfigManager(config_path) as manager:
                    assert isinstance(manager, ConfigManager)
                    mock_start.assert_called_once()
                
                mock_stop.assert_called_once()


class TestGlobalConfigManager:
    """Test global configuration manager functions."""
    
    def test_get_config_manager_singleton(self):
        """Test that get_config_manager returns singleton."""
        # Clear global instance
        import rss_mcp.config
        rss_mcp.config._config_manager = None
        
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        
        assert manager1 is manager2
    
    def test_get_config(self):
        """Test getting current configuration."""
        from rss_mcp.config import get_config
        
        # Clear global instance
        import rss_mcp.config
        rss_mcp.config._config_manager = None
        
        config = get_config()
        assert isinstance(config, RSSConfig)


class TestEnvironmentVariables:
    """Test environment variable support."""
    
    def test_config_dir_from_env_var(self, temp_dir):
        """Test RSS_MCP_CONFIG_DIR environment variable."""
        config_dir = temp_dir / "custom_config"
        
        with patch.dict('os.environ', {'RSS_MCP_CONFIG_DIR': str(config_dir)}):
            manager = ConfigManager(user_id="testuser")
            expected_path = config_dir / "testuser" / "config.json"
            assert manager.config_path == expected_path
    
    def test_cache_path_from_env_var(self, temp_dir):
        """Test RSS_MCP_CACHE_DIR environment variable."""
        cache_path = temp_dir / "custom_cache_dir" 
        with patch.dict('os.environ', {'RSS_MCP_CACHE_DIR': str(cache_path)}):
            config = RSSConfig()
            assert config.cache_path == str(cache_path)
            assert Path(cache_path).exists()
    
    def test_config_fallback_to_default(self):
        """Test fallback to default config path when env var not set."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('rss_mcp.config.user_config_dir') as mock_config_dir:
                mock_config_dir.return_value = "/tmp/rss-mcp"
                
                manager = ConfigManager()
                assert manager.config_path == Path("/tmp/rss-mcp/default/config.json")
    
    def test_cache_fallback_to_default(self):
        """Test fallback to default cache path when env var not set."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('rss_mcp.config.user_cache_dir') as mock_cache_dir:
                mock_cache_dir.return_value = "/tmp/rss-mcp-cache"
                
                config = RSSConfig()
                assert config.cache_path == "/tmp/rss-mcp-cache"
    
    def test_explicit_path_overrides_env_var(self, temp_dir):
        """Test that explicit path parameter overrides environment variable."""
        env_config_dir = temp_dir / "env_config_dir"
        explicit_config_path = temp_dir / "explicit_config.json"
        
        with patch.dict('os.environ', {'RSS_MCP_CONFIG_DIR': str(env_config_dir)}):
            manager = ConfigManager(config_path=explicit_config_path)
            assert manager.config_path == explicit_config_path
    
    def test_env_vars_isolation(self, temp_dir):
        """Test that environment variables are properly isolated in tests."""
        # This test ensures our test fixtures properly isolate environment variables
        config_dir = temp_dir / "test_config_dir"
        cache_path = temp_dir / "test_cache"
        
        with patch.dict('os.environ', {
            'RSS_MCP_CONFIG_DIR': str(config_dir),
            'RSS_MCP_CACHE_DIR': str(cache_path)
        }):
            manager = ConfigManager(user_id="testuser")
            config = RSSConfig()
            
            expected_config_path = config_dir / "testuser" / "config.json"
            assert manager.config_path == expected_config_path
            assert config.cache_path == str(cache_path)
            assert Path(cache_path).exists()
    
    def test_cache_directory_creation(self, temp_dir):
        """Test that cache directory is created automatically."""
        cache_path = temp_dir / "nested" / "cache" / "dir"
        
        with patch.dict('os.environ', {'RSS_MCP_CACHE_DIR': str(cache_path)}):
            config = RSSConfig()
            assert config.cache_path == str(cache_path)
            assert cache_path.exists()
            assert cache_path.is_dir()
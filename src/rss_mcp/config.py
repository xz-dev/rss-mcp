"""Configuration management with auto-reload support."""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from platformdirs import user_cache_dir, user_config_dir
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


def get_user_id(headers: Optional[Dict[str, str]] = None) -> str:
    """Get user ID from headers or environment variable.

    Args:
        headers: Optional HTTP headers dictionary to check for X-User-ID (case insensitive)

    Returns:
        User ID string, defaults to "default" if not found
    """
    # Check HTTP headers first (for HTTP/SSE mode)
    # Headers are case-insensitive, so normalize to lowercase for lookup
    if headers:
        # Create a case-insensitive header lookup
        lower_headers = {k.lower(): v for k, v in headers.items()}
        if "x-user-id" in lower_headers:
            user_id = lower_headers["x-user-id"].strip()
            if user_id:
                return user_id

    # Check environment variable (for stdio mode)
    # Environment variables are case-sensitive, must be exact: RSS_MCP_USER
    user_id = os.getenv("RSS_MCP_USER", "").strip()
    if user_id:
        return user_id

    # Default fallback
    return "default"


@dataclass
class RSSConfig:
    """RSS MCP server configuration."""

    # Cache settings
    cache_path: str = ""

    # Server settings
    default_fetch_interval: int = 3600  # 1 hour
    max_entries_per_feed: int = 1000
    cleanup_days: int = 90

    # HTTP server settings
    http_host: str = "localhost"
    http_port: int = 8080

    # Fetching settings
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 60
    user_agent: str = "RSS-MCP-Server/1.0"

    # Performance settings
    max_concurrent_fetches: int = 10
    rate_limit_requests: int = 100
    rate_limit_period: int = 3600  # 1 hour

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    def __post_init__(self):
        """Set defaults after initialization."""
        if not self.cache_path:
            # Check environment variable
            cache_path = os.getenv("RSS_MCP_CACHE_DIR")
            if cache_path:
                cache_dir = Path(cache_path)
            else:
                cache_dir = Path(user_cache_dir("rss-mcp"))
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_path = str(cache_dir)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RSSConfig":
        """Create from dictionary."""
        # Filter out unknown fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)


class ConfigWatcher(FileSystemEventHandler):
    """File system event handler for config changes."""

    def __init__(self, config_path: Path, callback: Callable[[], None]):
        """Initialize watcher."""
        self.config_path = config_path
        self.callback = callback

    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and Path(event.src_path) == self.config_path:
            logger.info(f"Config file changed: {self.config_path}")
            self.callback()


class ConfigManager:
    """Manages RSS configuration with auto-reload support."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        user_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize configuration manager.

        Args:
            config_path: Path to config file. If None, uses environment variable or default location.
            user_id: User ID for per-user configuration. If None, gets from headers or environment.
            headers: Optional HTTP headers for extracting user ID.
        """
        if config_path is None:
            # Get user ID for per-user config
            if user_id is None:
                user_id = get_user_id(headers)

            # Check for custom config base directory
            config_base = os.getenv("RSS_MCP_CONFIG_DIR")
            if config_base:
                config_dir = Path(config_base) / user_id
            else:
                config_dir = Path(user_config_dir("rss-mcp")) / user_id

            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "config.json"
        else:
            self.config_path = Path(config_path)

        self.config = RSSConfig()
        self._observers: list[Observer] = []
        self._callbacks: list[Callable[[RSSConfig], None]] = []

        # Load initial config
        self.load()

    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.config = RSSConfig.from_dict(data)
                logger.info(f"Loaded config from {self.config_path}")

            except Exception as e:
                logger.error(f"Error loading config from {self.config_path}: {e}")
                logger.info("Using default configuration")
                self.config = RSSConfig()
        else:
            logger.info("Config file not found, using defaults")
            self.config = RSSConfig()
            # Save default config
            self.save()

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2)

            logger.info(f"Saved config to {self.config_path}")

        except Exception as e:
            logger.error(f"Error saving config to {self.config_path}: {e}")

    def update(self, **kwargs) -> None:
        """Update configuration values."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                logger.warning(f"Unknown config key: {key}")

        # Recreate config to trigger __post_init__
        self.config = RSSConfig.from_dict(self.config.to_dict())
        self.save()

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(self.config)
            except Exception as e:
                logger.error(f"Error in config callback: {e}")

    def add_change_callback(self, callback: Callable[[RSSConfig], None]) -> None:
        """Add callback for config changes."""
        self._callbacks.append(callback)

    def remove_change_callback(self, callback: Callable[[RSSConfig], None]) -> None:
        """Remove config change callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start_watching(self) -> None:
        """Start watching config file for changes."""
        if self._observers:
            logger.warning("Config watcher already started")
            return

        def on_config_changed():
            """Handle config file changes."""
            old_config = self.config.to_dict()
            self.load()

            # Only notify if config actually changed
            if self.config.to_dict() != old_config:
                logger.info("Configuration reloaded")
                for callback in self._callbacks:
                    try:
                        callback(self.config)
                    except Exception as e:
                        logger.error(f"Error in config callback: {e}")

        # Watch the config directory
        observer = Observer()
        watcher = ConfigWatcher(self.config_path, on_config_changed)
        observer.schedule(watcher, str(self.config_path.parent), recursive=False)
        observer.start()
        self._observers.append(observer)

        logger.info(f"Started watching config file: {self.config_path}")

    def stop_watching(self) -> None:
        """Stop watching config file for changes."""
        for observer in self._observers:
            observer.stop()
            observer.join()

        self._observers.clear()
        logger.info("Stopped config file watching")

    def __enter__(self):
        """Context manager entry."""
        self.start_watching()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_watching()

    async def __aenter__(self):
        """Async context manager entry."""
        self.start_watching()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.stop_watching()


# Global config manager instances per user
_config_managers: Dict[str, ConfigManager] = {}


def get_config_manager(
    config_path: Optional[Path] = None,
    user_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ConfigManager:
    """Get the config manager instance for a specific user."""
    effective_user_id = user_id or get_user_id(headers)

    if effective_user_id not in _config_managers:
        _config_managers[effective_user_id] = ConfigManager(config_path, effective_user_id, headers)

    return _config_managers[effective_user_id]


def get_config() -> RSSConfig:
    """Get the current configuration."""
    return get_config_manager().config

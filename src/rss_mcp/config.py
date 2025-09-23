"""Configuration management with auto-reload support."""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from platformdirs import user_cache_dir, user_config_dir

logger = logging.getLogger(__name__)


def get_user_id(headers: Optional[Dict[str, str]] = None) -> str:
    """Get user ID from headers or environment variable.

    Args:
        headers: Optional HTTP headers dictionary to check for X-User-ID (case insensitive)

    Returns:
        User ID string, defaults to "default" if not found

    Raises:
        ValueError: If RSS_MCP_REQUIRE_USER_ID is set and no user ID is provided
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

    # Check if default user is disabled
    require_user_id = os.getenv("RSS_MCP_REQUIRE_USER_ID", "").lower() in ("1", "true", "yes", "on")
    if require_user_id:
        raise ValueError(
            "User ID is required but not provided. "
            "Set RSS_MCP_USER environment variable or provide X-User-ID header. "
            "To disable this requirement, unset RSS_MCP_REQUIRE_USER_ID."
        )

    # Default fallback
    return "default"


@dataclass
class RSSFeedConfig:
    """Individual RSS feed configuration."""

    name: str
    title: str
    description: str
    sources: List[str]
    fetch_interval: int = 3600
    retention_period: int = 2592000  # 30 days in seconds (30 * 24 * 60 * 60)


class Config:
    def __init__(
        self,
        cache_path: Path,
        config_path: Path,
        log_level: str,
        log_file_dir: Optional[Path] = None,
    ):
        self.cache_path = cache_path
        self.config_path = config_path
        self.log_level = log_level
        self.log_file_dir = log_file_dir

    @property
    def log_file_path(self) -> Path:
        """Get the log file path if log_file_dir is set."""
        # Date as filename
        from datetime import datetime

        date_str = datetime.now().strftime("%Y-%m-%d")
        file_name = f"{date_str}.log"
        if self.log_file_dir:
            return self.log_file_dir / file_name
        else:
            return self.cache_path / "logs" / file_name


@dataclass
class UserConfig:
    rss_list: List[RSSFeedConfig]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "UserConfig":
        """Create UserConfig from dictionary."""
        rss_list = [RSSFeedConfig(**item) for item in data.get("rss_list", [])]
        return UserConfig(rss_list=rss_list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert UserConfig to dictionary."""
        return {"rss_list": [asdict(item) for item in self.rss_list]}


class UserConfigManager:
    def __init__(
        self,
        config: Config,
        user_id: str,
    ):
        self.config = config
        self.user_id = user_id
        self.user_config: UserConfig = UserConfig(rss_list=[])

    def load(self):
        """Load user configuration from file."""
        try:
            user_config_path = self.config.config_path / self.user_id / "config.json"
            if user_config_path.exists():
                with open(user_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_config = UserConfig.from_dict(data)
            else:
                self.user_config = UserConfig(rss_list=[])
        except Exception as e:
            logger.error(f"Error loading user config for {self.user_id}: {e}")

    def save(self) -> None:
        """Save user configuration to file."""
        try:
            user_config_path = self.config.config_path / self.user_id / "config.json"
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(user_config_path, "w", encoding="utf-8") as f:
                json.dump(self.user_config.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving user config for {self.user_id}: {e}")

    def __enter__(self) -> "UserConfigManager":
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.save()


config = Config(
    cache_path=Path(os.getenv("RSS_MCP_CACHE_PATH", user_cache_dir("rss-mcp"))),
    config_path=Path(os.getenv("RSS_MCP_CONFIG_PATH", user_config_dir("rss-mcp"))),
    log_level=os.getenv("RSS_MCP_LOG_LEVEL", "INFO"),
    log_file_dir=(
        Path(os.getenv("RSS_MCP_LOG_DIR", "")) if os.getenv("RSS_MCP_LOG_DIR", "") else None
    ),
)

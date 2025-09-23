from typing import List

from .config import RSSFeedConfig, UserConfigManager


class UserRssManager:
    def __init__(self, user_config: UserConfigManager):
        self.config_manager = user_config

    def get_feeds(self) -> List[RSSFeedConfig]:
        """Get a list of all RSS feeds."""
        with self.config_manager as config_manager:
            return config_manager.user_config.rss_list

    def add_feed(self, feed: RSSFeedConfig) -> bool:
        """Add a new RSS feed configuration."""
        with self.config_manager as config_manager:
            if any(
                existing_feed.name == feed.name
                for existing_feed in config_manager.user_config.rss_list
            ):
                return False  # Feed with the same name already exists
            config_manager.user_config.rss_list.append(feed)
            return True

    def remove_feed(self, feed_name: str) -> bool:
        """Remove an RSS feed configuration by name. Returns True if removed, False if not found."""
        with self.config_manager as config_manager:
            for i, feed in enumerate(config_manager.user_config.rss_list):
                if feed.name == feed_name:
                    del config_manager.user_config.rss_list[i]
                    return True
        return False

    def update_feed(self, feed_name: str, new_feed_config: RSSFeedConfig) -> bool:
        """Update an existing RSS feed configuration by name. Returns True if updated, False if not found."""
        with self.config_manager as config_manager:
            for i, feed in enumerate(config_manager.user_config.rss_list):
                if feed.name == feed_name:
                    config_manager.user_config.rss_list[i] = new_feed_config
                    return True
        return False

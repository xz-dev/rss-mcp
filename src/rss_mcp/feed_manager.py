"""RSS feed fetching and management with failover support."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
import feedparser
from dateutil import parser as date_parser

from .config import RSSConfig
from .models import RSSEntry, RSSFeed, RSSSource
from .storage import RSSStorage


logger = logging.getLogger(__name__)


class FeedFetcher:
    """Handles RSS feed fetching with failover support."""
    
    def __init__(self, config: RSSConfig, storage: RSSStorage):
        """Initialize feed fetcher."""
        self.config = config
        self.storage = storage
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            headers = {
                'User-Agent': self.config.user_agent
            }
            self._session = aiohttp.ClientSession(
                timeout=timeout, 
                headers=headers
            )
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def fetch_feed_content(self, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Fetch feed content from URL.
        
        Returns:
            (success, content, error_message)
        """
        try:
            session = await self._get_session()
            
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    return True, content, None
                else:
                    error = f"HTTP {response.status}: {response.reason}"
                    return False, None, error
                    
        except asyncio.TimeoutError:
            return False, None, "Request timeout"
        except aiohttp.ClientError as e:
            return False, None, f"Client error: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"
    
    def parse_feed_content(self, content: str, source_url: str) -> Tuple[bool, Optional[feedparser.FeedParserDict], Optional[str]]:
        """Parse RSS feed content.
        
        Returns:
            (success, parsed_feed, error_message)
        """
        try:
            feed = feedparser.parse(content)
            
            # Check for parsing errors
            if hasattr(feed, 'bozo') and feed.bozo:
                if hasattr(feed, 'bozo_exception'):
                    logger.warning(f"Feed parsing warning for {source_url}: {feed.bozo_exception}")
            
            # Check if we got any entries
            if not hasattr(feed, 'entries'):
                return False, None, "No entries found in feed"
            
            return True, feed, None
            
        except Exception as e:
            return False, None, f"Parse error: {str(e)}"
    
    def extract_entries(self, parsed_feed: feedparser.FeedParserDict, feed_name: str, source_url: str) -> List[RSSEntry]:
        """Extract entries from parsed feed."""
        entries = []
        
        for entry in parsed_feed.entries:
            try:
                # Extract basic fields
                title = entry.get('title', 'Untitled')
                link = entry.get('link', '')
                description = entry.get('description', '')
                content = entry.get('content', '')
                author = entry.get('author', '')
                
                # Handle content field (can be a list)
                if isinstance(content, list) and content:
                    content = content[0].get('value', '')
                elif hasattr(content, 'value'):
                    content = content.value
                else:
                    content = str(content) if content else description
                
                # Extract GUID
                guid = entry.get('guid', entry.get('id', link))
                if hasattr(guid, 'href'):
                    guid = guid.href
                
                # Parse dates
                published = self._parse_date(entry.get('published_parsed') or entry.get('published'))
                updated = self._parse_date(entry.get('updated_parsed') or entry.get('updated'))
                
                # Extract tags
                tags = []
                if hasattr(entry, 'tags'):
                    tags = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
                elif 'category' in entry:
                    category = entry.category
                    if isinstance(category, str):
                        tags = [category]
                    elif hasattr(category, '__iter__'):
                        tags = list(category)
                
                # Extract enclosures (media attachments)
                enclosures = []
                if hasattr(entry, 'enclosures'):
                    enclosures = [enc.href for enc in entry.enclosures if hasattr(enc, 'href')]
                elif 'media_content' in entry:
                    media_content = entry.media_content
                    if isinstance(media_content, list):
                        enclosures = [m.get('url', '') for m in media_content if m.get('url')]
                
                # Create entry
                rss_entry = RSSEntry(
                    feed_name=feed_name,
                    source_url=source_url,
                    guid=str(guid),
                    title=title,
                    link=link,
                    description=description,
                    content=content,
                    author=author,
                    published=published,
                    updated=updated,
                    tags=tags,
                    enclosures=enclosures,
                )
                
                entries.append(rss_entry)
                
            except Exception as e:
                logger.warning(f"Error extracting entry from {source_url}: {e}")
                continue
        
        return entries
    
    def _parse_date(self, date_value) -> Optional[datetime]:
        """Parse various date formats to datetime."""
        if not date_value:
            return None
        
        try:
            # Handle time.struct_time from feedparser
            if hasattr(date_value, 'tm_year'):
                return datetime(*date_value[:6], tzinfo=timezone.utc)
            
            # Handle string dates
            if isinstance(date_value, str):
                parsed = date_parser.parse(date_value)
                # Ensure timezone awareness
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            
            # Handle datetime objects
            if isinstance(date_value, datetime):
                if date_value.tzinfo is None:
                    date_value = date_value.replace(tzinfo=timezone.utc)
                return date_value
                
        except Exception as e:
            logger.warning(f"Error parsing date {date_value}: {e}")
        
        return None
    
    async def fetch_feed_with_failover(self, feed: RSSFeed) -> Tuple[bool, List[RSSEntry], str]:
        """Fetch feed using failover between sources.
        
        Returns:
            (success, entries, status_message)
        """
        entries = []
        last_error = "No sources available"
        
        # Get healthy sources ordered by priority
        sources = feed.healthy_sources
        if not sources:
            # Try all sources if no healthy ones
            sources = [s for s in feed.sources if s.active]
        
        if not sources:
            return False, [], "No active sources configured"
        
        for source in sources:
            logger.info(f"Fetching {feed.name} from {source.url}")
            
            # Update source fetch time
            source.last_fetch = datetime.now()
            self.storage.update_source(source)
            
            # Fetch content
            success, content, error = await self.fetch_feed_content(source.url)
            
            if not success:
                # Update source error info
                source.error_count += 1
                source.last_error = error
                self.storage.update_source(source)
                
                last_error = f"Source {source.url}: {error}"
                logger.warning(f"Failed to fetch from {source.url}: {error}")
                continue
            
            # Parse content
            success, parsed_feed, error = self.parse_feed_content(content, source.url)
            
            if not success:
                # Update source error info
                source.error_count += 1
                source.last_error = error
                self.storage.update_source(source)
                
                last_error = f"Source {source.url}: {error}"
                logger.warning(f"Failed to parse from {source.url}: {error}")
                continue
            
            # Extract entries
            try:
                entries = self.extract_entries(parsed_feed, feed.name, source.url)
                
                # Update feed metadata from successful source
                if hasattr(parsed_feed.feed, 'title') and parsed_feed.feed.title:
                    feed.title = parsed_feed.feed.title
                if hasattr(parsed_feed.feed, 'description') and parsed_feed.feed.description:
                    feed.description = parsed_feed.feed.description
                if hasattr(parsed_feed.feed, 'link') and parsed_feed.feed.link:
                    feed.link = parsed_feed.feed.link
                
                # Update source success info
                source.last_success = datetime.now()
                source.error_count = 0
                source.last_error = None
                self.storage.update_source(source)
                
                # Update feed success info
                feed.last_success = datetime.now()
                self.storage.update_feed(feed)
                
                logger.info(f"Successfully fetched {len(entries)} entries from {source.url}")
                return True, entries, f"Fetched {len(entries)} entries from {source.url}"
                
            except Exception as e:
                source.error_count += 1
                source.last_error = str(e)
                self.storage.update_source(source)
                
                last_error = f"Source {source.url}: {str(e)}"
                logger.error(f"Error processing entries from {source.url}: {e}")
                continue
        
        return False, [], last_error
    
    async def store_entries(self, entries: List[RSSEntry]) -> int:
        """Store entries in database, avoiding duplicates.
        
        Returns:
            Number of new entries stored.
        """
        new_count = 0
        
        for entry in entries:
            if self.storage.create_entry(entry):
                new_count += 1
            else:
                logger.debug(f"Entry already exists: {entry.guid}")
        
        return new_count
    
    async def refresh_feed(self, feed_name: str) -> Tuple[bool, str]:
        """Refresh a single feed.
        
        Returns:
            (success, status_message)
        """
        feed = self.storage.get_feed(feed_name)
        if not feed:
            return False, f"Feed '{feed_name}' not found"
        
        if not feed.active:
            return False, f"Feed '{feed_name}' is disabled"
        
        # Update feed fetch time
        feed.last_fetch = datetime.now()
        self.storage.update_feed(feed)
        
        # Fetch entries
        success, entries, message = await self.fetch_feed_with_failover(feed)
        
        if success:
            # Store new entries
            new_count = await self.store_entries(entries)
            
            # Update feed entry count
            feed.entry_count = self.storage.get_entry_count(feed_name=feed_name)
            self.storage.update_feed(feed)
            
            final_message = f"Feed '{feed_name}': {new_count} new entries (total: {feed.entry_count})"
            return True, final_message
        else:
            return False, f"Feed '{feed_name}': {message}"
    
    async def refresh_all_feeds(self, feed_names: Optional[List[str]] = None) -> List[Tuple[str, bool, str]]:
        """Refresh multiple feeds concurrently.
        
        Args:
            feed_names: Specific feeds to refresh, or None for all active feeds
            
        Returns:
            List of (feed_name, success, message) tuples
        """
        if feed_names is None:
            feeds = self.storage.list_feeds(active_only=True)
            feed_names = [feed.name for feed in feeds]
        
        # Limit concurrent fetches
        semaphore = asyncio.Semaphore(self.config.max_concurrent_fetches)
        
        async def refresh_with_semaphore(feed_name: str) -> Tuple[str, bool, str]:
            async with semaphore:
                success, message = await self.refresh_feed(feed_name)
                return feed_name, success, message
        
        # Execute refreshes concurrently
        tasks = [refresh_with_semaphore(name) for name in feed_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append((feed_names[i], False, str(result)))
            else:
                final_results.append(result)
        
        return final_results
    
    def cleanup_old_entries(self) -> int:
        """Clean up old entries based on config."""
        return self.storage.cleanup_old_entries(self.config.cleanup_days)
"""Command-line interface for RSS MCP server."""

import asyncio
import sys
from datetime import datetime, timedelta

import click
from dateutil import parser as date_parser

from .cache_storage import CacheStorage
from .config import RSSFeedConfig, UserConfigManager, config, get_user_id
from .feed_manager import FeedManager
from .user_rss_manager import UserRssManager


def get_user_resources() -> tuple[UserRssManager, FeedManager, CacheStorage]:
    """Get user-specific resources for CLI operations."""
    user_id = get_user_id()
    user_config_manager = UserConfigManager(config, user_id)
    user_manager = UserRssManager(user_config_manager)
    cache_storage = CacheStorage(config.cache_path, user_id)
    feed_manager = FeedManager(user_manager, cache_storage, config)
    return user_manager, feed_manager, cache_storage


@click.group()
def cli():
    """RSS MCP Server - Manage RSS feeds with AI integration."""


@cli.group()
def feed():
    """Manage RSS feeds."""


@feed.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--title", help="Feed title")
@click.option("--description", help="Feed description")
@click.option("--interval", type=int, default=3600, help="Fetch interval in seconds")
def add_feed(name, url, title, description, interval):
    """Add a new RSS feed with source URL."""
    try:
        user_manager, _, _ = get_user_resources()

        # Check if feed already exists
        existing_feeds = user_manager.get_feeds()
        if any(feed.name == name for feed in existing_feeds):
            click.echo(f"Error: Feed '{name}' already exists", err=True)
            sys.exit(1)

        # Create feed config
        feed_config = RSSFeedConfig(
            name=name,
            title=title or name,
            description=description or "",
            sources=[url],
            fetch_interval=interval,
        )

        # Add to configuration
        if user_manager.add_feed(feed_config):
            click.echo(f"✓ Added feed '{name}' with source {url}")
        else:
            click.echo(f"Error: Failed to create feed '{name}'", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def list_feeds(verbose):
    """List all RSS feeds."""
    try:
        user_manager, _, cache_storage = get_user_resources()
        feeds = user_manager.get_feeds()

        if not feeds:
            click.echo("No feeds found")
            return

        for feed in feeds:
            status = "🟢" if feed.sources else "🔴"  # Green if has sources, red if empty
            entry_count = cache_storage.get_entry_count(feed.name)

            if verbose:
                click.echo(f"{status} {feed.name}")
                click.echo(f"  Title: {feed.title}")
                click.echo(f"  Description: {feed.description}")
                click.echo(f"  Sources: {len(feed.sources)}")
                for i, source in enumerate(feed.sources):
                    click.echo(f"    {i+1}. {source}")
                click.echo(f"  Entries: {entry_count}")
                click.echo(f"  Fetch Interval: {feed.fetch_interval}s")
                click.echo()
            else:
                click.echo(f"{status} {feed.name} ({entry_count} entries)")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("remove")
@click.argument("name")
@click.option("--keep-entries", is_flag=True, help="Keep cached entries")
def remove_feed(name, keep_entries):
    """Remove an RSS feed."""
    try:
        user_manager, _, cache_storage = get_user_resources()

        if user_manager.remove_feed(name):
            if not keep_entries:
                entries_removed = cache_storage.delete_feed_entries(name)
                click.echo(f"✓ Removed feed '{name}' and {entries_removed} entries")
            else:
                click.echo(f"✓ Removed feed '{name}' (entries preserved)")
        else:
            click.echo(f"Error: Feed '{name}' not found", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("refresh")
@click.argument("name", required=False)
@click.option("--all", "refresh_all", is_flag=True, help="Refresh all feeds")
def refresh_feeds(name, refresh_all):
    """Refresh RSS feeds."""
    try:
        user_manager, feed_manager, _ = get_user_resources()

        async def do_refresh():
            if refresh_all or name is None:
                # Refresh all feeds
                feeds = user_manager.get_feeds()
                feed_names = [feed.name for feed in feeds]
                if not feed_names:
                    click.echo("No feeds to refresh")
                    return

                click.echo(f"Refreshing {len(feed_names)} feeds...")
                results = await feed_manager.refresh_all_feeds(feed_names)

                success_count = 0
                total_entries = 0

                for feed_name, success, message in results:
                    if success:
                        success_count += 1
                        # Extract entry count from message
                        import re

                        match = re.search(r"(\d+) new entries", message)
                        if match:
                            new_count = int(match.group(1))
                            total_entries += new_count
                            click.echo(f"✓ {feed_name}: {new_count} new entries")
                        else:
                            click.echo(f"✓ {feed_name}: refreshed")
                    else:
                        click.echo(f"✗ {feed_name}: {message}")

                click.echo(
                    f"\nRefreshed {success_count}/{len(feed_names)} feeds, {total_entries} new entries total"
                )

            else:
                # Refresh specific feed
                feeds = user_manager.get_feeds()
                if not any(feed.name == name for feed in feeds):
                    click.echo(f"Error: Feed '{name}' not found", err=True)
                    sys.exit(1)

                click.echo(f"Refreshing feed '{name}'...")
                success, message = await feed_manager.refresh_feed(name)

                if success:
                    click.echo(f"✓ {message}")
                else:
                    click.echo(f"✗ {message}")

        # Run async refresh
        asyncio.run(do_refresh())

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("add-source")
@click.argument("feed_name")
@click.argument("url")
def add_source(feed_name, url):
    """Add a source URL to an existing feed."""
    try:
        user_manager, _, _ = get_user_resources()

        # Get current feeds
        feeds = user_manager.get_feeds()
        target_feed = None
        for feed in feeds:
            if feed.name == feed_name:
                target_feed = feed
                break

        if not target_feed:
            click.echo(f"Error: Feed '{feed_name}' not found", err=True)
            sys.exit(1)

        # Add source URL if not already present
        if url not in target_feed.sources:
            target_feed.sources.append(url)
            if user_manager.update_feed(feed_name, target_feed):
                click.echo(f"✓ Added source {url} to feed '{feed_name}'")
            else:
                click.echo(f"Error: Failed to update feed '{feed_name}'", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: Source {url} already exists in feed '{feed_name}'", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("remove-source")
@click.argument("feed_name")
@click.argument("url")
def remove_source(feed_name, url):
    """Remove a source URL from a feed."""
    try:
        user_manager, _, _ = get_user_resources()

        # Get current feeds
        feeds = user_manager.get_feeds()
        target_feed = None
        for feed in feeds:
            if feed.name == feed_name:
                target_feed = feed
                break

        if not target_feed:
            click.echo(f"Error: Feed '{feed_name}' not found", err=True)
            sys.exit(1)

        # Remove source URL if present
        if url in target_feed.sources:
            target_feed.sources.remove(url)
            if user_manager.update_feed(feed_name, target_feed):
                click.echo(f"✓ Removed source {url} from feed '{feed_name}'")
            else:
                click.echo(f"Error: Failed to update feed '{feed_name}'", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: Source {url} not found in feed '{feed_name}'", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def entries():
    """Manage RSS entries."""


@entries.command("list")
@click.option("--feed", help="Filter by feed name")
@click.option("--limit", type=int, default=20, help="Number of entries to show")
@click.option("--offset", type=int, default=0, help="Number of entries to skip")
@click.option("--since", help="Show entries since date (ISO format)")
@click.option("--until", help="Show entries until date (ISO format)")
def list_entries(feed, limit, offset, since, until):
    """List RSS entries."""
    try:
        _, _, cache_storage = get_user_resources()

        # Parse date filters
        since_dt = None
        until_dt = None
        if since:
            since_dt = date_parser.parse(since)
        if until:
            until_dt = date_parser.parse(until)

        entries = cache_storage.get_entries(
            feed_name=feed, limit=limit, offset=offset, since=since_dt, until=until_dt
        )

        if not entries:
            click.echo("No entries found")
            return

        for entry in entries:
            published = entry.effective_published.strftime("%Y-%m-%d %H:%M")
            click.echo(f"[{published}] {entry.feed_name}: {entry.title}")
            if entry.author:
                click.echo(f"  Author: {entry.author}")
            if entry.tags:
                click.echo(f"  Tags: {', '.join(entry.tags)}")
            click.echo(f"  Link: {entry.link}")
            click.echo(f"  Summary: {entry.get_truncated_summary(100)}")
            click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@entries.command("count")
@click.option("--feed", help="Filter by feed name")
def count_entries(feed):
    """Count RSS entries."""
    try:
        _, _, cache_storage = get_user_resources()
        count = cache_storage.get_entry_count(feed_name=feed)

        if feed:
            click.echo(f"Feed '{feed}': {count} entries")
        else:
            click.echo(f"Total entries: {count}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@entries.command("cleanup")
@click.option("--days", type=int, default=30, help="Remove entries older than N days")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def cleanup_entries(days, confirm):
    """Clean up old RSS entries."""
    try:
        _, _, cache_storage = get_user_resources()

        if not confirm:
            if not click.confirm(f"Remove entries older than {days} days?"):
                return

        removed_count = cache_storage.cleanup_old_entries(days)
        click.echo(f"✓ Removed {removed_count} old entries")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def serve():
    """Server management commands."""


@serve.command("stdio")
def serve_stdio():
    """Run the MCP server in stdio mode."""
    try:
        from .server import run_stdio

        asyncio.run(run_stdio())
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serve.command("http")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", type=int, default=8000, help="Port to bind to")
def serve_http(host, port):
    """Run the MCP server in HTTP mode with modern transport support."""
    try:
        from .server import run_http_with_sse

        click.echo(f"Starting HTTP server on {host}:{port}")
        click.echo(f"  Modern HTTP transport with automatic protocol negotiation")
        asyncio.run(run_http_with_sse(host, port))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command("stats")
@click.option("--feed", help="Show stats for specific feed")
def show_stats(feed):
    """Show feed statistics."""
    try:
        user_manager, _, cache_storage = get_user_resources()

        if feed:
            # Specific feed stats
            feeds = user_manager.get_feeds()
            if not any(f.name == feed for f in feeds):
                click.echo(f"Error: Feed '{feed}' not found", err=True)
                sys.exit(1)

            total_entries = cache_storage.get_entry_count(feed)

            # Get recent entries
            now = datetime.now()
            entries_24h = cache_storage.get_entries(
                feed_name=feed, since=now - timedelta(hours=24), limit=1000
            )
            entries_7d = cache_storage.get_entries(
                feed_name=feed, since=now - timedelta(days=7), limit=1000
            )

            click.echo(f"Feed: {feed}")
            click.echo(f"Total entries: {total_entries}")
            click.echo(f"Last 24h: {len(entries_24h)} entries")
            click.echo(f"Last 7d: {len(entries_7d)} entries")
        else:
            # Overall stats
            feeds = user_manager.get_feeds()
            total_feeds = len(feeds)
            total_entries = cache_storage.get_entry_count()

            # Get recent entries
            now = datetime.now()
            entries_24h = cache_storage.get_entries(since=now - timedelta(hours=24), limit=1000)
            entries_7d = cache_storage.get_entries(since=now - timedelta(days=7), limit=1000)

            click.echo("RSS MCP Statistics")
            click.echo("-" * 20)
            click.echo(f"Total feeds: {total_feeds}")
            click.echo(f"Total entries: {total_entries}")
            click.echo(f"Last 24h: {len(entries_24h)} entries")
            click.echo(f"Last 7d: {len(entries_7d)} entries")

            if feeds:
                click.echo("\nPer-feed stats:")
                for feed_config in feeds:
                    feed_entries = cache_storage.get_entry_count(feed_config.name)
                    click.echo(f"  {feed_config.name}: {feed_entries} entries")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()

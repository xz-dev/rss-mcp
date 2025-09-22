"""Command-line interface for RSS MCP server."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click
from dateutil import parser as date_parser

from .config import get_config_manager
from .feed_manager import FeedFetcher
from .models import RSSFeed, RSSSource
from .storage import RSSStorage


def get_storage() -> RSSStorage:
    """Get storage instance using config."""
    config = get_config_manager().config
    return RSSStorage(Path(config.cache_path))


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
@click.option("--interval", type=int, help="Fetch interval in seconds")
@click.option("--priority", type=int, default=0, help="Source priority (lower = higher priority)")
def add_feed(name, url, title, description, interval, priority):
    """Add a new RSS feed with source URL."""
    try:
        storage = get_storage()
        config = get_config_manager().config

        # Check if feed already exists
        existing = storage.get_feed(name)
        if existing:
            click.echo(f"Error: Feed '{name}' already exists", err=True)
            sys.exit(1)

        # Create feed
        feed = RSSFeed(
            name=name,
            title=title or name,
            description=description or "",
            fetch_interval=interval or config.default_fetch_interval,
        )

        # Create source
        source = RSSSource(
            feed_name=name,
            url=url,
            priority=priority,
        )
        feed.sources.append(source)

        # Save to database
        if storage.create_feed(feed):
            # Also save the source
            if storage.create_source(source):
                click.echo(f"✓ Added feed '{name}' with source {url}")
            else:
                click.echo(f"Error: Failed to create source for feed '{name}'", err=True)
                sys.exit(1)
        else:
            click.echo(f"Error: Failed to create feed '{name}'", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("list")
@click.option("--active-only", is_flag=True, help="Show only active feeds")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def list_feeds(active_only, verbose):
    """List all RSS feeds."""
    try:
        storage = get_storage()
        feeds = storage.list_feeds(active_only=active_only)

        if not feeds:
            click.echo("No feeds found")
            return

        for feed in feeds:
            status = "🟢" if feed.active else "🔴"

            if verbose:
                click.echo(f"\n{status} {feed.name}")
                click.echo(f"  Title: {feed.title}")
                if feed.description:
                    click.echo(f"  Description: {feed.description}")
                click.echo(f"  Sources: {len(feed.sources)}")
                click.echo(f"  Entries: {feed.entry_count}")
                click.echo(f"  Interval: {feed.fetch_interval}s")
                if feed.last_success:
                    click.echo(f"  Last Success: {feed.last_success}")

                for i, source in enumerate(feed.sources):
                    src_status = "🟢" if source.active and source.is_healthy else "🔴"
                    click.echo(f"    {src_status} [{source.priority}] {source.url}")
                    if source.error_count > 0:
                        click.echo(
                            f"        Errors: {source.error_count}, Last: {source.last_error}"
                        )
            else:
                sources_info = f"{len(feed.sources)} source(s)"
                click.echo(f"{status} {feed.name:20} {feed.entry_count:5} entries {sources_info}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("remove")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure you want to delete this feed?")
def remove_feed(name):
    """Remove an RSS feed and all its data."""
    try:
        storage = get_storage()

        if storage.delete_feed(name):
            click.echo(f"✓ Removed feed '{name}'")
        else:
            click.echo(f"Error: Feed '{name}' not found", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("enable")
@click.argument("name")
def enable_feed(name):
    """Enable a feed."""
    try:
        storage = get_storage()
        feed = storage.get_feed(name)

        if not feed:
            click.echo(f"Error: Feed '{name}' not found", err=True)
            sys.exit(1)

        feed.active = True
        if storage.update_feed(feed):
            click.echo(f"✓ Enabled feed '{name}'")
        else:
            click.echo(f"Error: Failed to enable feed '{name}'", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@feed.command("disable")
@click.argument("name")
def disable_feed(name):
    """Disable a feed."""
    try:
        storage = get_storage()
        feed = storage.get_feed(name)

        if not feed:
            click.echo(f"Error: Feed '{name}' not found", err=True)
            sys.exit(1)

        feed.active = False
        if storage.update_feed(feed):
            click.echo(f"✓ Disabled feed '{name}'")
        else:
            click.echo(f"Error: Failed to disable feed '{name}'", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def source():
    """Manage RSS sources."""


@source.command("add")
@click.argument("feed_name")
@click.argument("url")
@click.option("--priority", type=int, default=0, help="Source priority (lower = higher priority)")
def add_source(feed_name, url, priority):
    """Add a source URL to an existing feed."""
    try:
        storage = get_storage()

        # Check if feed exists
        feed = storage.get_feed(feed_name)
        if not feed:
            click.echo(f"Error: Feed '{feed_name}' not found", err=True)
            sys.exit(1)

        # Create source
        source = RSSSource(
            feed_name=feed_name,
            url=url,
            priority=priority,
        )

        if storage.create_source(source):
            click.echo(f"✓ Added source {url} to feed '{feed_name}'")
        else:
            click.echo(f"Error: Source already exists or failed to create", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@source.command("remove")
@click.argument("feed_name")
@click.argument("url")
@click.confirmation_option(prompt="Are you sure you want to remove this source?")
def remove_source(feed_name, url):
    """Remove a source URL from a feed."""
    try:
        storage = get_storage()

        if storage.delete_source(feed_name, url):
            click.echo(f"✓ Removed source {url} from feed '{feed_name}'")
        else:
            click.echo(f"Error: Source not found", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--feed", help="Specific feed to fetch")
@click.option("--concurrent", type=int, help="Max concurrent fetches")
def fetch(feed, concurrent):
    """Fetch RSS feeds."""

    async def do_fetch():
        try:
            storage = get_storage()
            config_manager = get_config_manager()

            if concurrent:
                config_manager.update(max_concurrent_fetches=concurrent)

            fetcher = FeedFetcher(config_manager.config, storage)

            try:
                if feed:
                    # Fetch specific feed
                    success, message = await fetcher.refresh_feed(feed)
                    if success:
                        click.echo(f"✓ {message}")
                    else:
                        click.echo(f"✗ {message}", err=True)
                        sys.exit(1)
                else:
                    # Fetch all active feeds
                    results = await fetcher.refresh_all_feeds()

                    success_count = 0
                    for feed_name, success, message in results:
                        status = "✓" if success else "✗"
                        click.echo(f"{status} {message}")
                        if success:
                            success_count += 1

                    click.echo(f"\n{success_count}/{len(results)} feeds updated successfully")

            finally:
                await fetcher.close()

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    asyncio.run(do_fetch())


@cli.command()
@click.option("--feed", help="Show entries for specific feed")
@click.option("--since", help='Show entries since date/time (e.g. "2023-01-01", "1 day ago")')
@click.option("--until", help="Show entries until date/time")
@click.option("--limit", type=int, default=20, help="Maximum number of entries")
@click.option("--verbose", "-v", is_flag=True, help="Show full entry details")
def entries(feed, since, until, limit, verbose):
    """Show RSS entries."""
    try:
        storage = get_storage()

        # Parse date filters
        start_time = None
        end_time = None

        if since:
            start_time = parse_date_filter(since)

        if until:
            end_time = parse_date_filter(until)

        # Get entries
        entries = storage.get_entries(
            feed_name=feed, start_time=start_time, end_time=end_time, limit=limit
        )

        if not entries:
            click.echo("No entries found")
            return

        for entry in entries:
            pub_date = entry.effective_published.strftime("%Y-%m-%d %H:%M")

            if verbose:
                click.echo(f"\n📰 {entry.title}")
                click.echo(f"   Feed: {entry.feed_name}")
                click.echo(f"   Published: {pub_date}")
                click.echo(f"   Link: {entry.link}")
                if entry.author:
                    click.echo(f"   Author: {entry.author}")
                if entry.tags:
                    click.echo(f"   Tags: {', '.join(entry.tags)}")
                click.echo(f"   Summary: {entry.get_truncated_summary(200)}")
            else:
                click.echo(f"{pub_date} | {entry.feed_name:15} | {entry.title}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--feed", help="Show stats for specific feed")
def stats(feed):
    """Show RSS statistics."""
    try:
        storage = get_storage()

        if feed:
            # Check if feed exists
            feed_obj = storage.get_feed(feed)
            if not feed_obj:
                click.echo(f"Error: Feed '{feed}' not found", err=True)
                sys.exit(1)
            
            # Show stats for specific feed
            stats = storage.get_feed_stats(feed)
            click.echo(f"📊 Statistics for feed '{feed}':")
            click.echo(f"   Total entries: {stats.total_entries}")
            click.echo(f"   Last 24h: {stats.entries_last_24h}")
            click.echo(f"   Last 7 days: {stats.entries_last_7d}")
            click.echo(f"   Active sources: {stats.active_sources}")
            click.echo(f"   Healthy sources: {stats.healthy_sources}")
            if stats.last_success:
                click.echo(f"   Last success: {stats.last_success}")
        else:
            # Show overall stats
            feeds = storage.list_feeds()
            active_feeds = [f for f in feeds if f.active]
            total_entries = sum(f.entry_count for f in feeds)

            click.echo("📊 Overall Statistics:")
            click.echo(f"   Total feeds: {len(feeds)}")
            click.echo(f"   Active feeds: {len(active_feeds)}")
            click.echo(f"   Total entries: {total_entries}")

            # Show top feeds by entry count
            if feeds:
                top_feeds = sorted(feeds, key=lambda f: f.entry_count, reverse=True)[:5]
                click.echo("\n   Top feeds by entry count:")
                for feed in top_feeds:
                    status = "🟢" if feed.active else "🔴"
                    click.echo(f"     {status} {feed.name}: {feed.entry_count} entries")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--days", type=int, default=90, help="Remove entries older than N days")
@click.confirmation_option(prompt="Are you sure you want to delete old entries?")
def cleanup(days):
    """Clean up old RSS entries."""
    try:
        storage = get_storage()

        count = storage.cleanup_old_entries(days)
        click.echo(f"✓ Removed {count} old entries (older than {days} days)")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def serve():
    """Start MCP server."""


@serve.command("stdio")
def serve_stdio():
    """Start MCP server in stdio mode with multi-user support."""
    from .fastmcp_multiuser import run_multiuser_fastmcp_stdio

    try:
        asyncio.run(run_multiuser_fastmcp_stdio())
    except KeyboardInterrupt:
        click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Server error: {e}", err=True)
        sys.exit(1)


@serve.command("http")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", type=int, default=8080, help="Port to bind to")
def serve_http(host, port):
    """Start MCP server in HTTP mode with multi-user support."""
    from .fastmcp_multiuser import run_multiuser_fastmcp_server
    
    try:
        click.echo(f"Starting RSS MCP server in HTTP mode on {host}:{port}")
        asyncio.run(run_multiuser_fastmcp_server(host, port))
    except KeyboardInterrupt:
        click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Server error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--key", help="Configuration key to get/set")
@click.option("--value", help="Value to set (omit to get current value)")
def config(key, value):
    """Get or set configuration values."""
    try:
        config_manager = get_config_manager()

        if not key:
            # Show all config
            click.echo("Current configuration:")
            for k, v in config_manager.config.to_dict().items():
                click.echo(f"  {k}: {v}")
        elif not value:
            # Get specific key
            if hasattr(config_manager.config, key):
                click.echo(f"{key}: {getattr(config_manager.config, key)}")
            else:
                click.echo(f"Error: Unknown config key '{key}'", err=True)
                sys.exit(1)
        else:
            # Set key=value
            try:
                # Try to convert to appropriate type
                current_val = getattr(config_manager.config, key, None)
                if isinstance(current_val, int):
                    value = int(value)
                elif isinstance(current_val, bool):
                    value = value.lower() in ("true", "1", "yes", "on")

                config_manager.update(**{key: value})
                click.echo(f"✓ Set {key} = {value}")

            except ValueError as e:
                click.echo(f"Error: Invalid value for {key}: {e}", err=True)
                sys.exit(1)
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def parse_date_filter(date_str: str) -> datetime:
    """Parse date filter string."""
    date_str = date_str.strip().lower()

    # Handle relative dates
    if "ago" in date_str:
        parts = date_str.replace("ago", "").strip().split()
        if len(parts) == 2:
            try:
                num = int(parts[0])
                unit = parts[1].rstrip("s")  # Remove plural 's'

                now = datetime.now()
                if unit in ("day", "days"):
                    return now - timedelta(days=num)
                elif unit in ("hour", "hours"):
                    return now - timedelta(hours=num)
                elif unit in ("week", "weeks"):
                    return now - timedelta(weeks=num)
                elif unit in ("month", "months"):
                    return now - timedelta(days=num * 30)
            except ValueError:
                pass

    # Parse absolute date
    try:
        return date_parser.parse(date_str)
    except Exception:
        raise ValueError(f"Cannot parse date: {date_str}")


if __name__ == "__main__":
    cli()

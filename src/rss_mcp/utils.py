"""Utility functions for RSS MCP server."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(level=log_level, handlers=handlers, force=True)


def validate_url(url: str) -> bool:
    """Validate if a URL is well-formed."""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def safe_filename(text: str, max_length: int = 100) -> str:
    """Create a safe filename from text."""
    # Remove/replace unsafe characters
    safe_chars = []
    for char in text:
        if char.isalnum() or char in ("-", "_", ".", " "):
            safe_chars.append(char)
        else:
            safe_chars.append("_")

    filename = "".join(safe_chars).strip()

    # Replace multiple spaces/underscores with single ones
    while "  " in filename:
        filename = filename.replace("  ", " ")
    while "__" in filename:
        filename = filename.replace("__", "_")

    # Limit length
    if len(filename) > max_length:
        filename = filename[:max_length].rsplit(" ", 1)[0]

    return filename or "untitled"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_size(bytes_count: int) -> str:
    """Format byte count to human readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024:
            return f"{bytes_count:.1f}{unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f}TB"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length with suffix."""
    if len(text) <= max_length:
        return text

    truncated = text[: max_length - len(suffix)]

    # Try to break at word boundary
    if " " in truncated:
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.7:  # Don't break too early
            truncated = truncated[:last_space]

    return truncated + suffix


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return url


def is_recent(dt: Optional[datetime], hours: int = 24) -> bool:
    """Check if datetime is within the last N hours."""
    if not dt:
        return False

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    return delta.total_seconds() < hours * 3600


def normalize_feed_url(url: str) -> str:
    """Normalize feed URL for consistent comparison."""
    # Remove trailing slashes, convert to lowercase
    normalized = url.strip().lower()
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized

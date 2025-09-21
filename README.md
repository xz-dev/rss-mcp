# RSS MCP Server

A comprehensive RSS feed management system with MCP (Model Context Protocol) support, providing both CLI management and AI integration capabilities.

## Features

- **Multiple Sources per Feed**: Each RSS feed can have multiple source URLs for automatic failover
- **MCP Integration**: Full MCP protocol support for AI assistants with both stdio and HTTP transports
- **CLI Management**: Complete command-line interface for feed management
- **Auto-reload Configuration**: Configuration changes are automatically detected and applied
- **Time-based Queries**: Efficient filtering of RSS entries by publication date
- **Pagination Support**: Handle large datasets with cursor-based pagination
- **Comprehensive Testing**: Full pytest test suite with 80%+ code coverage

## Installation

```bash
# Install with pip
pip install rss-mcp

# Or install from source
git clone https://github.com/yourusername/rss-mcp.git
cd rss-mcp
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

## Quick Start

### 1. Add your first RSS feed

```bash
rss-mcp feed add "tech-news" "https://feeds.feedburner.com/TechCrunch" \
    --title "TechCrunch" \
    --description "Latest technology news"
```

### 2. Add backup sources for reliability

```bash
rss-mcp source add "tech-news" "https://techcrunch.com/feed/" --priority 1
```

### 3. Fetch the latest entries

```bash
rss-mcp fetch
```

### 4. View recent entries

```bash
rss-mcp entries --since "1 day ago" --limit 10
```

### 5. Start MCP server for AI integration

```bash
# For stdio transport (recommended for most MCP clients)
rss-mcp serve stdio

# For HTTP transport
rss-mcp serve http --host localhost --port 8080
```

## CLI Commands

### Feed Management

```bash
# Add a new feed
rss-mcp feed add <name> <url> [--title TITLE] [--description DESC] [--interval SECONDS]

# List all feeds
rss-mcp feed list [--active-only] [--verbose]

# Remove a feed
rss-mcp feed remove <name>

# Enable/disable feeds
rss-mcp feed enable <name>
rss-mcp feed disable <name>
```

### Source Management

```bash
# Add a backup source to existing feed
rss-mcp source add <feed_name> <url> [--priority N]

# Remove a source
rss-mcp source remove <feed_name> <url>
```

### Content Operations

```bash
# Fetch new entries
rss-mcp fetch [--feed FEED_NAME] [--concurrent N]

# View entries
rss-mcp entries [--feed FEED] [--since DATE] [--until DATE] [--limit N] [--verbose]

# View statistics
rss-mcp stats [--feed FEED_NAME]

# Clean up old entries
rss-mcp cleanup [--days N]
```

### Server Operations

```bash
# Start MCP server (stdio transport)
rss-mcp serve stdio

# Start MCP server (HTTP transport)
rss-mcp serve http [--host HOST] [--port PORT]
```

### Configuration

```bash
# View current configuration
rss-mcp config

# Get specific setting
rss-mcp config --key database_path

# Update setting
rss-mcp config --key http_port --value 9000
```

## MCP Integration

The RSS MCP server provides the following tools for AI assistants:

### Available Tools

1. **`list_feeds`** - List all RSS feeds with their sources and status
2. **`add_feed`** - Add a new RSS feed with source URLs
3. **`remove_feed`** - Remove an RSS feed and all its data
4. **`add_source`** - Add a source URL to an existing feed
5. **`remove_source`** - Remove a source URL from a feed
6. **`get_entries`** - Get RSS entries with optional filtering and pagination
7. **`get_entry_summary`** - Get a summary of a specific RSS entry
8. **`refresh_feeds`** - Refresh RSS feeds to fetch new entries
9. **`get_feed_stats`** - Get statistics for RSS feeds

### Example MCP Tool Usage

```python
# List all active feeds
await client.call_tool("list_feeds", {"active_only": True})

# Add a new feed with multiple sources
await client.call_tool("add_feed", {
    "name": "python-news",
    "urls": ["https://realpython.com/atom.xml", "https://planet.python.org/rss20.xml"],
    "title": "Python News"
})

# Get recent entries with pagination
await client.call_tool("get_entries", {
    "start_time": "1 week ago",
    "page": 1,
    "page_size": 20
})

# Refresh all feeds
await client.call_tool("refresh_feeds", {})
```

## Configuration

Configuration is stored in JSON format and supports auto-reload. Default location:

- Linux: `~/.config/rss-mcp/config.json`
- macOS: `~/Library/Application Support/rss-mcp/config.json`
- Windows: `%APPDATA%/rss-mcp/config.json`

### Configuration Options

```json
{
  "cache_path": "~/.cache/rss-mcp",
  "default_fetch_interval": 3600,
  "max_entries_per_feed": 1000,
  "cleanup_days": 90,
  "http_host": "localhost",
  "http_port": 8080,
  "request_timeout": 30,
  "max_retries": 3,
  "retry_delay": 60,
  "user_agent": "RSS-MCP-Server/1.0",
  "max_concurrent_fetches": 10,
  "rate_limit_requests": 100,
  "rate_limit_period": 3600,
  "log_level": "INFO",
  "log_file": null
}
```

## File Storage Structure

The system uses JSON files for storage with the following structure:

```
~/.cache/rss-mcp/
├── feeds/              # Feed definitions
│   ├── feed1.json
│   ├── feed2.json
│   └── ...
├── sources/            # Source URLs for feeds
│   ├── {source-id}.json
│   └── ...
└── entries/            # RSS entries organized by feed
    ├── feed1/
    │   ├── {entry-id}.json
    │   └── ...
    ├── feed2/
    │   ├── {entry-id}.json
    │   └── ...
    └── ...
```

### Feed Files (`~/.cache/rss-mcp/feeds/{name}.json`)
```json
{
  "name": "tech-news",
  "title": "Technology News", 
  "description": "Latest tech updates",
  "link": "https://example.com",
  "active": true,
  "fetch_interval": 3600,
  "last_fetch": "2024-01-15T10:30:00Z",
  "last_success": "2024-01-15T10:30:00Z",
  "entry_count": 150,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### Source Files (`~/.cache/rss-mcp/sources/{uuid}.json`)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "feed_name": "tech-news",
  "url": "https://example.com/rss.xml",
  "priority": 0,
  "active": true,
  "last_fetch": "2024-01-15T10:30:00Z", 
  "last_success": "2024-01-15T10:30:00Z",
  "error_count": 0,
  "last_error": null,
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Entry Files (`~/.cache/rss-mcp/entries/{feed_name}/{uuid}.json`)
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "feed_name": "tech-news",
  "source_url": "https://example.com/rss.xml",
  "guid": "article-123",
  "title": "Breaking: New Tech Announcement",
  "link": "https://example.com/article-123",
  "description": "Summary of the article...",
  "content": "Full article content...",
  "author": "John Doe",
  "published": "2024-01-15T09:00:00Z",
  "updated": "2024-01-15T09:30:00Z", 
  "tags": ["technology", "news"],
  "enclosures": [],
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Development

### Setup Development Environment

```bash
git clone https://github.com/yourusername/rss-mcp.git
cd rss-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

The project includes both unit tests and comprehensive integration tests using the MCP Inspector CLI.

#### Quick Test Commands (Pytest-Native)

```bash
# Fast unit tests
pytest --test-type=unit

# Integration tests (requires Node.js and MCP Inspector)
pytest --test-type=integration

# Specific integration test types
pytest --test-type=stdio    # Test stdio transport only
pytest --test-type=http     # Test HTTP transport only  
pytest --test-type=env      # Test environment validation

# All tests
pytest --test-type=all

# With coverage reporting
pytest --test-type=all --cov=rss_mcp --cov-report=html

# Install dependencies and run tests
pytest --test-type=integration --install-deps --setup-mcp

# Environment check and cleanup
pytest --test-type=unit --check-env --clean
```


#### Manual Test Commands

```bash
# Unit tests only
pytest tests/ -m "not integration" -v

# Integration tests only
pytest tests/integration/ -v

# All tests
pytest tests/ -v

# With coverage
pytest --cov=rss_mcp --cov-report=html tests/
```

#### Pytest Features and Options

The project uses a custom pytest plugin (in `conftest.py`) that adds powerful testing features:

```bash
# Custom test selection
pytest --test-type=unit                    # Only unit tests
pytest --test-type=integration             # Only integration tests
pytest --test-type=stdio                   # Only stdio transport tests
pytest --test-type=http                    # Only HTTP transport tests
pytest --test-type=env                     # Environment validation tests
pytest --test-type=all                     # All tests

# Environment and setup
pytest --check-env                         # Check environment before tests
pytest --install-deps                      # Install Python dependencies
pytest --setup-mcp                        # Install MCP Inspector
pytest --clean                            # Clean test artifacts
pytest --no-env-check                     # Skip auto environment checks

# Combine options
pytest --test-type=integration --setup-mcp --clean --check-env

# Standard pytest options still work
pytest --test-type=all -x                 # Stop on first failure
pytest --test-type=unit -k "test_model"   # Run specific test pattern
pytest --test-type=integration --tb=long  # Detailed traceback
pytest --test-type=all --maxfail=3        # Stop after 3 failures
```

#### Integration Test Requirements

Integration tests require additional setup:

1. **Node.js and npm** (for MCP Inspector)
2. **MCP Inspector CLI** package  
3. **Network connectivity** (for RSS feed testing)

```bash
# Automatic setup
pytest --test-type=integration --install-deps --setup-mcp

# Manual setup
npm install -g @modelcontextprotocol/inspector
pip install -e ".[dev]"

# Check environment
pytest --check-env
```

#### Integration Test Features

The integration tests provide comprehensive real-world testing:

- **MCP Inspector CLI Integration**: Tests actual MCP protocol communication
- **Both Transport Types**: Stdio (primary) and HTTP transport testing  
- **Real RSS Feeds**: Uses stable RSSHub feeds for realistic testing
- **End-to-End Workflows**: CLI → MCP → Database consistency testing
- **Error Handling**: Network failures, invalid inputs, resource limits
- **Performance Testing**: Concurrent operations, large datasets
- **Failover Testing**: Multiple source URLs with automatic failover

#### Test Organization

```
tests/
├── unit tests/              # Fast, isolated tests
│   ├── test_models.py       # Data model validation
│   ├── test_storage.py      # Database operations
│   ├── test_config.py       # Configuration management
│   ├── test_feed_manager.py # RSS fetching logic
│   ├── test_server.py       # MCP server logic
│   └── test_cli.py          # CLI command testing
└── integration/             # Real-world integration tests
    ├── test_environment.py  # Environment validation
    ├── test_mcp_stdio_integration.py  # Stdio transport tests
    ├── test_mcp_http_integration.py   # HTTP transport tests
    ├── conftest.py          # Integration test fixtures
    └── utils.py             # Integration test utilities
```

### Project Structure

```
rss-mcp/
   src/rss_mcp/
      __init__.py          # Entry point
      cli.py              # CLI commands
      server.py           # MCP server implementation
      models.py           # Data models
      storage.py          # Database layer
      feed_manager.py     # RSS fetching logic
      config.py           # Configuration management
      utils.py            # Utility functions
   tests/                  # Test suite
   pyproject.toml          # Project configuration
   README.md              # This file
```

## Error Handling

The system includes comprehensive error handling:

- **Network Errors**: Automatic retry with exponential backoff
- **Feed Parse Errors**: Graceful handling of malformed RSS
- **Database Errors**: Transaction rollback and recovery
- **Source Failover**: Automatic switching to backup sources
- **Rate Limiting**: Respects server rate limits

## Performance

- **Concurrent Fetching**: Configurable concurrency limits
- **Database Indexing**: Optimized queries for large datasets
- **Memory Efficient**: Streaming RSS parsing
- **Caching**: Smart caching to avoid duplicate fetches

## Security

- **Input Validation**: All user inputs are validated
- **SQL Injection Prevention**: Parameterized queries
- **URL Validation**: Malicious URLs are rejected
- **No Code Execution**: Safe RSS parsing only

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/rss-mcp/issues)
- **Documentation**: [Wiki](https://github.com/yourusername/rss-mcp/wiki)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/rss-mcp/discussions)

## Changelog

### v1.0.0 (Initial Release)
- Complete MCP server implementation with stdio and HTTP transports
- Full CLI interface with all management commands
- Multiple source failover support
- Auto-reload configuration
- Comprehensive test suite
- Time-based entry filtering
- Pagination support
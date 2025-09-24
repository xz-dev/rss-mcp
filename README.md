# 📰 RSS MCP Server

> 🚀 A powerful RSS feed management system with Model Context Protocol (MCP) integration, enabling AI assistants to intelligently analyze, aggregate, and track RSS content evolution.

## ✨ Features

- 🔄 **Multi-Source Feeds**: Multiple RSS sources per feed with automatic failover
- 🤖 **MCP Integration**: Full Model Context Protocol support (stdio, HTTP, SSE)
- 📊 **Content Evolution Tracking**: AI can analyze how news stories develop over time
- ⚡ **Intelligent Caching**: Efficient content storage with deduplication
- 🔍 **Time-based Filtering**: Query entries by publication date ranges
- 👥 **Multi-user Support**: Isolated configurations and data per user
- 🐳 **Docker Ready**: Containerized deployment support
- 🛠️ **Rich CLI**: Comprehensive command-line interface

## 🚀 Quick Start

### Installation

```bash
# From PyPI
pip install rss-mcp

# From source
git clone https://github.com/xz-dev/rss-mcp.git
cd rss-mcp
uv sync
```

### Basic Usage

```bash
# Add RSS feed
rss-mcp feed add "tech-news" "https://feeds.feedburner.com/TechCrunch" \
  --title "TechCrunch" --description "Latest tech news"

# Fetch entries
rss-mcp fetch

# View recent entries
rss-mcp entries --since "1 day ago" --limit 10

# Start MCP server
rss-mcp serve stdio
```

## 🔌 MCP Configuration

### stdio Mode (Recommended)
For Claude Desktop, Continue.dev, and other local MCP clients:

```json
{
  "mcpServers": {
    "rss-mcp": {
      "command": "rss-mcp",
      "args": ["serve", "stdio"],
      "env": {
        "RSS_MCP_USER": "your-username"
      }
    }
  }
}
```

### HTTP Mode
For remote deployment and web-based clients:

```json
{
  "mcpServers": {
    "rss-mcp": {
      "type": "http",
      "url": "https://your-server.com/mcp",
      "headers": {
        "X-User-ID": "your-username"
      }
    }
  }
}
```

### SSE Mode (Deprecated)
For legacy Server-Sent Events transport:

```json
{
  "mcpServers": {
    "rss-mcp": {
      "type": "sse",
      "url": "https://your-server.com/sse",
      "headers": {
        "X-User-ID": "your-username"
      }
    }
  }
}
```

## 🤖 MCP Tools

The server provides these tools for AI assistants:

| Tool | Description | Usage |
|------|-------------|-------|
| `list_feeds` | List all configured RSS feeds | Get feed overview |
| `get_entries` | Retrieve RSS entries with filtering | Analyze recent content |
| `add_feed` | Create new RSS feed | Setup new sources |
| `add_source` | Add backup URL to feed | Improve reliability |
| `remove_feed` | Delete feed and entries | Clean up |
| `remove_source` | Remove source URL | Maintenance |
| `refresh_feeds` | Fetch latest entries | Update content |
| `get_feed_stats` | Get feed statistics | Monitor activity |

### Example AI Interactions

```
User: "Show me tech news from the last 6 hours"
AI: Uses get_entries with since parameter to fetch recent entries

User: "Track how this breaking news story has evolved"
AI: Uses get_entries to find multiple versions of the same story by GUID

User: "Add a backup source for my news feed"
AI: Uses add_source to improve feed reliability
```

## 🛠️ CLI Reference

### Feed Management
```bash
# Feed operations
rss-mcp feed add <name> <url> [--title TITLE] [--description DESC]
rss-mcp feed list [--active-only] [--verbose]
rss-mcp feed remove <name>
rss-mcp feed enable/disable <name>

# Source operations  
rss-mcp source add <feed_name> <url> [--priority N]
rss-mcp source remove <feed_name> <url>

# Content operations
rss-mcp fetch [--feed FEED] [--force]
rss-mcp entries [--feed FEED] [--since TIME] [--limit N]
rss-mcp stats [--feed FEED]
```

### Server Modes
```bash
# stdio mode (for local MCP clients)
rss-mcp serve stdio

# HTTP mode (for remote access)
rss-mcp serve http --host 0.0.0.0 --port 8080

# SSE mode (deprecated)
rss-mcp serve sse --host 0.0.0.0 --port 8080
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RSS_MCP_CONFIG_DIR` | Configuration directory | `~/.config/rss-mcp` |
| `RSS_MCP_CACHE_DIR` | Cache directory | `~/.cache/rss-mcp` |
| `RSS_MCP_USER` | Default user ID | `default` |
| `RSS_MCP_REQUIRE_USER_ID` | Require user ID for access | `false` |

### Multi-user Setup

For multi-tenant deployments:

```bash
# Enable user ID requirement
export RSS_MCP_REQUIRE_USER_ID=1

# Start server (users must provide X-User-ID header)
rss-mcp serve http --host 0.0.0.0 --port 8080
```

## 🐳 Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install .

# Set environment variables
ENV RSS_MCP_CONFIG_DIR=/app/config
ENV RSS_MCP_CACHE_DIR=/app/cache
ENV RSS_MCP_REQUIRE_USER_ID=1

EXPOSE 8080
CMD ["rss-mcp", "serve", "http", "--host", "0.0.0.0", "--port", "8080"]
```

```bash
# Build and run
docker build -t rss-mcp .
docker run -p 8080:8080 -v ./config:/app/config -v ./cache:/app/cache rss-mcp
```

## 🎯 Use Cases

### News Analysis
- **Story Evolution**: Track how breaking news develops over time
- **Source Comparison**: Compare reporting across different outlets
- **Trend Detection**: Identify emerging topics and patterns

### Content Aggregation
- **Multi-source Feeds**: Combine multiple RSS sources for comprehensive coverage
- **Intelligent Deduplication**: Avoid duplicate content across sources
- **Reliability**: Automatic failover when sources are unavailable

### AI Integration
- **Content Summarization**: Let AI analyze and summarize RSS content
- **Semantic Search**: Find relevant articles based on meaning, not just keywords
- **Automated Insights**: Generate reports on content trends and patterns

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   RSS Sources   │    │  Configuration  │
│  (Claude, etc.) │    │  (Web Feeds)    │    │     Files       │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │ MCP Protocol         │ HTTP Fetch           │ JSON
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RSS MCP Server                               │
├─────────────────┬─────────────────┬─────────────────────────────┤
│  FastMCP Core   │  Feed Manager   │      Cache Storage          │
│  (Tools/Proto)  │  (RSS Parsing)  │   (Entries/Deduplication)   │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/xz-dev/rss-mcp.git
cd rss-mcp
uv sync --dev

# Run tests
uv run pytest

# Format code
uv run black src tests
uv run isort src tests
```

## 📝 License

This project is licensed under the BSD 2-Clause License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- Built with [FastMCP](https://github.com/stpmax/fastmcp) for MCP protocol support
- Uses [feedparser](https://feedparser.readthedocs.io/) for RSS parsing
- Powered by [FastAPI](https://fastapi.tiangolo.com/) for HTTP transport

---

<div align="center">
<strong>Made with ❤️ for the AI community</strong><br>
<sub>Enabling AI assistants to understand and analyze the world's RSS feeds</sub>
</div>
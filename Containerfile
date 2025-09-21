# Multi-stage build for RSS MCP Server
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml LICENSE README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Final runtime stage
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash rssuser && \
    mkdir -p /app/config /app/cache && \
    chown -R rssuser:rssuser /app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/rss-mcp /usr/local/bin/rss-mcp

# Create default config file
RUN echo '{\n\
  "default_fetch_interval": 3600,\n\
  "max_entries_per_feed": 1000,\n\
  "cleanup_days": 30,\n\
  "request_timeout": 30,\n\
  "max_retries": 3,\n\
  "max_concurrent_fetches": 5,\n\
  "http_host": "0.0.0.0",\n\
  "http_port": 8080,\n\
  "log_level": "INFO"\n\
}' > /app/config/config.json && \
    chown rssuser:rssuser /app/config/config.json

USER rssuser

# Environment variables
ENV RSS_MCP_CONFIG=/app/config/config.json \
    RSS_MCP_CACHE=/app/cache \
    PYTHONUNBUFFERED=1

# Expose HTTP port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/').read()" || exit 1

# Run HTTP server
CMD ["rss-mcp", "serve", "http", "--host", "0.0.0.0", "--port", "8080"]
# RSS MCP Server Container
FROM python:3.13-slim

# Create application directories
RUN mkdir -p /app/config /app/cache

WORKDIR /app

# Copy project files
COPY pyproject.toml LICENSE README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Config and cache directories will be created at runtime as needed

# Environment variables
# RSS_MCP_CONFIG_DIR: Base directory for per-user configs (will be /app/config/{user_id}/)
# RSS_MCP_CACHE_DIR: Shared cache directory for all users
# Note: RSS_MCP_CONFIG is intentionally not set to enable per-user configs
ENV RSS_MCP_CONFIG_DIR=/app/config \
    RSS_MCP_CACHE_DIR=/app/cache \
    PYTHONUNBUFFERED=1

# Expose HTTP port
EXPOSE 8080

# Run HTTP server
CMD ["rss-mcp", "serve", "http", "--host", "0.0.0.0", "--port", "8080"]

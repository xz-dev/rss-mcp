"""Integration test fixtures and utilities."""

import asyncio
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import pytest
import psutil
from pytest_subprocess import FakeProcess
from unittest.mock import patch

from rss_mcp.config import RSSConfig


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for integration tests with environment isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / "config.json"
        cache_path = tmpdir_path / "cache"
        
        # Set environment variables to use temporary directories
        with patch.dict('os.environ', {
            'RSS_MCP_CONFIG_DIR': str(tmpdir_path / "config"),
            'RSS_MCP_CACHE_DIR': str(cache_path)
        }):
            yield tmpdir_path


@pytest.fixture
def integration_config(temp_dir):
    """Create integration test configuration."""
    # The cache_path will be set automatically via RSS_MCP_CACHE_DIR env var
    config = RSSConfig(
        default_fetch_interval=3600,
        max_entries_per_feed=100,
        cleanup_days=30,
        request_timeout=10,
        max_retries=2,
        max_concurrent_fetches=5,
        http_host="127.0.0.1",
        http_port=0,  # Let the system choose a free port
        log_level="DEBUG",
    )
    
    # Save config to temp directory
    config_path = temp_dir / "config.json"
    with open(config_path, 'w') as f:
        json.dump(config.to_dict(), f, indent=2)
    
    return config, config_path


@pytest.fixture
def test_feeds():
    """Test RSS feed URLs from RSSHub."""
    return {
        "github-trending": {
            "name": "github-trending",
            "title": "GitHub Trending",
            "urls": ["https://rsshub.app/github/trending/daily"],
            "backup_urls": ["https://rsshub.app/github/trending/weekly"],
        },
        "tech-news": {
            "name": "tech-news", 
            "title": "36kr News",
            "urls": ["https://rsshub.app/36kr/newsflashes"],
            "backup_urls": ["https://rsshub.app/36kr/latest"],
        },
        "zhihu-hot": {
            "name": "zhihu-hot",
            "title": "Zhihu Hot Topics",
            "urls": ["https://rsshub.app/zhihu/hot"],
            "backup_urls": [],
        }
    }


class ServerProcess:
    """Manages RSS MCP server process lifecycle."""
    
    def __init__(self, config_path: Path, mode: str = "stdio", host: str = "127.0.0.1", port: int = 8080):
        """Initialize server process manager."""
        self.config_path = config_path
        self.mode = mode
        self.host = host
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.env = os.environ.copy()
        
    def start(self) -> Tuple[str, int]:
        """Start the MCP server process."""
        cmd = ["python", "-m", "rss_mcp"]
        
        if self.mode == "stdio":
            cmd.extend(["serve", "stdio"])
        elif self.mode == "http":
            cmd.extend(["serve", "http", "--host", self.host, "--port", str(self.port)])
        else:
            raise ValueError(f"Unsupported mode: {self.mode}")
        
        # Config path is already set via the temp_dir fixture's environment patch
        # But we'll set it again to ensure it matches our config file
        self.env["RSS_MCP_CONFIG_DIR"] = str(self.config_path.parent / "config")
        self.env["RSS_MCP_CACHE_DIR"] = str(self.config_path.parent / "cache")
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            text=True,
            bufsize=0,  # Unbuffered for real-time interaction
        )
        
        # For HTTP mode, wait for server to start and get actual port
        if self.mode == "http":
            actual_port = self._wait_for_http_server()
            return self.host, actual_port
        else:
            # For stdio mode, give it a moment to initialize
            time.sleep(1)
            return "stdio", 0
    
    def _wait_for_http_server(self, timeout: int = 10) -> int:
        """Wait for HTTP server to start and return actual port."""
        import requests
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.process and self.process.poll() is None:  # Process still running
                try:
                    # Try to connect to the server
                    response = requests.get(f"http://{self.host}:{self.port}/", timeout=1)
                    if response.status_code == 200:
                        return self.port
                except (requests.ConnectionError, requests.Timeout):
                    pass
            time.sleep(0.5)
        
        raise TimeoutError(f"HTTP server failed to start within {timeout} seconds")
    
    def stop(self):
        """Stop the MCP server process."""
        if self.process:
            try:
                # Try graceful shutdown first
                self.process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if necessary
                    self.process.kill()
                    self.process.wait()
                    
            except ProcessLookupError:
                # Process already terminated
                pass
            
            self.process = None
    
    def is_running(self) -> bool:
        """Check if server process is running."""
        if not self.process:
            return False
        return self.process.poll() is None
    
    def send_input(self, data: str):
        """Send input to stdio server."""
        if self.mode == "stdio" and self.process and self.process.stdin:
            self.process.stdin.write(data)
            self.process.stdin.flush()
    
    def read_output(self, timeout: float = 1.0) -> str:
        """Read output from stdio server."""
        if self.mode == "stdio" and self.process and self.process.stdout:
            # This is a simplified version - in practice you'd want non-blocking I/O
            import select
            
            if select.select([self.process.stdout], [], [], timeout)[0]:
                return self.process.stdout.readline()
        return ""
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


@pytest.fixture
def server_process_stdio(integration_config):
    """Create stdio server process fixture."""
    config, config_path = integration_config
    server = ServerProcess(config_path, mode="stdio")
    
    try:
        server.start()
        yield server
    finally:
        server.stop()


@pytest.fixture
def server_process_http(integration_config):
    """Create HTTP server process fixture."""
    config, config_path = integration_config
    
    # Find a free port
    import socket
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    server = ServerProcess(config_path, mode="http", port=port)
    
    try:
        host, actual_port = server.start()
        server.host = host
        server.port = actual_port
        yield server
    finally:
        server.stop()

@pytest.fixture
def cli_wrapper(temp_dir, integration_config):
    """Create CLI wrapper for RSS MCP commands."""
    config, config_path = integration_config
    
    class CLIWrapper:
        def __init__(self, config_path: Path):
            self.config_path = config_path
            self.env = os.environ.copy()
            self.env["RSS_MCP_CONFIG_DIR"] = str(config_path.parent / "config")
            self.env["RSS_MCP_CACHE_DIR"] = str(config_path.parent / "cache")
        
        def run_command(self, cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
            """Run RSS MCP CLI command."""
            full_cmd = ["python", "-m", "rss_mcp"] + cmd
            
            try:
                result = subprocess.run(
                    full_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=self.env,
                    check=False
                )
                return result
            except subprocess.TimeoutExpired as e:
                raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(full_cmd)}") from e
        
        def add_feed(self, name: str, url: str, **kwargs) -> subprocess.CompletedProcess:
            """Add RSS feed via CLI."""
            cmd = ["feed", "add", name, url]
            for key, value in kwargs.items():
                cmd.extend([f"--{key}", str(value)])
            return self.run_command(cmd)
        
        def list_feeds(self, **kwargs) -> subprocess.CompletedProcess:
            """List RSS feeds via CLI."""
            cmd = ["feed", "list"]
            for key, value in kwargs.items():
                if value is True:
                    cmd.append(f"--{key}")
                else:
                    cmd.extend([f"--{key}", str(value)])
            return self.run_command(cmd)
        
        def add_source(self, feed_name: str, url: str, priority: int = 0) -> subprocess.CompletedProcess:
            """Add source to feed via CLI."""
            return self.run_command(["source", "add", feed_name, url, "--priority", str(priority)])
        
        def fetch_feeds(self, feed_name: str = None) -> subprocess.CompletedProcess:
            """Fetch feeds via CLI."""
            cmd = ["fetch"]
            if feed_name:
                cmd.extend(["--feed", feed_name])
            return self.run_command(cmd)
        
        def get_entries(self, **kwargs) -> subprocess.CompletedProcess:
            """Get entries via CLI."""
            cmd = ["entries"]
            for key, value in kwargs.items():
                if value is True:
                    cmd.append(f"--{key}")
                else:
                    cmd.extend([f"--{key}", str(value)])
            return self.run_command(cmd)
        
        def get_stats(self, feed_name: str = None) -> subprocess.CompletedProcess:
            """Get stats via CLI."""
            cmd = ["stats"]
            if feed_name:
                cmd.extend(["--feed", feed_name])
            return self.run_command(cmd)
    
    return CLIWrapper(config_path)


# Helper functions for assertions
def assert_successful_command(result: subprocess.CompletedProcess, expected_text: str = None):
    """Assert that a command completed successfully."""
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    if expected_text:
        assert expected_text in result.stdout, f"Expected '{expected_text}' not found in output: {result.stdout}"


def assert_failed_command(result: subprocess.CompletedProcess, expected_error: str = None):
    """Assert that a command failed as expected."""
    assert result.returncode != 0, f"Command unexpectedly succeeded: {result.stdout}"
    if expected_error:
        error_output = result.stderr or result.stdout
        assert expected_error in error_output, f"Expected error '{expected_error}' not found in: {error_output}"


def assert_json_response(response: Dict, required_keys: List[str] = None):
    """Assert that response is valid JSON with required keys."""
    assert isinstance(response, dict), f"Response is not a dict: {response}"
    
    if required_keys:
        for key in required_keys:
            assert key in response, f"Required key '{key}' not found in response: {response}"

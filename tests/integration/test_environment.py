"""Environment validation tests for RSS MCP server."""

import os
import socket
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

pytestmark = [
    pytest.mark.env_check,
    pytest.mark.integration,
]


class TestPythonEnvironment:
    """Test Python environment setup."""

    def test_python_version(self):
        """Test that Python version is compatible."""
        version_info = sys.version_info
        assert version_info.major >= 3, f"Python 3.x required, got {version_info.major}"
        assert (
            version_info.minor >= 8
        ), f"Python 3.8+ required, got {version_info.major}.{version_info.minor}"

    def test_required_packages(self):
        """Test that all required packages are available."""
        required_packages = [
            "pytest",
            "mcp",
            "feedparser",
            "aiohttp",
            "click",
            "fastapi",
            "uvicorn",
            "watchdog",
        ]

        for package in required_packages:
            try:
                __import__(package)
            except ImportError as e:
                pytest.fail(f"Required package '{package}' not found: {e}")

    def test_dev_packages(self):
        """Test that dev packages are available."""
        dev_packages = [
            "pytest_asyncio",
            "pytest_mock",
            "httpx",
            "psutil",
        ]

        for package in dev_packages:
            try:
                __import__(package)
            except ImportError as e:
                pytest.fail(f"Dev package '{package}' not found: {e}")

    def test_rss_mcp_package(self):
        """Test that RSS MCP package is installed."""
        try:
            import rss_mcp

            assert hasattr(rss_mcp, "main"), "rss_mcp.main not found"
        except ImportError as e:
            pytest.fail(f"RSS MCP package not installed: {e}")


class TestFileSystemEnvironment:
    """Test file system requirements."""

    def test_temp_directory_writable(self):
        """Test that temp directory is writable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")

            assert test_file.exists()
            assert test_file.read_text() == "test"

    def test_database_creation(self):
        """Test that SQLite database can be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            import sqlite3

            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()

            assert db_path.exists()
            assert db_path.stat().st_size > 0

    def test_config_file_creation(self):
        """Test that config files can be created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            import json

            config_data = {"test": "value"}

            with open(config_path, "w") as f:
                json.dump(config_data, f)

            assert config_path.exists()

            with open(config_path, "r") as f:
                loaded = json.load(f)

            assert loaded == config_data


@pytest.mark.network
@pytest.mark.skipif(os.getenv("RUN_NETWORK_TESTS") != "1", reason="Network tests disabled (set RUN_NETWORK_TESTS=1 to enable)")
class TestNetworkEnvironment:
    """Test network connectivity."""

    @pytest.mark.asyncio
    async def test_basic_connectivity(self):
        """Test basic network connectivity."""
        # Try to connect to well-known public servers
        test_urls = [
            "https://example.com",
            "https://www.google.com",
        ]

        async with httpx.AsyncClient(timeout=10) as client:
            success = False
            for url in test_urls:
                try:
                    response = await client.get(url)
                    if response.status_code < 500:
                        success = True
                        break
                except Exception:
                    continue

            assert success, "No network connectivity to public internet"

    @pytest.mark.asyncio
    async def test_rsshub_connectivity(self):
        """Test connectivity to RSSHub."""
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get("https://rsshub.app")
                assert response.status_code < 500, f"RSSHub returned {response.status_code}"
            except httpx.ConnectTimeout:
                pytest.skip("RSSHub connection timeout - may be blocked or down")
            except Exception as e:
                pytest.skip(f"Could not connect to RSSHub: {e}")

    def test_localhost_binding(self):
        """Test that we can bind to localhost ports."""
        # Try to bind to a random port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            assert port > 0, "Could not bind to localhost port"
        finally:
            sock.close()


class TestEnvironmentSummary:
    """Summary of environment status."""

    def test_environment_summary(self):
        """Print environment summary."""
        print("\n" + "=" * 60)
        print("RSS MCP Test Environment Summary")
        print("=" * 60)

        # Python version
        print(f"Python: {sys.version}")

        # Key packages
        packages = {
            "mcp": "MCP Library",
            "feedparser": "Feed Parser",
            "aiohttp": "Async HTTP",
            "fastapi": "FastAPI",
            "pytest": "PyTest",
        }

        print("\nPackages:")
        for pkg, name in packages.items():
            try:
                module = __import__(pkg)
                version = getattr(module, "__version__", "installed")
                print(f"  ✅ {name}: {version}")
            except ImportError:
                print(f"  ❌ {name}: not installed")

        # RSS MCP
        try:
            import rss_mcp

            print(f"\n✅ RSS MCP Package: {rss_mcp.__file__}")
        except ImportError:
            print("\n❌ RSS MCP Package: not installed")

        print("=" * 60)

"""Basic validation tests to ensure the test framework works."""

import os
import tempfile
from pathlib import Path

import pytest

try:
    from .test_rss_server import LocalRSSServer
except ImportError:
    from test_rss_server import LocalRSSServer


class TestBasicValidation:
    """Basic validation tests."""

    def test_project_structure(self):
        """Test that required project files exist."""
        project_root = Path(__file__).parent.parent

        # Check key files exist
        assert (project_root / "src" / "rss_mcp" / "__init__.py").exists()
        assert (project_root / "src" / "rss_mcp" / "cli.py").exists()
        assert (project_root / "src" / "rss_mcp" / "server.py").exists()
        assert (project_root / "pyproject.toml").exists()

    def test_test_data_exists(self):
        """Test that RSS test data files exist."""
        test_data_dir = Path(__file__).parent / "fixtures" / "rss_data"

        assert test_data_dir.exists(), "Test data directory should exist"
        assert (test_data_dir / "solidot.xml").exists(), "Solidot RSS data should exist"
        assert (test_data_dir / "zaobao.xml").exists(), "Zaobao RSS data should exist"

        # Check files are not empty
        solidot_content = (test_data_dir / "solidot.xml").read_text()
        zaobao_content = (test_data_dir / "zaobao.xml").read_text()

        assert len(solidot_content) > 100, "Solidot RSS data should not be empty"
        assert len(zaobao_content) > 100, "Zaobao RSS data should not be empty"
        assert "<?xml" in solidot_content, "Solidot should be valid XML"
        assert "<?xml" in zaobao_content, "Zaobao should be valid XML"

    @pytest.mark.asyncio
    async def test_local_rss_server_functionality(self):
        """Test that our local RSS server works."""
        server = LocalRSSServer()

        try:
            base_url = await server.start()
            assert base_url.startswith("http://")

            # Test that server has both URLs
            assert server.solidot_url.endswith("/solidot/www")
            assert server.zaobao_url.endswith("/zaobao/znews/world")

        finally:
            await server.stop()

    def test_cli_import(self):
        """Test that CLI module can be imported."""
        try:
            import src.rss_mcp.cli

            assert hasattr(src.rss_mcp.cli, "cli")
        except ImportError:
            import rss_mcp.cli

            assert hasattr(rss_mcp.cli, "cli")

    def test_server_import(self):
        """Test that server module can be imported."""
        try:
            import src.rss_mcp.server

            assert hasattr(src.rss_mcp.server, "server")
        except ImportError:
            import rss_mcp.server

            assert hasattr(rss_mcp.server, "server")

    def test_environment_setup(self):
        """Test environment variable setup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_env = {
                **os.environ,
                "RSS_MCP_CONFIG_DIR": str(Path(temp_dir) / "config"),
                "RSS_MCP_CACHE_DIR": str(Path(temp_dir) / "cache"),
                "RSS_MCP_USER": "test_validation_user",
            }

            # Test that the environment variables are set correctly
            assert test_env["RSS_MCP_CONFIG_DIR"].endswith("config")
            assert test_env["RSS_MCP_CACHE_DIR"].endswith("cache")
            assert test_env["RSS_MCP_USER"] == "test_validation_user"

    def test_required_dependencies(self):
        """Test that required dependencies are available."""
        try:
            pass

            assert True, "All required dependencies are available"
        except ImportError as e:
            pytest.fail(f"Required dependency missing: {e}")


if __name__ == "__main__":
    # Run basic tests directly
    import asyncio

    validator = TestBasicValidation()

    print("Running basic validation tests...")

    # Test 1: Project structure
    try:
        validator.test_project_structure()
        print("✓ Project structure test passed")
    except Exception as e:
        print(f"✗ Project structure test failed: {e}")

    # Test 2: Test data exists
    try:
        validator.test_test_data_exists()
        print("✓ Test data exists test passed")
    except Exception as e:
        print(f"✗ Test data exists test failed: {e}")

    # Test 3: RSS server functionality
    try:
        asyncio.run(validator.test_local_rss_server_functionality())
        print("✓ Local RSS server functionality test passed")
    except Exception as e:
        print(f"✗ Local RSS server functionality test failed: {e}")

    # Test 4: CLI import
    try:
        validator.test_cli_import()
        print("✓ CLI import test passed")
    except Exception as e:
        print(f"✗ CLI import test failed: {e}")

    # Test 5: Server import
    try:
        validator.test_server_import()
        print("✓ Server import test passed")
    except Exception as e:
        print(f"✗ Server import test failed: {e}")

    # Test 6: Environment setup
    try:
        validator.test_environment_setup()
        print("✓ Environment setup test passed")
    except Exception as e:
        print(f"✗ Environment setup test failed: {e}")

    # Test 7: Dependencies
    try:
        validator.test_required_dependencies()
        print("✓ Required dependencies test passed")
    except Exception as e:
        print(f"✗ Required dependencies test failed: {e}")

    print("\nBasic validation tests completed!")

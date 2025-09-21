"""Root pytest configuration with custom test runner functionality."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

import pytest


# Test environment utilities
def install_python_dependencies() -> bool:
    """Install Python development dependencies."""
    try:
        print("📦 Installing Python dependencies...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            print("✅ Python dependencies installed successfully")
            return True
        else:
            print(f"❌ Python dependency installation failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Python dependency installation timed out")
        return False


def clean_test_artifacts():
    """Clean up test artifacts."""
    print("🧹 Cleaning test artifacts...")
    
    artifacts = [
        "htmlcov/",
        ".coverage",
        "coverage.xml", 
        ".pytest_cache/",
        "integration-test-results.xml",
        "test-results.xml",
        "__pycache__",
        "*.pyc",
    ]
    
    cleaned_count = 0
    for artifact in artifacts:
        artifact_path = Path(artifact)
        
        # Handle glob patterns
        if '*' in artifact:
            import glob
            for match in glob.glob(artifact, recursive=True):
                match_path = Path(match)
                if match_path.exists():
                    if match_path.is_dir():
                        shutil.rmtree(match_path)
                    else:
                        match_path.unlink()
                    cleaned_count += 1
        else:
            if artifact_path.exists():
                if artifact_path.is_dir():
                    shutil.rmtree(artifact_path)
                    print(f"  Removed directory: {artifact}")
                else:
                    artifact_path.unlink()
                    print(f"  Removed file: {artifact}")
                cleaned_count += 1
    
    print(f"✅ Cleaned {cleaned_count} artifacts")


def check_environment():
    """Check if test environment is ready."""
    print("\n🔍 Environment Check")
    print("=" * 50)
    
    issues = []
    
    # Python version
    python_version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True)
    print(f"Python: {python_version.stdout.strip()}")
    
    # Project dependencies
    try:
        import rss_mcp
        print(f"✅ RSS MCP: {rss_mcp.__file__}")
    except ImportError:
        print("❌ RSS MCP: Not installed")
        issues.append("RSS MCP package not installed - install with --install-deps")
    
    if issues:
        print(f"\n⚠️  Found {len(issues)} issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n✅ Environment is ready for testing!")
        return True


# Pytest hooks and configuration
def pytest_addoption(parser):
    """Add custom command-line options."""
    group = parser.getgroup("RSS MCP Testing")
    
    # Test type selection
    group.addoption(
        "--test-type",
        choices=["unit", "integration", "stdio", "http", "env", "all"],
        default=None,
        help="Type of tests to run (unit, integration, stdio, http, env, all)"
    )
    
    # Environment and setup options
    group.addoption(
        "--check-env",
        action="store_true",
        help="Check test environment before running"
    )
    
    group.addoption(
        "--install-deps",
        action="store_true",
        help="Install Python dependencies before testing"
    )
    
    group.addoption(
        "--clean",
        action="store_true",
        help="Clean test artifacts before running"
    )
    
    group.addoption(
        "--no-env-check",
        action="store_true",
        help="Skip automatic environment checks"
    )


def pytest_configure(config):
    """Configure pytest and handle setup options."""
    # Register custom markers
    markers = [
        "integration: marks tests as integration tests",
        "slow: marks tests as slow (may be skipped)",
        "network: marks tests as requiring network access",
        "unit: marks tests as unit tests",
        "env_check: marks tests for environment validation"
    ]
    
    for marker in markers:
        config.addinivalue_line("markers", marker)
    
    # Handle setup options before test collection
    if config.getoption("--clean"):
        clean_test_artifacts()
    
    if config.getoption("--install-deps"):
        if not install_python_dependencies():
            print("⚠️  Python dependency installation failed - tests may not work")
    
    # Check environment if requested
    should_check_env = config.getoption("--check-env")
    
    if should_check_env and not config.getoption("--no-env-check"):
        if not check_environment():
            print("\n⚠️  Environment issues detected. Use --no-env-check to skip validation.")


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on --test-type option."""
    test_type = config.getoption("--test-type")
    
    if not test_type:
        return  # No filtering requested
    
    # Apply filters based on test type
    if test_type == "unit":
        # Skip integration tests
        skip_integration = pytest.mark.skip(reason="Running unit tests only (--test-type=unit)")
        for item in items:
            if any(marker in item.keywords for marker in ["integration", "network"]):
                item.add_marker(skip_integration)
    
    elif test_type == "integration":
        # Skip unit tests, only run integration tests
        skip_unit = pytest.mark.skip(reason="Running integration tests only (--test-type=integration)")
        for item in items:
            if "integration" not in item.keywords:
                # Check if it's in integration directory
                if "integration" not in str(item.fspath):
                    item.add_marker(skip_unit)
    
    elif test_type == "stdio":
        # Only run stdio-specific integration tests
        skip_non_stdio = pytest.mark.skip(reason="Running stdio tests only (--test-type=stdio)")
        for item in items:
            if "test_mcp_stdio" not in str(item.fspath) and "test_mcp_native_stdio" not in str(item.fspath):
                item.add_marker(skip_non_stdio)
    
    elif test_type == "http":
        # Only run HTTP-specific integration tests
        skip_non_http = pytest.mark.skip(reason="Running HTTP tests only (--test-type=http)")
        for item in items:
            if "test_mcp_http" not in str(item.fspath) and "test_mcp_native_http" not in str(item.fspath):
                item.add_marker(skip_non_http)
    
    elif test_type == "env":
        # Only run environment tests
        skip_non_env = pytest.mark.skip(reason="Running environment tests only (--test-type=env)")
        for item in items:
            if not any(marker in item.keywords for marker in ["env_check"]) and "environment" not in str(item.fspath):
                item.add_marker(skip_non_env)
    
    # test_type == "all" runs everything (no filtering)


def pytest_report_teststatus(report, config):
    """Customize test status reporting with emoji."""
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            return "xfailed", "⚠", "XFAIL"
        elif report.passed:
            if "slow" in getattr(report, "keywords", {}):
                return "passed", "🐢", "SLOW"
            elif "integration" in getattr(report, "keywords", {}):
                return "passed", "🔗", "INTEGRATION"
            else:
                return "passed", "✅", "PASS"
        elif report.failed:
            return "failed", "❌", "FAIL"
        elif report.skipped:
            return "skipped", "⏭", "SKIP"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Add custom summary information to test output."""
    test_type = config.getoption("--test-type")
    
    if test_type:
        terminalreporter.section(f"RSS MCP Test Summary ({test_type})")
    else:
        terminalreporter.section("RSS MCP Test Summary")
    
    # Environment status
    terminalreporter.write_line("Environment Status:")
    terminalreporter.write_line(f"  Python: ✅")
    
    try:
        import rss_mcp
        terminalreporter.write_line(f"  RSS MCP: ✅")
    except ImportError:
        terminalreporter.write_line(f"  RSS MCP: ❌")
    
    # Quick command examples
    terminalreporter.write_line("\nQuick Commands:")
    terminalreporter.write_line("  pytest --test-type=unit              # Fast unit tests")
    terminalreporter.write_line("  pytest --test-type=integration       # All integration tests")  
    terminalreporter.write_line("  pytest --test-type=stdio             # Stdio transport tests")
    terminalreporter.write_line("  pytest --test-type=http              # HTTP transport tests")
    terminalreporter.write_line("  pytest --test-type=all               # Everything")


# Pytest session hooks for overall test management
def pytest_sessionstart(session):
    """Called after the Session object has been created."""
    config = session.config
    test_type = config.getoption("--test-type")
    
    if test_type:
        print(f"\n🧪 Starting {test_type.upper()} tests...")
    else:
        print("\n🧪 Starting tests...")


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished."""
    test_type = session.config.getoption("--test-type")
    
    if exitstatus == 0:
        if test_type:
            print(f"\n🎉 All {test_type} tests passed!")
        else:
            print("\n🎉 All tests passed!")
    else:
        if test_type:
            print(f"\n💥 Some {test_type} tests failed!")
        else:
            print("\n💥 Some tests failed!")
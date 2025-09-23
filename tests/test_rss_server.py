"""Local RSS test server for testing without external dependencies."""

import asyncio
import logging
import socket
from pathlib import Path
from typing import Dict, Optional

import aiohttp
import pytest
from aiohttp import web

logger = logging.getLogger(__name__)


class LocalRSSServer:
    """Local RSS server to serve test data."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._actual_port: Optional[int] = None

        # Load test RSS data
        self.rss_data = self._load_test_data()

    def _load_test_data(self) -> Dict[str, str]:
        """Load RSS test data from files."""
        test_data_dir = Path(__file__).parent / "fixtures" / "rss_data"
        data = {}

        # Load Solidot data
        solidot_file = test_data_dir / "solidot.xml"
        if solidot_file.exists():
            data["solidot"] = solidot_file.read_text(encoding="utf-8")

        # Load Zaobao data
        zaobao_file = test_data_dir / "zaobao.xml"
        if zaobao_file.exists():
            data["zaobao"] = zaobao_file.read_text(encoding="utf-8")

        logger.info(f"Loaded {len(data)} RSS test data files")
        return data

    def _find_free_port(self) -> int:
        """Find a free port if port is 0."""
        if self.port != 0:
            return self.port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    async def _handle_solidot(self, request: web.Request) -> web.Response:
        """Handle solidot RSS requests."""
        content = self.rss_data.get("solidot", "")
        if not content:
            return web.Response(text="Solidot RSS data not found", status=404)

        return web.Response(text=content, content_type="application/xml", charset="utf-8")

    async def _handle_zaobao(self, request: web.Request) -> web.Response:
        """Handle zaobao RSS requests."""
        content = self.rss_data.get("zaobao", "")
        if not content:
            return web.Response(text="Zaobao RSS data not found", status=404)

        return web.Response(text=content, content_type="application/xml", charset="utf-8")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.Response(text="OK")

    def _setup_routes(self):
        """Setup server routes."""
        self.app.router.add_get("/solidot/www", self._handle_solidot)
        self.app.router.add_get("/zaobao/znews/world", self._handle_zaobao)
        self.app.router.add_get("/health", self._handle_health)

    async def start(self) -> str:
        """Start the RSS server and return the base URL."""
        # Find actual port to use
        self._actual_port = self._find_free_port()

        # Create aiohttp application
        self.app = web.Application()
        self._setup_routes()

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self._actual_port, reuse_address=True)
        await self.site.start()

        base_url = f"http://{self.host}:{self._actual_port}"
        logger.info(f"Local RSS server started at {base_url}")
        return base_url

    async def stop(self):
        """Stop the RSS server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        logger.info("Local RSS server stopped")

    @property
    def base_url(self) -> str:
        """Get the base URL of the server."""
        if self._actual_port is None:
            raise RuntimeError("Server not started")
        return f"http://{self.host}:{self._actual_port}"

    @property
    def solidot_url(self) -> str:
        """Get the Solidot RSS URL."""
        return f"{self.base_url}/solidot/www"

    @property
    def zaobao_url(self) -> str:
        """Get the Zaobao RSS URL."""
        return f"{self.base_url}/zaobao/znews/world"


# Test the server
@pytest.mark.asyncio
async def test_local_rss_server():
    """Test the local RSS server functionality."""
    server = LocalRSSServer()

    try:
        # Start server
        base_url = await server.start()
        print(f"Test server started at: {base_url}")

        # Test health endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/health") as resp:
                assert resp.status == 200
                text = await resp.text()
                assert text == "OK"

        # Test Solidot RSS
        async with aiohttp.ClientSession() as session:
            async with session.get(server.solidot_url) as resp:
                assert resp.status == 200
                content = await resp.text()
                assert "<?xml" in content
                assert "Solidot" in content or "奇客" in content

        # Test Zaobao RSS
        async with aiohttp.ClientSession() as session:
            async with session.get(server.zaobao_url) as resp:
                assert resp.status == 200
                content = await resp.text()
                assert "<?xml" in content
                assert "联合早报" in content

        print("✓ All RSS server tests passed")

    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(test_local_rss_server())

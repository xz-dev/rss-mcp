"""Mock HTTP server for RSS content in tests."""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from aiohttp import web
from aiohttp.web import Application, Request, Response

# Sample RSS content templates
SAMPLE_RSS_FEEDS = {
    "v2ex-latest": """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
<channel>
<title>V2EX-最新主题</title>
<link>https://www.v2ex.com/</link>
<atom:link href="http://localhost:{port}/v2ex/topics/latest" rel="self" type="application/rss+xml"/>
<description>V2EX-最新主题 - Mock RSS Server for Tests</description>
<generator>Mock RSS Server</generator>
<language>en</language>
<lastBuildDate>Mon, 22 Sep 2025 01:12:02 GMT</lastBuildDate>
<ttl>180</ttl>
<item>
<title>AI 应用开发工程师（居家办公）</title>
<description>负责出海 AI 陪伴类移动 App 后端 AI 智能体系统研发，最前沿的 AI 应用领域。</description>
<link>https://www.v2ex.com/t/1160931</link>
<guid isPermaLink="false">https://www.v2ex.com/t/1160931</guid>
<pubDate>Mon, 22 Sep 2025 00:57:37 GMT</pubDate>
<author>NascentCoreAI</author>
<category>酷工作</category>
</item>
<item>
<title>调查：问男生，在家会不会坐着尿尿？</title>
<description>之前会坐着，现在倾向站着。</description>
<link>https://www.v2ex.com/t/1160930</link>
<guid isPermaLink="false">https://www.v2ex.com/t/1160930</guid>
<pubDate>Mon, 22 Sep 2025 00:53:01 GMT</pubDate>
<author>poe</author>
<category>问与答</category>
</item>
<item>
<title>预算 3000 左右的 NAS 选择</title>
<description>想给家里孩子的照片、动画片、纪录片什么的准备的一个 NAS 单独存。</description>
<link>https://www.v2ex.com/t/1160927</link>
<guid isPermaLink="false">https://www.v2ex.com/t/1160927</guid>
<pubDate>Mon, 22 Sep 2025 00:41:46 GMT</pubDate>
<author>itoshinji</author>
<category>NAS</category>
</item>
</channel>
</rss>""",

    "github-trending": """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
<channel>
<title>GitHub Trending - Daily</title>
<link>https://github.com/trending</link>
<atom:link href="http://localhost:{port}/github/trending/daily" rel="self" type="application/rss+xml"/>
<description>GitHub Trending Repositories - Mock RSS Server for Tests</description>
<generator>Mock RSS Server</generator>
<language>en</language>
<lastBuildDate>Mon, 22 Sep 2025 01:00:00 GMT</lastBuildDate>
<ttl>3600</ttl>
<item>
<title>awesome/project - Awesome AI project for developers</title>
<description>An amazing AI project that helps developers build better applications with machine learning.</description>
<link>https://github.com/awesome/project</link>
<guid isPermaLink="false">https://github.com/awesome/project</guid>
<pubDate>Mon, 22 Sep 2025 00:30:00 GMT</pubDate>
<author>awesome-dev</author>
<category>ai</category>
</item>
<item>
<title>cool/tool - Developer productivity tool</title>
<description>A cool productivity tool that makes development faster and more efficient.</description>
<link>https://github.com/cool/tool</link>
<guid isPermaLink="false">https://github.com/cool/tool</guid>
<pubDate>Mon, 22 Sep 2025 00:15:00 GMT</pubDate>
<author>cool-dev</author>
<category>productivity</category>
</item>
</channel>
</rss>""",

    "tech-news": """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
<channel>
<title>Tech News - Latest</title>
<link>https://technews.example.com/</link>
<atom:link href="http://localhost:{port}/tech/news" rel="self" type="application/rss+xml"/>
<description>Latest Technology News - Mock RSS Server for Tests</description>
<generator>Mock RSS Server</generator>
<language>en</language>
<lastBuildDate>Mon, 22 Sep 2025 01:00:00 GMT</lastBuildDate>
<ttl>1800</ttl>
<item>
<title>AI Breakthrough in Natural Language Processing</title>
<description>Researchers announce major breakthrough in AI language models with improved accuracy.</description>
<link>https://technews.example.com/ai-breakthrough-nlp</link>
<guid isPermaLink="false">ai-breakthrough-nlp-2025</guid>
<pubDate>Mon, 22 Sep 2025 00:45:00 GMT</pubDate>
<author>Tech Reporter</author>
<category>AI</category>
</item>
<item>
<title>New Programming Language Gains Popularity</title>
<description>A new systems programming language is gaining traction among developers.</description>
<link>https://technews.example.com/new-lang-popular</link>
<guid isPermaLink="false">new-lang-popular-2025</guid>
<pubDate>Mon, 22 Sep 2025 00:30:00 GMT</pubDate>
<author>Dev News</author>
<category>Programming</category>
</item>
</channel>
</rss>"""
}


class MockRSSServer:
    """Mock HTTP server serving RSS feeds for testing."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.actual_port: Optional[int] = None
        
        # Set up routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up HTTP routes for RSS feeds."""
        self.app.router.add_get("/v2ex/topics/latest", self._handle_v2ex_latest)
        self.app.router.add_get("/github/trending/daily", self._handle_github_trending) 
        self.app.router.add_get("/github/trending/weekly", self._handle_github_trending)
        self.app.router.add_get("/tech/news", self._handle_tech_news)
        self.app.router.add_get("/36kr/newsflashes", self._handle_tech_news)
        self.app.router.add_get("/36kr/latest", self._handle_tech_news)
        self.app.router.add_get("/zhihu/hot", self._handle_tech_news)
        
        # Health check endpoint
        self.app.router.add_get("/health", self._handle_health)
    
    async def _handle_v2ex_latest(self, request: Request) -> Response:
        """Handle V2EX latest topics RSS."""
        content = SAMPLE_RSS_FEEDS["v2ex-latest"].format(port=self.actual_port or self.port)
        return Response(text=content, content_type="application/xml", charset="utf-8")
    
    async def _handle_github_trending(self, request: Request) -> Response:
        """Handle GitHub trending RSS."""
        content = SAMPLE_RSS_FEEDS["github-trending"].format(port=self.actual_port or self.port)
        return Response(text=content, content_type="application/xml", charset="utf-8")
    
    async def _handle_tech_news(self, request: Request) -> Response:
        """Handle tech news RSS."""
        content = SAMPLE_RSS_FEEDS["tech-news"].format(port=self.actual_port or self.port)
        return Response(text=content, content_type="application/xml", charset="utf-8")
    
    async def _handle_health(self, request: Request) -> Response:
        """Health check endpoint."""
        return Response(text=json.dumps({"status": "ok", "server": "mock-rss"}), 
                       content_type="application/json")
    
    async def start(self) -> int:
        """Start the mock RSS server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        # Get the actual port if port was 0
        self.actual_port = self.site._server.sockets[0].getsockname()[1]
        return self.actual_port
    
    async def stop(self):
        """Stop the mock RSS server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
    
    def get_url(self, path: str = "") -> str:
        """Get the base URL or URL with path for the mock server."""
        port = self.actual_port or self.port
        return f"http://{self.host}:{port}{path}"
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


# Convenience functions for tests
async def create_mock_rss_server(host: str = "127.0.0.1", port: int = 0) -> MockRSSServer:
    """Create and start a mock RSS server."""
    server = MockRSSServer(host, port)
    await server.start()
    return server


def get_mock_feed_urls(server_url: str) -> Dict[str, List[str]]:
    """Get mock RSS feed URLs for testing."""
    return {
        "v2ex-latest": {
            "name": "v2ex-latest",
            "title": "V2EX Latest Topics", 
            "urls": [f"{server_url}/v2ex/topics/latest"],
            "backup_urls": [],
        },
        "github-trending": {
            "name": "github-trending",
            "title": "GitHub Trending",
            "urls": [f"{server_url}/github/trending/daily"],
            "backup_urls": [f"{server_url}/github/trending/weekly"],
        },
        "tech-news": {
            "name": "tech-news",
            "title": "Tech News",
            "urls": [f"{server_url}/tech/news"],
            "backup_urls": [f"{server_url}/36kr/latest", f"{server_url}/zhihu/hot"],
        },
    }
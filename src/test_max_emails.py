import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from scraper import AsyncScraper

class TestAsyncScraper(unittest.IsolatedAsyncioTestCase):
    async def test_max_emails_limit(self):
        config = {
            'max_emails_per_domain': 2,
            'max_pages_per_domain': 10,
            'domain_timeout': 10,
            'request_timeout': 1,
            'booking_platforms_follow': [],
            'booking_platforms_skip': [],
            'priority_paths': [],
            'link_keywords': ['page']
        }
        filters = {}
        scraper = AsyncScraper(config, filters)

        # Mock fetch_html
        scraper.fetch_html = AsyncMock(side_effect=[
            '<html><body>Email: test1@example.com <a href="/page2">Page 2</a></body></html>',
            '<html><body>Email: test2@example.com Email: test3@example.com</body></html>',
            '<html><body>Email: test4@example.com</body></html>'
        ])

        session = AsyncMock()

        # Run crawl_website
        result = await scraper.crawl_website(session, "http://example.com")

        # First page: 1 email. Link /page2 found (matches 'page' keyword).
        # Second page: 2 emails. Total 3.
        # Check limit (3 >= 2). Break.

        self.assertGreaterEqual(len(result['emails']), 2)
        # Should be exactly 3 in this setup
        self.assertEqual(len(result['emails']), 3)

        # Should have fetched exactly 2 pages
        self.assertEqual(scraper.fetch_html.call_count, 2)

        self.assertIn('test1@example.com', result['emails'])
        self.assertIn('test2@example.com', result['emails'])
        self.assertIn('test3@example.com', result['emails'])
        self.assertNotIn('test4@example.com', result['emails'])

if __name__ == '__main__':
    unittest.main()

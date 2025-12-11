import asyncio
import aiohttp
import logging
import re
import json
import yaml
import random
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from fake_useragent import UserAgent
import time
from typing import List, Set, Dict, Tuple, Optional
from utils import log_filtered_item

# Load configuration
def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("config.yaml not found, using defaults")
        return {}

def load_filters(path: str = "filters.json") -> dict:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("filters.json not found, using defaults")
        return {}

class AsyncScraper:
    def __init__(self, config: dict, filters: dict):
        self.config = config
        self.filters = filters
        self.ua = UserAgent()

        # Regex Patterns
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        self.fb_pattern = re.compile(r'(?:https?://)?(?:www\.|m\.)?(?:facebook\.com|fb\.com|fb\.me)/(?:(?:\w)*#!(?:/))?(?:pages/)?(?:[\w\-]*\/)*([\w\-\.]+)(?:/)?')

        # Timeout settings
        self.timeout_seconds = self.config.get('request_timeout', 15)
        self.timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        self.max_retries = self.config.get('max_retries_per_url', 2)

    def get_headers(self) -> dict:
        """Generate random headers to mimic a browser."""
        return {
            'User-Agent': self.ua.random if self.config.get('user_agent_rotation', True) else 'Mozilla/5.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def should_scrape_domain(self, url: str) -> Tuple[bool, str]:
        """Check if domain should be scraped based on filters."""
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check extensions
        for ext in self.filters.get('skip_domain_extensions', []):
            if domain.endswith(ext):
                return False, f"Excluded extension: {ext}"

        return True, ""

    def is_valid_email(self, email: str) -> Tuple[bool, str]:
        """Check if email is valid based on filters."""
        email_lower = email.lower()

        # Basic validation
        if len(email) > 100: return False, "Too long"

        # Check prefixes
        for prefix in self.filters.get('skip_email_prefixes', []):
            if email_lower.startswith(prefix):
                return False, f"Excluded prefix: {prefix}"

        # Check domains
        domain = email_lower.split('@')[-1]
        if domain in self.filters.get('skip_email_domains', []):
            return False, f"Excluded domain: {domain}"

        # Check patterns
        for pattern in self.filters.get('skip_email_patterns', []):
            if pattern in email_lower:
                return False, f"Excluded pattern: {pattern}"

        return True, ""

    async def fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch HTML content with retries and timeout."""
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        for attempt in range(self.max_retries + 1):
            try:
                # Random delay
                min_delay = self.config.get('delay_between_requests_min', 0.5)
                max_delay = self.config.get('delay_between_requests_max', 2.0)
                await asyncio.sleep(random.uniform(min_delay, max_delay))

                async with session.get(url, headers=self.get_headers(), timeout=self.timeout, ssl=self.config.get('verify_ssl', False)) as response:
                    if response.status == 200:
                        # Limit size to prevent memory issues with massive pages
                        # Reading strictly up to 5MB
                        content = await response.content.read(5 * 1024 * 1024)
                        try:
                            return content.decode('utf-8', errors='ignore')
                        except Exception:
                            return content.decode('latin-1', errors='ignore')
                    elif response.status in [403, 401, 429]:
                        logging.warning(f"Access denied {response.status} for {url}. Attempt {attempt+1}/{self.max_retries+1}")
                    else:
                        logging.warning(f"Status {response.status} for {url}")

            except asyncio.TimeoutError:
                logging.warning(f"Timeout ({self.timeout_seconds}s) for {url}. Attempt {attempt+1}/{self.max_retries+1}")
            except aiohttp.ClientError as e:
                logging.warning(f"ClientError for {url}: {str(e)}. Attempt {attempt+1}/{self.max_retries+1}")
            except Exception as e:
                logging.error(f"Unexpected error for {url}: {str(e)}")

            # Exponential backoff for retries
            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)

        return None

    def extract_data(self, html: str, base_url: str) -> Dict[str, Set[str]]:
        """Extract emails and Facebook links from HTML."""
        if not html:
            return {'emails': set(), 'facebook': set()}

        soup = BeautifulSoup(html, 'lxml')
        text_content = soup.get_text()

        # Extract Emails
        found_emails = set()

        # 1. From text content
        text_emails = self.email_pattern.findall(text_content)
        found_emails.update(text_emails)

        # 2. From mailto links
        for link in soup.select('a[href^="mailto:"]'):
            href = link.get('href', '')
            if href:
                # Handle 'mailto:user@example.com?subject=...'
                clean_email = href.replace('mailto:', '').split('?')[0]
                if self.email_pattern.match(clean_email):
                    found_emails.add(clean_email)

        # Validate and Filter Emails
        valid_emails = set()
        for email in found_emails:
            # Clean trailing periods or dots that regex might have picked up at end of sentence
            email = email.rstrip('.')
            is_valid, reason = self.is_valid_email(email)
            if is_valid:
                valid_emails.add(email)
            else:
                log_filtered_item("Email", email, reason)

        # Extract Facebook Links
        facebook_links = set()

        # Search all 'a' tags
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Resolve relative URLs
            absolute_url = urljoin(base_url, href)

            if 'facebook.com' in absolute_url or 'fb.com' in absolute_url:
                 # Basic filter to avoid share links if possible, though regex helps
                 if 'share' not in absolute_url and 'sharer' not in absolute_url:
                     facebook_links.add(absolute_url)

        return {
            'emails': valid_emails,
            'facebook': facebook_links
        }

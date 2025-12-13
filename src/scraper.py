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
from collections import deque

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
        # Improved email regex:
        # - Requires at least 2 chars for TLD
        # - Handles + tags
        # - Excludes common image extensions at the end (basic heuristic)
        self.email_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        )

        # Timeout settings
        self.timeout_seconds = self.config.get('request_timeout', 15)
        self.timeout = aiohttp.ClientTimeout(total=self.timeout_seconds, sock_connect=10, sock_read=10)

        self.max_retries = self.config.get('max_retries_per_url', 2)

    def get_headers(self) -> dict:
        """Generate random headers to mimic a browser."""
        return {
            'User-Agent': self.ua.random if self.config.get('user_agent_rotation', True) else 'Mozilla/5.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1', # Do Not Track
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }

    def should_scrape_domain(self, url: str) -> Tuple[bool, str]:
        """Check if domain should be scraped based on filters."""
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except ValueError:
             return False, "Invalid URL"

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
        try:
            domain = email_lower.split('@')[-1]
        except IndexError:
             return False, "Invalid email format"

        if domain in self.filters.get('skip_email_domains', []):
            return False, f"Excluded domain: {domain}"

        # Check patterns
        for pattern in self.filters.get('skip_email_patterns', []):
            if pattern in email_lower:
                return False, f"Excluded pattern: {pattern}"

        # Additional sanity checks
        # Avoid image files mistook as emails (e.g. name@domain.png)
        if email_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp')):
             return False, "Image extension"

        return True, ""

    async def fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch HTML content with retries and timeout."""
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        for attempt in range(self.max_retries + 1):
            try:
                # Random delay
                min_delay = self.config.get('delay_between_requests_min', 0.1)
                max_delay = self.config.get('delay_between_requests_max', 1.0)
                if min_delay > 0 or max_delay > 0:
                     await asyncio.sleep(random.uniform(min_delay, max_delay))

                async with session.get(url, headers=self.get_headers(), timeout=self.timeout, ssl=self.config.get('verify_ssl', False)) as response:
                    if response.status == 200:
                        # Limit size to avoid memory issues
                        content = await response.content.read(10 * 1024 * 1024) # 10MB limit

                        # Try to detect encoding
                        encoding = response.charset or 'utf-8'
                        try:
                            return content.decode(encoding, errors='ignore')
                        except LookupError:
                             # Fallback
                             return content.decode('utf-8', errors='ignore')

                    elif response.status in [403, 401, 429]:
                        logging.debug(f"Access denied {response.status} for {url}. Attempt {attempt+1}")
                        # Slightly longer backoff for 429
                        if response.status == 429:
                             await asyncio.sleep(2 ** (attempt + 2))
                    else:
                        logging.debug(f"Status {response.status} for {url}")

            except asyncio.TimeoutError:
                logging.debug(f"Timeout ({self.timeout_seconds}s) for {url}")
            except aiohttp.ClientError as e:
                logging.debug(f"ClientError for {url}: {str(e)}")
            except Exception as e:
                logging.debug(f"Unexpected error for {url}: {str(e)}")

            # Exponential backoff for retries
            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)

        return None

    def extract_data(self, html: str, base_url: str) -> Dict[str, Set[str]]:
        """Extract emails, Facebook links, and new candidate links from HTML."""
        if not html:
            return {'emails': set(), 'facebook': set(), 'links': set()}

        soup = BeautifulSoup(html, 'lxml')
        text_content = soup.get_text()

        # 1. Extract Emails
        found_emails = set()
        text_emails = self.email_pattern.findall(text_content)
        found_emails.update(text_emails)

        for link in soup.select('a[href^="mailto:"]'):
            href = link.get('href', '')
            if href:
                clean_email = href.replace('mailto:', '').split('?')[0]
                if self.email_pattern.match(clean_email):
                    found_emails.add(clean_email)

        valid_emails = set()
        for email in found_emails:
            email = email.rstrip('.')
            is_valid, reason = self.is_valid_email(email)
            if is_valid:
                valid_emails.add(email)
            else:
                log_filtered_item("Email", email, reason)

        # 2. Extract Facebook Links & Candidate Links
        facebook_links = set()
        candidate_links = set()

        follow_platforms = self.config.get('booking_platforms_follow', [])
        skip_platforms = self.config.get('booking_platforms_skip', [])
        keywords = self.config.get('link_keywords', [])

        base_parsed = urlparse(base_url)
        base_domain = base_parsed.netloc.replace('www.', '')

        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            parsed_url = urlparse(absolute_url)

            # Facebook
            if 'facebook.com' in absolute_url or 'fb.com' in absolute_url:
                 if 'share' not in absolute_url and 'sharer' not in absolute_url:
                     facebook_links.add(absolute_url)

            # Booking Platforms
            if any(p in absolute_url for p in follow_platforms):
                candidate_links.add(absolute_url)
            elif any(p in absolute_url for p in skip_platforms):
                # Just log, don't follow
                logging.debug(f"Booking platform detected but skipped: {absolute_url}")

            # Internal Links with Keywords
            # Robust domain check
            link_domain = parsed_url.netloc.replace('www.', '')
            if link_domain == base_domain or link_domain == "":
                 lower_href = href.lower()
                 if any(kw in lower_href for kw in keywords):
                     candidate_links.add(absolute_url)

        return {
            'emails': valid_emails,
            'facebook': facebook_links,
            'links': candidate_links
        }

    async def crawl_website(self, session: aiohttp.ClientSession, start_url: str) -> Dict[str, Set[str]]:
        """Crawl the website starting from start_url."""
        if not start_url.startswith(('http://', 'https://')):
            start_url = 'http://' + start_url

        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc.replace('www.', '')

        domain_timeout = self.config.get('domain_timeout', 45)
        max_pages = self.config.get('max_pages_per_domain', 15)

        visited = set()
        queue = deque([start_url])

        # Add priority paths
        priority_paths = self.config.get('priority_paths', [])
        clean_start = start_url.rstrip('/')
        for path in priority_paths:
            if not path.startswith('/'): path = '/' + path
            queue.append(clean_start + path)

        all_emails = set()
        all_facebook = set()
        pages_crawled = 0

        start_time = time.time()

        while queue and pages_crawled < max_pages:
            if time.time() - start_time > domain_timeout:
                logging.info(f"Domain timeout for {base_domain}")
                break

            current_url = queue.popleft()

            # Normalize for visited check
            # Strip fragments and query params for basic dedup
            normalized_url = current_url.split('#')[0].rstrip('/')

            if normalized_url in visited:
                continue
            visited.add(normalized_url)

            logging.debug(f"Crawling {current_url} ({pages_crawled+1}/{max_pages})")

            html = await self.fetch_html(session, current_url)
            pages_crawled += 1

            if html:
                data = self.extract_data(html, current_url)
                all_emails.update(data['emails'])
                all_facebook.update(data['facebook'])

                # Add new discovered links to queue
                for link in data['links']:
                    link_clean = link.split('#')[0].rstrip('/')
                    if link_clean not in visited and link not in queue:
                        # Safety check
                        try:
                            parsed_link = urlparse(link)
                        except ValueError:
                            continue

                        link_domain = parsed_link.netloc.replace('www.', '')

                        is_same_domain = link_domain == base_domain
                        is_booking = any(p in link for p in self.config.get('booking_platforms_follow', []))

                        if is_booking:
                             # Prioritize booking platforms
                             queue.appendleft(link)
                        elif is_same_domain:
                            queue.append(link)

        return {
            'emails': all_emails,
            'facebook': all_facebook
        }

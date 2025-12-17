import asyncio
import aiohttp
import logging
import re
import random
import tldextract
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
from fake_useragent import UserAgent
import time
from typing import List, Set, Dict, Tuple, Optional
from utils import log_filtered_item, normalize_url

class AsyncScraper:
    def __init__(self, config: dict, filters: dict, proxies: List[str] = None):
        self.config = config
        self.filters = filters
        self.proxies = proxies or []
        self.ua = UserAgent()
        self.tld_extractor = tldextract.TLDExtract()

        # Regex Patterns
        # Improved regex to avoid matching things like "user@domain.png" if not desired,
        # but for now we keep it standard and broad to catch everything, then filter.
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

        # Timeout settings
        self.timeout_seconds = self.config.get('request_timeout', 15)
        self.timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        self.max_retries = self.config.get('max_retries_per_url', 2)

    def get_base_domain(self, url: str) -> str:
        """Extract the base domain (SLD + TLD) from a URL."""
        ext = self.tld_extractor(url)
        if ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
        return ext.domain

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
        """Check if email is valid based on filters and syntax."""

        # 1. Basic length check
        if len(email) > 100: return False, "Too long"

        # 2. Basic Syntax Check (Regex)
        # We rely on the regex used during extraction, but double check here.
        if not self.email_pattern.match(email):
            return False, "Invalid syntax"

        email_lower = email.lower()

        # 3. Check for common binary/image extensions that might be mistaken for emails
        # e.g. user@image.png (less common in email regex but possible)
        bad_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.woff', '.ttf']
        if any(email_lower.endswith(ext) for ext in bad_extensions):
            return False, "Invalid extension"

        # 4. Check prefixes
        for prefix in self.filters.get('skip_email_prefixes', []):
            if email_lower.startswith(prefix):
                return False, f"Excluded prefix: {prefix}"

        # 5. Check domains (Junk Domains)
        try:
            domain = email_lower.split('@')[-1]
            if domain in self.filters.get('skip_email_domains', []):
                return False, f"Excluded domain: {domain}"
        except IndexError:
             return False, "Invalid format"

        # 6. Check patterns
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
                min_delay = self.config.get('delay_between_requests_min', 0.1)
                max_delay = self.config.get('delay_between_requests_max', 1.0)
                await asyncio.sleep(random.uniform(min_delay, max_delay))

                proxy = None
                if self.config.get('use_proxies', False) and self.proxies:
                    proxy = random.choice(self.proxies)

                async with session.get(url, headers=self.get_headers(), proxy=proxy, timeout=self.timeout, ssl=self.config.get('verify_ssl', False)) as response:
                    if response.status == 200:
                        content = await response.content.read(5 * 1024 * 1024)
                        try:
                            return content.decode('utf-8', errors='ignore')
                        except Exception:
                            return content.decode('latin-1', errors='ignore')
                    elif response.status in [403, 401, 429]:
                        logging.debug(f"Access denied {response.status} for {url}. Attempt {attempt+1}")
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

    def decode_cloudflare_email(self, encoded_string: str) -> Optional[str]:
        """Decode Cloudflare email protection string."""
        try:
            r = int(encoded_string[:2], 16)
            email = ''.join([chr(int(encoded_string[i:i+2], 16) ^ r) for i in range(2, len(encoded_string), 2)])
            return email
        except Exception:
            return None

    def deobfuscate_text(self, text: str) -> str:
        """Replace common obfuscation patterns with standard characters."""
        # Replace markers
        text = text.replace('[at]', '@').replace('(at)', '@').replace(' at ', '@')
        text = text.replace('[dot]', '.').replace('(dot)', '.').replace(' dot ', '.')

        # Remove spaces around @ and . to fix "user @ domain . com"
        text = re.sub(r'\s*@\s*', '@', text)
        text = re.sub(r'\s*\.\s*', '.', text)

        return text

    def extract_data(self, html: str, base_url: str) -> Dict[str, Set[str]]:
        """Extract emails, Facebook/Social links, and new candidate links from HTML."""
        if not html:
            return {'emails': set(), 'socials': set(), 'links': set(), 'priority_links': set()}

        soup = BeautifulSoup(html, 'lxml')

        # Pre-process for Cloudflare emails
        for cf_email in soup.select('.__cf_email__'):
            if cf_email.get('data-cfemail'):
                decoded = self.decode_cloudflare_email(cf_email.get('data-cfemail'))
                if decoded:
                    cf_email.string = decoded

        text_content = soup.get_text()

        # De-obfuscate text content
        clean_text = self.deobfuscate_text(text_content)

        # 1. Extract Emails
        found_emails = set()
        text_emails = self.email_pattern.findall(clean_text)
        found_emails.update(text_emails)

        for link in soup.select('a[href^="mailto:"]'):
            href = link.get('href', '')
            if href:
                # URL Decode
                href = unquote(href)
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

        # 2. Extract Social Links & Candidate Links
        social_links = set()
        candidate_links = set()
        priority_links = set()

        follow_platforms = self.config.get('booking_platforms_follow', [])
        skip_platforms = self.config.get('booking_platforms_skip', [])
        keywords = self.config.get('link_keywords', [])
        blacklisted = self.config.get('blacklisted_domains', [])

        base_domain = self.get_base_domain(base_url)

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not href:
                continue

            absolute_url = urljoin(base_url, href)
            # Use normalized URL for candidate links to ensure consistency
            absolute_url = normalize_url(absolute_url)
            link_base_domain = self.get_base_domain(absolute_url)

            # Check if it is a blacklisted domain (e.g. facebook, instagram)
            is_blacklisted = False
            for bl_domain in blacklisted:
                if bl_domain in absolute_url:
                     # Check if it is a share link (usually we skip those)
                     if 'share' not in absolute_url and 'sharer' not in absolute_url:
                        social_links.add(absolute_url)
                     is_blacklisted = True
                     break

            if is_blacklisted:
                continue

            # Booking Platforms
            if any(p in absolute_url for p in follow_platforms):
                # Prioritize booking platforms
                priority_links.add(absolute_url)
                continue
            elif any(p in absolute_url for p in skip_platforms):
                # Just log, don't follow
                logging.info(f"Booking platform detected but skipped: {absolute_url}")
                continue

            # Internal Links with Smart Discovery
            # Must be same domain (ignoring www)
            if link_base_domain == base_domain:
                 lower_href = href.lower()
                 link_text = link.get_text().lower()

                 # Smart Link Discovery: Check both href and text for keywords
                 is_priority = False
                 if any(kw in lower_href for kw in keywords) or any(kw in link_text for kw in keywords):
                     is_priority = True

                 if is_priority:
                     priority_links.add(absolute_url)
                 else:
                     candidate_links.add(absolute_url)

        return {
            'emails': valid_emails,
            'socials': social_links,
            'links': candidate_links,
            'priority_links': priority_links
        }

    async def crawl_website(self, session: aiohttp.ClientSession, start_url: str) -> Dict[str, Set[str]]:
        """Crawl the website starting from start_url."""
        if not start_url.startswith(('http://', 'https://')):
            start_url = 'http://' + start_url

        start_url = normalize_url(start_url)

        base_domain = self.get_base_domain(start_url)
        domain_timeout = self.config.get('domain_timeout', 45)
        max_pages = self.config.get('max_pages_per_domain', 15)
        max_emails = self.config.get('max_emails_per_domain', 10)

        visited = set()
        queue = [start_url]

        # Add initial priority paths
        priority_paths = self.config.get('priority_paths', [])
        clean_start = start_url.rstrip('/')
        for path in priority_paths:
            if not path.startswith('/'): path = '/' + path
            queue.append(normalize_url(clean_start + path))

        all_emails = set()
        all_socials = set()
        pages_crawled = 0

        start_time = time.time()

        while queue and pages_crawled < max_pages:
            if time.time() - start_time > domain_timeout:
                logging.info(f"Domain timeout for {base_domain}")
                break

            current_url = queue.pop(0)

            current_url = normalize_url(current_url)

            if current_url in visited:
                continue
            visited.add(current_url)

            # Final check against blacklisted domains before crawling
            should_skip = False
            for bl in self.config.get('blacklisted_domains', []):
                if bl in current_url:
                    should_skip = True
                    break
            if should_skip:
                continue

            logging.debug(f"Crawling {current_url} ({pages_crawled+1}/{max_pages})")

            html = await self.fetch_html(session, current_url)
            pages_crawled += 1

            if html:
                data = self.extract_data(html, current_url)
                all_emails.update(data['emails'])
                all_socials.update(data['socials'])

                if len(all_emails) >= max_emails:
                    logging.info(f"Reached max emails ({max_emails}) for {base_domain}")
                    break

                # Add new discovered links to queue

                # 1. Add Priority Links (Smart Discovery & Booking) to FRONT
                # We add them in reverse order so the first one stays first
                for link in reversed(list(data['priority_links'])):
                     if link not in visited and link not in queue:
                         queue.insert(0, link)

                # 2. Add Normal Links to BACK
                for link in data['links']:
                    if link not in visited and link not in queue:
                        # Safety check: ensure we don't crawl infinite external sites
                        link_base_domain = self.get_base_domain(link)
                        is_same_domain = link_base_domain == base_domain

                        if is_same_domain:
                            queue.append(link)

        return {
            'emails': all_emails,
            'socials': all_socials
        }

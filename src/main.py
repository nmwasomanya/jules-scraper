import asyncio
import aiohttp
import pandas as pd
import logging
import json
import os
import signal
import sys
import time
from typing import List, Dict, Any
from scraper import AsyncScraper, load_config, load_filters
from utils import setup_logging, log_filtered_item

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    logging.info("Shutdown signal received. Finishing pending tasks...")
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

class ScraperManager:
    def __init__(self):
        self.config = load_config()
        self.filters = load_filters()
        self.logger, self.filtered_logger = setup_logging(self.config)
        self.scraper = AsyncScraper(self.config, self.filters)

        self.checkpoint_file = self.config.get('checkpoint_file', 'data/checkpoint.json')
        self.processed_urls = self.load_checkpoint()
        self.output_file = self.config.get('output_file', 'data/output.csv')
        self.temp_results = []

        # Performance stats
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'emails_found': 0,
            'start_time': time.time()
        }

    def load_checkpoint(self) -> set:
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    return set(json.load(f))
            except json.JSONDecodeError:
                return set()
        return set()

    def save_checkpoint(self):
        with open(self.checkpoint_file, 'w') as f:
            json.dump(list(self.processed_urls), f)

    def load_input(self) -> pd.DataFrame:
        input_path = self.config.get('input_file', 'data/input.csv')
        if not os.path.exists(input_path):
            logging.error(f"Input file not found: {input_path}")
            sys.exit(1)

        if input_path.endswith('.csv'):
            return pd.read_csv(input_path)
        elif input_path.endswith(('.xls', '.xlsx')):
            return pd.read_excel(input_path)
        else:
            logging.error("Unsupported file format. Use CSV or Excel.")
            sys.exit(1)

    async def process_row(self, session: aiohttp.ClientSession, row: pd.Series, semaphore: asyncio.Semaphore):
        if shutdown_event.is_set():
            return

        async with semaphore:
            # Assuming the URL column is named 'Website' or similar.
            # We'll try to find a column that looks like a URL.
            url_col = None
            for col in row.index:
                if 'website' in col.lower() or 'url' in col.lower() or 'link' in col.lower():
                    url_col = col
                    break

            if not url_col:
                # Fallback: check first column
                url_col = row.index[0]

            url = str(row[url_col]).strip()

            if not url or pd.isna(url):
                return

            # Check checkpoint
            if url in self.processed_urls:
                return

            # Check filters (Domain level)
            should_scrape, reason = self.scraper.should_scrape_domain(url)
            if not should_scrape:
                log_filtered_item('Domain', url, reason)
                self.stats['skipped'] += 1
                self.processed_urls.add(url)
                return

            try:
                html = await self.scraper.fetch_html(session, url)
                if html:
                    data = self.scraper.extract_data(html, url)
                    self.stats['success'] += 1
                    self.stats['emails_found'] += len(data['emails'])

                    self.process_results(row, data)
                else:
                    self.stats['failed'] += 1
                    # Still mark as processed to avoid retry loops on dead sites
            except Exception as e:
                logging.error(f"Error processing {url}: {e}")
                self.stats['failed'] += 1
            finally:
                self.processed_urls.add(url)
                self.stats['total'] += 1

    def process_results(self, original_row: pd.Series, data: dict):
        emails = list(data['emails'])
        facebook_links = list(data['facebook'])

        fb_str = ', '.join(facebook_links)

        # Row Explosion Logic
        if not emails:
            # No emails found: 1 row
            new_row = original_row.to_dict()
            new_row['Extracted Emails'] = ''
            new_row['Facebook Links'] = fb_str
            self.temp_results.append(new_row)
        else:
            # Multiple emails: multiple rows
            for email in emails:
                new_row = original_row.to_dict()
                new_row['Extracted Emails'] = email
                new_row['Facebook Links'] = fb_str
                self.temp_results.append(new_row)

    def flush_results(self):
        if not self.temp_results:
            return

        df = pd.DataFrame(self.temp_results)

        # Append to CSV
        header = not os.path.exists(self.output_file)
        df.to_csv(self.output_file, mode='a', header=header, index=False)

        logging.info(f"Flushed {len(self.temp_results)} rows to {self.output_file}")
        self.temp_results = []
        self.save_checkpoint()

    async def run(self):
        df = self.load_input()
        logging.info(f"Loaded {len(df)} rows from input.")

        # Create TCPConnector with limits
        # We limit the pool size but rely on Semaphore for concurrency control
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=None) # We handle individual request timeouts

        concurrency = self.config.get('max_concurrent_requests', 20)
        semaphore = asyncio.Semaphore(concurrency)

        save_freq = self.config.get('save_frequency', 50)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            for i, (_, row) in enumerate(df.iterrows()):
                if shutdown_event.is_set():
                    break

                task = asyncio.create_task(self.process_row(session, row, semaphore))
                tasks.append(task)

                # Batch processing to manage memory and saves
                if len(tasks) >= concurrency * 2:
                     # Wait for some tasks to finish before adding more to avoid huge queue
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)

                # Periodic Save
                if self.stats['total'] > 0 and self.stats['total'] % save_freq == 0:
                     self.flush_results()

            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks)

        self.flush_results()
        self.save_checkpoint()

        elapsed = time.time() - self.stats['start_time']
        logging.info(f"Scraping completed in {elapsed:.2f}s.")
        logging.info(f"Stats: {self.stats}")

if __name__ == "__main__":
    manager = ScraperManager()
    asyncio.run(manager.run())

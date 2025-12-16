import logging
import os
import sys
import yaml
import json
from urllib.parse import urlparse, urlunparse

def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"{path} not found, using defaults")
        return {}

def load_filters(path: str = "filters.json") -> dict:
    """Load filters from JSON file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"{path} not found, using defaults")
        return {}

def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    - Lowercase scheme and host
    - Strip fragment
    - Strip trailing slash from path (unless root)
    """
    if not url:
        return ""

    u = urlparse(url)

    scheme = u.scheme.lower() if u.scheme else 'http'
    netloc = u.netloc.lower()
    path = u.path

    # Strip trailing slash
    if path and path.endswith('/'):
        path = path.rstrip('/')

    # Reconstruct, ignoring fragment (last element is empty string)
    return urlunparse((scheme, netloc, path, u.params, u.query, ''))

def setup_logging(config: dict):
    """Setup logging configuration."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(c_handler)

    # Error File Handler
    error_log_path = config.get('error_log', 'logs/error.log')
    try:
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        f_handler = logging.FileHandler(error_log_path)
        f_handler.setLevel(logging.ERROR)
        f_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(f_handler)
    except Exception as e:
        print(f"Failed to setup error log: {e}")

    # Filtered Items Logger (Separate logger)
    filtered_logger = logging.getLogger('filtered_items')
    filtered_logger.setLevel(logging.INFO)
    filtered_logger.propagate = False # Don't send to root logger

    if filtered_logger.hasHandlers():
        filtered_logger.handlers.clear()

    filtered_log_path = config.get('filtered_items_log', 'logs/filtered_items.log')
    try:
        os.makedirs(os.path.dirname(filtered_log_path), exist_ok=True)
        filtered_handler = logging.FileHandler(filtered_log_path)
        filtered_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        filtered_logger.addHandler(filtered_handler)
    except Exception as e:
        print(f"Failed to setup filtered log: {e}")

    return logger, filtered_logger

def log_filtered_item(item_type: str, value: str, reason: str):
    """Log a filtered item to the specific log file."""
    logger = logging.getLogger('filtered_items')
    logger.info(f"[{item_type}] {value} - Reason: {reason}")

import logging
import os
import sys

def setup_logging(config: dict):
    """Setup logging configuration."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Console Handler
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(c_handler)

    # Error File Handler
    error_log_path = config.get('error_log', 'logs/error.log')
    os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
    f_handler = logging.FileHandler(error_log_path)
    f_handler.setLevel(logging.ERROR)
    f_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(f_handler)

    # Filtered Items Logger (Separate logger)
    filtered_logger = logging.getLogger('filtered_items')
    filtered_logger.setLevel(logging.INFO)
    filtered_logger.propagate = False # Don't send to root logger

    filtered_log_path = config.get('filtered_items_log', 'logs/filtered_items.log')
    os.makedirs(os.path.dirname(filtered_log_path), exist_ok=True)
    filtered_handler = logging.FileHandler(filtered_log_path)
    filtered_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    filtered_logger.addHandler(filtered_handler)

    return logger, filtered_logger

def log_filtered_item(item_type: str, value: str, reason: str):
    """Log a filtered item to the specific log file."""
    logger = logging.getLogger('filtered_items')
    logger.info(f"[{item_type}] {value} - Reason: {reason}")

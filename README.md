# High-Performance Web Scraper

This is a production-ready, asynchronous web scraper designed to process thousands of websites to extract emails and Facebook links. It is optimized for Digital Ocean droplets and high concurrency.

## Features

- **High Performance**: Uses `aiohttp` and `asyncio` for non-blocking I/O. Capable of handling 150+ concurrent requests.
- **Deep Crawling**: Automatically crawls priority pages (`/contact`, `/about`, `/book`, etc.) to find hidden contact info.
- **Smart Detection**: Detects and follows booking platforms (Square, Calendly, etc.) to extract emails from them.
- **Resilient**: Includes retries, exponential backoff, and strict timeouts to prevent hanging.
- **Row Explosion**: Automatically creates separate rows for each extracted email while preserving original data.
- **Filtering**: Robust filtering system to exclude domains (.edu, .gov) and ignore placeholder emails.
- **Checkpointing**: Saves progress automatically and resumes from where it left off.
- **Multi-Sheet Output**: Generates an Excel file with "Emails Found" and "No Emails" sheets.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd scraper
    ```

2.  **Run the setup script** (for Digital Ocean / Linux):
    This script installs system dependencies, creates a virtual environment, and tunes system limits (ulimit).
    ```bash
    sudo ./setup_droplet.sh
    ```

    *Alternatively, for manual setup:*
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

## Configuration

Edit `config.yaml` to adjust settings:

```yaml
max_concurrent_requests: 20   # Increase to 100-200 on a good server
request_timeout: 15           # Strict timeout per request
domain_timeout: 45            # Max time to spend on one website
max_pages_per_domain: 15      # Max pages to crawl per website
input_file: "data/input.csv"
output_file: "data/output.xlsx"
priority_paths: ["/contact", "/about", ...]
```

Edit `filters.json` to manage exclusion rules:

```json
{
  "skip_domain_extensions": [".edu", ".gov"],
  "skip_email_prefixes": ["noreply@", "admin@"]
}
```

## Usage

1.  **Prepare Input Data**:
    Place your CSV or Excel file in `data/input.csv`. It should have a column containing URLs (e.g., "Website").

2.  **Run the Scraper**:
    ```bash
    ./run.sh
    ```

    Or as a background service (if setup via `setup_droplet.sh`):
    ```bash
    systemctl start scraper
    ```

3.  **Monitor Progress**:
    -   Standard logs: `scraper.log` (stdout)
    -   Error logs: `logs/error.log`
    -   Filtered items: `logs/filtered_items.log`

4.  **Results**:
    Output is saved to `data/output.xlsx`.

## Troubleshooting

-   **Too many open files**: ensure you ran `setup_droplet.sh` or increased `ulimit -n 65535`.
-   **Memory issues**: Reduce `max_concurrent_requests` in `config.yaml`.
-   **Resume**: If the process stops, just run it again. It will skip URLs listed in `data/checkpoint.json`.

## License

Proprietary.

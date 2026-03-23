# URL Status Checker

A fast, async Python script for bulk checking URL status codes. Perfect for validating large lists of URLs (e.g., backlinks, client sites, redirects).

## Features

- ✅ Async processing (checks 700+ URLs in minutes)
- 🔄 Automatic retry logic with exponential backoff
- 🌐 Domain-specific rate limiting (won't overwhelm single domains)
- 📊 Progress bar with ETA
- 📁 CSV input/output support
- 📈 Detailed summary reports

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/url-status-checker.git
cd url-status-checker

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. Prepare your URL list

Create a CSV file with URLs in the first column:

```
URL
https://example.com
https://another-site.com
https://third-site.com
```

### 2. Update configuration

Edit the `INPUT_FILE` variable in `url_checker.py`:

```python
INPUT_FILE = "your_urls.csv"
OUTPUT_FILE = "results.csv"
```

### 3. Run the script

```bash
python url_checker.py
```

### 4. Review results

Open `results.csv` to see status codes and error details.

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `TIMEOUT` | 10 | Seconds before request times out |
| `MAX_CONCURRENT` | 50 | Total concurrent requests |
| `REQUESTS_PER_DOMAIN` | 5 | Concurrent requests per domain |
| `MAX_RETRIES` | 3 | Retry attempts for failed URLs |
| `RETRY_DELAY` | 2 | Base delay between retries |

## Output Format

| Column | Description |
|--------|-------------|
| URL | The checked URL |
| Domain | Extracted domain name |
| Status Code | HTTP status (or N/A if failed) |
| Result | Human-readable status |
| Attempts | Number of retry attempts |
| Checked At | Timestamp of check |

## License

MIT License - feel free to use and modify.

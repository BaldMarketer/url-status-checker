#!/usr/bin/env python3
"""
Bulk URL Status Checker - Enhanced Edition
Features: Progress bar, retry logic, domain-specific rate limiting
"""

import asyncio
import aiohttp
import csv
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict
from typing import Optional, Tuple

# Progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("💡 Tip: Install tqdm for progress bars: pip install tqdm")


class URLChecker:
    def __init__(self, timeout=10, max_concurrent=50, max_retries=3, 
                 retry_delay=2, requests_per_domain=5):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.requests_per_domain = requests_per_domain
        self.results = []
        self.domain_semaphores = {}
        self.global_semaphore = None
        
    def get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create a semaphore for a specific domain"""
        if domain not in self.domain_semaphores:
            self.domain_semaphores[domain] = asyncio.Semaphore(self.requests_per_domain)
        return self.domain_semaphores[domain]
    
    async def check_single_url(self, session, url: str, pbar=None) -> Tuple[str, Optional[int], str, int]:
        """
        Check a single URL with retry logic and domain rate limiting
        Returns: (url, status_code, result, attempts_made)
        """
        parsed = urlparse(url)
        domain = parsed.netloc
        domain_sem = self.get_domain_semaphore(domain)
        
        last_error = "UNKNOWN ERROR"
        attempts = 0
        
        for attempt in range(self.max_retries):
            attempts += 1
            
            async with self.global_semaphore:
                async with domain_sem:
                    try:
                        async with session.get(
                            url, 
                            timeout=self.timeout,
                            allow_redirects=True,
                            headers={'User-Agent': 'Mozilla/5.0 (compatible; URLChecker/1.0)'}
                        ) as response:
                            status = response.status
                            
                            if status == 200:
                                result = "OK"
                            elif status in [301, 302, 303, 307, 308]:
                                result = f"REDIRECT ({status})"
                            elif status == 404:
                                result = "NOT FOUND (404)"
                            elif status == 403:
                                result = "FORBIDDEN (403)"
                            elif status >= 500:
                                result = f"SERVER ERROR ({status})"
                            else:
                                result = f"HTTP {status}"
                            
                            if pbar:
                                pbar.update(1)
                            
                            return url, status, result, attempts
                            
                    except asyncio.TimeoutError:
                        last_error = "TIMEOUT"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            
                    except aiohttp.ClientConnectorError:
                        last_error = "CONNECTION FAILED"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            
                    except aiohttp.ClientResponseError as e:
                        last_error = f"HTTP ERROR {e.status}"
                        # Don't retry client errors (4xx)
                        if 400 <= e.status < 500:
                            if pbar:
                                pbar.update(1)
                            return url, e.status, last_error, attempts
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            
                    except aiohttp.ClientError as e:
                        last_error = f"CLIENT ERROR: {type(e).__name__}"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                            
                    except Exception as e:
                        last_error = f"UNEXPECTED: {str(e)[:50]}"
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        # All retries exhausted
        if pbar:
            pbar.update(1)
        return url, None, f"{last_error} (after {attempts} attempts)", attempts
    
    async def check_all_urls(self, urls: list):
        """Check all URLs with progress tracking"""
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=self.timeout * 2)
        
        self.global_semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Setup progress bar
        if HAS_TQDM:
            pbar = tqdm(total=len(urls), desc="🔍 Checking URLs", unit="url", 
                       bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
        else:
            pbar = None
            print(f"⏳ Checking {len(urls)} URLs...")
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [self.check_single_url(session, url, pbar) for url in urls]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            self.results = []
            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    self.results.append((urls[i], None, f"EXCEPTION: {result}", 0))
                else:
                    self.results.append(result)
        
        if pbar:
            pbar.close()
    
    def save_to_csv(self, output_file: str = "url_check_results.csv"):
        """Save results to CSV with retry info"""
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['URL', 'Domain', 'Status Code', 'Result', 'Attempts', 'Checked At'])
            
            for url, status, result, attempts in self.results:
                domain = urlparse(url).netloc
                writer.writerow([
                    url, 
                    domain,
                    status if status else "N/A", 
                    result, 
                    attempts,
                    datetime.now().isoformat()
                ])
        
        print(f"\n✅ Results saved to: {output_file}")
    
    def print_summary(self):
        """Print detailed summary"""
        total = len(self.results)
        ok_count = sum(1 for _, status, _, _ in self.results if status == 200)
        redirects = sum(1 for _, _, result, _ in self.results if "REDIRECT" in result)
        not_found = sum(1 for _, _, result, _ in self.results if "NOT FOUND" in result or "404" in result)
        timeouts = sum(1 for _, _, result, _ in self.results if "TIMEOUT" in result)
        connection_failed = sum(1 for _, _, result, _ in self.results if "CONNECTION" in result)
        other_errors = total - ok_count - redirects - not_found - timeouts - connection_failed
        
        retried = sum(1 for _, _, _, attempts in self.results if attempts > 1)
        
        print(f"\n{'═' * 50}")
        print(f"📊 RESULTS SUMMARY")
        print(f"{'═' * 50}")
        print(f"   Total URLs:           {total:>6}")
        print(f"   ─────────────────────────────")
        print(f"   ✅ Working (200):     {ok_count:>6}")
        print(f"   ↪️  Redirects:         {redirects:>6}")
        print(f"   ❌ Not Found (404):   {not_found:>6}")
        print(f"   ⏱️  Timeouts:          {timeouts:>6}")
        print(f"   🔌 Connection Failed: {connection_failed:>6}")
        print(f"   ⚠️  Other Errors:      {other_errors:>6}")
        print(f"   ─────────────────────────────")
        print(f"   🔄 Retried URLs:      {retried:>6}")
        print(f"   📈 Success Rate:      {(ok_count/total)*100:>5.1f}%" if total > 0 else "   N/A")
        print(f"{'═' * 50}")
        
        # Show domains with most failures
        domain_failures = defaultdict(int)
        for url, status, _, _ in self.results:
            if status != 200:
                domain = urlparse(url).netloc
                domain_failures[domain] += 1
        
        if domain_failures:
            print(f"\n🔴 Top Domains with Failures:")
            for domain, count in sorted(domain_failures.items(), key=lambda x: -x[1])[:5]:
                print(f"   {domain}: {count} failures")


def load_urls_from_csv(input_file: str) -> list:
    """Load URLs from CSV (assumes URL in first column)"""
    urls = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header if exists
        
        for row in reader:
            if row and row[0].strip():
                url = row[0].strip()
                if url.startswith(('http://', 'https://')):
                    urls.append(url)
                elif not url.lower() in ['url', 'urls', 'link', 'links']:
                    print(f"⚠️  Skipping invalid URL: {url[:50]}...")
    return urls


def load_urls_from_txt(input_file: str) -> list:
    """Load URLs from plain text file"""
    with open(input_file, 'r', encoding='utf-8') as f:
        return [
            line.strip() for line in f 
            if line.strip() and line.strip().startswith(('http://', 'https://'))
        ]


async def main():
    # ═════════════════════════════════════════════════════
    # CONFIGURATION - Edit these values as needed
    # ═════════════════════════════════════════════════════
    INPUT_FILE = "urls_to_check.csv"
    OUTPUT_FILE = "url_check_results.csv"
    
    # Performance settings
    TIMEOUT = 10              # Seconds per request
    MAX_CONCURRENT = 50       # Total concurrent requests
    REQUESTS_PER_DOMAIN = 5   # Concurrent requests per domain
    
    # Retry settings
    MAX_RETRIES = 3           # Attempts per URL
    RETRY_DELAY = 2           # Base delay between retries (multiplied by attempt)
    # ═════════════════════════════════════════════════════
    
    # Load URLs
    input_path = Path(INPUT_FILE)
    if not input_path.exists():
        print(f"❌ Input file not found: {INPUT_FILE}")
        print(f"   Create a CSV with URLs in the first column.")
        sys.exit(1)
    
    print(f"📂 Loading URLs from: {INPUT_FILE}")
    
    if input_path.suffix == '.csv':
        urls = load_urls_from_csv(INPUT_FILE)
    else:
        urls = load_urls_from_txt(INPUT_FILE)
    
    if not urls:
        print("❌ No valid URLs found in input file.")
        sys.exit(1)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    duplicates = 0
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
        else:
            duplicates += 1
    
    urls = unique_urls
    
    print(f"✅ Loaded {len(urls)} unique URLs ({duplicates} duplicates removed)")
    print(f"\n⚙️  Settings:")
    print(f"   Timeout: {TIMEOUT}s | Concurrent: {MAX_CONCURRENT} | Per-domain: {REQUESTS_PER_DOMAIN}")
    print(f"   Retries: {MAX_RETRIES} | Retry delay: {RETRY_DELAY}s")
    print()
    
    # Run checker
    checker = URLChecker(
        timeout=TIMEOUT,
        max_concurrent=MAX_CONCURRENT,
        max_retries=MAX_RETRIES,
        retry_delay=RETRY_DELAY,
        requests_per_domain=REQUESTS_PER_DOMAIN
    )
    
    await checker.check_all_urls(urls)
    
    # Save and summarize
    checker.save_to_csv(OUTPUT_FILE)
    checker.print_summary()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Partial results may be incomplete.")
        sys.exit(130)

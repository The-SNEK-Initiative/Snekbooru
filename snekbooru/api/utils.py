import re
import os
import time
import requests
import cloudscraper

from snekbooru.common.constants import USER_AGENT

_FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "http://localhost:8191")
_cf_bypass_cache = {}

def _flaresolverr_solve(url, timeout=60):
    try:
        import json
        r = requests.post(
            f"{_FLARESOLVERR_URL}/v1",
            json={"cmd": "request.get", "url": url, "maxTimeout": str(timeout * 1000)},
            timeout=timeout + 10,
        )
        r.raise_for_status()
        data = r.json()
        solution = data.get("solution", {})
        if solution.get("status") == 200:
            return {
                "user_agent": solution.get("userAgent", USER_AGENT),
                "cookies": {c["name"]: c["value"] for c in solution.get("cookies", [])},
                "response": solution.get("response", ""),
            }
    except Exception:
        pass
    return None


def http_get(url, params=None, auth=None, custom_headers=None):
    headers = {"User-Agent": USER_AGENT}
    if custom_headers:
        headers.update(custom_headers)

    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    cf_entry = _cf_bypass_cache.get(domain)
    if cf_entry and cf_entry.get("expires", 0) > time.time():
        if cf_entry.get("headers"):
            headers.update(cf_entry["headers"])

    last_error = None
    for attempt in range(3):
        try:
            if auth and isinstance(auth, tuple):
                r = requests.get(url, params=params, headers=headers, timeout=30, auth=auth)
            else:
                r = requests.get(url, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            if not r.content: return []
            return r.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.SSLError,
                requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
            last_error = e
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
            continue
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 503):
                last_error = e
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                continue
            raise

    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        if auth and isinstance(auth, tuple):
            r2 = scraper.get(url, params=params, headers=headers, timeout=60, auth=auth)
        else:
            r2 = scraper.get(url, params=params, headers=headers, timeout=60)
        r2.raise_for_status()
        if not r2.content: return []
        return r2.json()
    except Exception:
        pass

    fs_result = _flaresolverr_solve(url)
    if fs_result and fs_result.get("response"):
        try:
            import json
            data = json.loads(fs_result["response"])
            _cf_bypass_cache[domain] = {
                "expires": time.time() + 1800,
                "headers": {"User-Agent": fs_result["user_agent"]},
                "cookies": fs_result.get("cookies", {}),
            }
            return data
        except Exception:
            pass

    if last_error:
        raise last_error
    return []

def scrape_post_count(url, scrape_method):
    last_error = None
    for attempt in (1, 2):
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            r = scraper.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            r.raise_for_status()
            text = r.text

            if scrape_method == 'serving_text':
                match = re.search(r'Serving ([\d,]+) posts', text, re.IGNORECASE)
                if match: return int(match.group(1).replace(',', ''))
            elif scrape_method == 'posts_link':
                match = re.search(r'Posts</a> \(([\d,]+)\)', text)
                if match: return int(match.group(1).replace(',', ''))
            return 0
        except Exception as e:
            last_error = e
            print(f"Failed to scrape post count from {url} (attempt {attempt}): {e}")
            time.sleep(0.5)
    return 0
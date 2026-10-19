import re
import os
import time
import hashlib
import requests
import cloudscraper

from snekbooru.common.constants import USER_AGENT
from snekbooru.common.constants import RULE34_POSTS

_FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "http://localhost:8191")
_cf_bypass_cache = {}
_verification_cache = {}
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


def _is_verification_page(r):
    try:
        if "json" in (r.headers.get("content-type") or ""):
            return False
        return "const challenge_id" in (r.text or "")
    except Exception:
        return False


def _solve_verification_challenge(r):
    text = r.text or ""

    def grab(name):
        m = re.search(r'const %s = "([^"]*)"' % name, text)
        return m.group(1) if m else None

    challenge_id = grab("challenge_id")
    generated = grab("challenge_generated")
    expires = grab("challenge_cookie_expires")
    seed = grab("powSeed")
    if not (challenge_id and generated and expires and seed):
        return None

    m = re.search(r'const powPrefix = "0"\.repeat\((\d+)\)', text)
    prefix = "0" * (int(m.group(1)) if m else 5)
    md = re.search(r"const delay = ([\d.]+);", text)
    delay = float(md.group(1)) if md else 5.0

    started = time.time()
    nonce = 0
    while True:
        pow_hash = hashlib.sha1(("%s:%d" % (seed, nonce)).encode()).hexdigest()
        if pow_hash.startswith(prefix):
            break
        nonce += 1

    remaining = delay - (time.time() - started)
    if remaining > 0:
        time.sleep(remaining)

    from urllib.parse import urlsplit
    parts = urlsplit(r.url)
    origin = "%s://%s" % (parts.scheme, parts.netloc)
    payload = {
        "challenge_id": challenge_id,
        "challenge_generated": generated,
        "challenge_cookie_expires": expires,
        "pow_nonce": str(nonce),
        "pow_hash": pow_hash,
    }
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Verification-Challenge": "1",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referer": r.url,
        "Origin": origin,
    }
    try:
        pr = requests.post(origin + "/", json=payload, headers=headers, timeout=30)
    except requests.RequestException:
        return None
    jar = requests.utils.dict_from_cookiejar(pr.cookies)
    if "atf-anti-bot" not in jar:
        return None
    return {"cookies": jar, "expires": float(expires)}


def verification_get(url, headers=None, auth=None, timeout=30, params=None):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    cache = _verification_cache.get(domain)
    cookies = None
    if cache and cache.get("expires", 0) > time.time():
        cookies = cache.get("cookies")

    try:
        r = requests.get(url, params=params, headers=headers, cookies=cookies,
                         timeout=timeout, auth=auth)
    except requests.RequestException:
        return None
    if not _is_verification_page(r):
        return r

    solution = _solve_verification_challenge(r)
    if solution:
        _verification_cache[domain] = solution
        r = requests.get(url, params=params, headers=headers,
                         cookies=solution["cookies"], timeout=timeout, auth=auth)
    return r

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
    cookies = None
    if cf_entry and cf_entry.get("expires", 0) > time.time():
        cookies = cf_entry.get("cookies")
        if cf_entry.get("headers"):
            headers.update(cf_entry["headers"])

    last_error = None
    for attempt in range(3):
        try:
            if auth and isinstance(auth, tuple):
                r = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=30, auth=auth)
            else:
                r = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=30)
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
            r2 = scraper.get(url, params=params, headers=headers, cookies=cookies, timeout=60, auth=auth)
        else:
            r2 = scraper.get(url, params=params, headers=headers, cookies=cookies, timeout=60)
        r2.raise_for_status()
        if not r2.content: return []
        return r2.json()
    except Exception:
        pass

    request_url = requests.Request("GET", url, params=params).prepare().url
    fs_result = _flaresolverr_solve(request_url) if not auth else None
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

def rule34_post_count(credentials):
    user_id = str(credentials.get("user_id") or "").strip()
    api_key = str(credentials.get("api_key") or "").strip()
    if not user_id or not api_key:
        return None
    import xml.etree.ElementTree as ET
    try:
        response = requests.get(
            RULE34_POSTS,
            params={"limit": 1, "pid": 0, "user_id": user_id, "api_key": api_key},
            headers={"User-Agent": USER_AGENT}, timeout=(5, 15),
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        count = root.get("count") if root.tag == "posts" else None
        return int(count) if count is not None and str(count).isdigit() else None
    except (requests.RequestException, ET.ParseError, ValueError, TypeError):
        return None


def scrape_post_count(url, scrape_method):
    from urllib.parse import urlparse
    if urlparse(url).hostname in ("rule34.xxx", "www.rule34.xxx", "api.rule34.xxx"):
        from snekbooru.core.config import SETTINGS
        return rule34_post_count(SETTINGS.get("rule34", {}))
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
            return None
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403, 404):
                return None
        except requests.RequestException:
            pass
        if attempt == 1:
            time.sleep(0.5)
    return None

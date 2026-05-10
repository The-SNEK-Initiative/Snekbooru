import re
import requests
import cloudscraper

from snekbooru.common.constants import USER_AGENT


def http_get(url, params=None, auth=None, custom_headers=None):
    headers = {"User-Agent": USER_AGENT}
    if custom_headers:
        headers.update(custom_headers)

    if auth and isinstance(auth, tuple):
        r = requests.get(url, params=params, headers=headers, timeout=30, auth=auth)
    else:
        r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    if not r.content: return [] 
    return r.json()

def scrape_post_count(url, scrape_method):
    try:
        scraper = cloudscraper.create_scraper()
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
        print(f"Failed to scrape post count from {url}: {e}")
        return 0
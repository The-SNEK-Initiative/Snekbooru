import random
import re
import json
import urllib.parse
import xml.etree.ElementTree as ET
import time


def filter_posts_by_blacklist(posts, blacklisted_tags):
    """Filter out posts that contain any blacklisted tags."""
    if not blacklisted_tags:
        return posts
    
    filtered = []
    blacklist_set = set(t.lower() for t in blacklisted_tags if t)
    
    for post in posts:
        tags = post.get("tags", "").lower()
        tags_set = set(tags.split())
        
        # If any blacklisted tag is in the post's tags, skip it
        if not tags_set.intersection(blacklist_set):
            filtered.append(post)
    
    return filtered
import requests

from snekbooru_linux.api.utils import http_get
from snekbooru_linux.common.constants import (DANBOORU_COUNTS_POSTS, DANBOORU_POSTS,
                                        DANBOORU_RANDOM, DANBOORU_TAGS,
                                        GELBOORU_POSTS, GELBOORU_TAGS,
                                        HYPNOHUB_POSTS, HYPNOHUB_TAGS,
                                        KONACHAN_POSTS, KONACHAN_TAGS,
                                        RULE34_POSTS, RULE34_TAGS,
                                        WAIFU_PICS_API,
                                        WAIFU_PICS_NSFW_CATEGORIES,
                                        WAIFU_PICS_SFW_CATEGORIES,
                                        YANDERE_POSTS, YANDERE_TAGS,
                                        ZEROCHAN_API)
from snekbooru_linux.core.config import SETTINGS

def _get_blacklist_tags():
    """Retrieves and normalizes blacklist tags from settings."""
    blacklisted = SETTINGS.get("blacklisted_tags", "").split()
    return [tag.strip().lower() for tag in blacklisted if tag.strip()]

def _get_content_filter_tags():
    """Gets tags to filter based on content settings."""
    filter_tags = set()
    if not SETTINGS.get("allow_loli_shota", False):
        filter_tags.update(["loli", "shota"])
    if not SETTINGS.get("allow_bestiality", False):
        filter_tags.add("bestiality")
    if not SETTINGS.get("allow_guro", False):
        filter_tags.update(["guro", "gore", "blood", "injury"])
    return filter_tags

def _is_rating_allowed(post):
    """Checks if post rating is allowed based on settings."""
    rating = post.get("rating", "").lower()
    
    # Allow safe/unknown ratings always
    if rating in ["safe", "unknown", ""]:
        return True
    
    # Check explicit setting
    if not SETTINGS.get("allow_explicit", False):
        return False
    
    return True

def _post_should_be_filtered(post, blacklist_tags, content_filter_tags):
    """Determines if a post should be filtered out based on all criteria."""
    # Check rating first
    if not _is_rating_allowed(post):
        return True
    
    # Get post tags (handle both 'tags' and 'tag_string' fields)
    post_tags_str = post.get("tags", "") or post.get("tag_string", "")
    post_tags_lower = {tag.lower() for tag in post_tags_str.split()}
    
    # Check blacklist
    if blacklist_tags and any(bl_tag in post_tags_lower for bl_tag in blacklist_tags):
        return True
    
    # Check content filters
    if content_filter_tags and any(cf_tag in post_tags_lower for cf_tag in content_filter_tags):
        return True
    
    return False

def _filter_posts(posts):
    """Applies all filtering rules to posts (rating, blacklist, content filters)."""
    blacklist = _get_blacklist_tags()
    content_filters = _get_content_filter_tags()
    
    return [p for p in posts if not _post_should_be_filtered(p, blacklist, content_filters)]

# Gelbooru

def gelbooru_posts(tags, limit, pid):
    params = {"tags": tags}
    gb = SETTINGS.get("gelbooru", {})
    if gb.get("user_id") and gb.get("api_key"):
        params["user_id"] = gb["user_id"]
        params["api_key"] = gb["api_key"]

    total_count = 0
    # Request more posts to account for filtering (3x to be safe)
    fetch_limit = limit * 3
    params.update({"limit": fetch_limit, "pid": pid})
    data = http_get(GELBOORU_POSTS, params=params)
    if "@attributes" in data and "count" in data["@attributes"]:
        try: total_count = int(data["@attributes"]["count"])
        except (ValueError, TypeError): pass
    all_posts_raw = data.get("post", [])

    posts = all_posts_raw
    if isinstance(posts, dict):
        posts = [posts]
    
    norm = []
    for p in posts:
        norm.append({
            "id": str(p.get("id")),
            "preview_url": p.get("preview_url") or p.get("sample_url") or p.get("file_url"),
            "file_url": p.get("file_url"),
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={p.get('id')}",
            "file_ext": p.get("file_url", "").split('.')[-1].lower() if p.get("file_url") else ""
        })
    
    norm = _filter_posts(norm)
    # Return up to the requested limit
    return norm[:limit], total_count

def gelbooru_tags_like(pattern, limit=20):
    params = {"name_pattern": pattern, "limit": limit}
    gb = SETTINGS.get("gelbooru", {})
    if gb.get("user_id") and gb.get("api_key"):
        params["user_id"] = gb["user_id"]
        params["api_key"] = gb["api_key"]
    data = http_get(GELBOORU_TAGS, params=params)
    tags = data.get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]
    return [t.get("name") for t in tags if t.get("name")]

# Danbooru

def danbooru_auth():
    db = SETTINGS.get("danbooru", {})
    if db.get("login") and db.get("api_key"):
        return (db["login"], db["api_key"])
    return None


def danbooru_posts(tags, limit, page):
    auth_tuple = danbooru_auth()

    # Danbooru requires at least one positive tag. If only negative tags are present,
    # the API returns a 422 error. We add 'order:rank' as a default to show popular posts.
    tag_parts = tags.split()
    has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
    if not has_positive_tag:
        tags += " order:rank"

    # Get total count for pagination display
    total_count = 0
    try:
        count_params = {"tags": tags}
        count_data = http_get(DANBOORU_COUNTS_POSTS, params=count_params, auth=auth_tuple)
        total_count = count_data.get("counts", {}).get("posts", 0)
    except Exception:
        pass # Fail gracefully, we just won't show the total pages

    params = {"tags": tags, "limit": limit, "page": page + 1}
    all_posts_raw = http_get(DANBOORU_POSTS, params=params, auth=auth_tuple)

    data = all_posts_raw
    
    norm = []
    for p in data:
        if not p.get("file_url"):
            continue
        norm.append({
            "id": str(p.get("id")),
            "preview_url": p.get("preview_file_url") or p.get("file_url"),
            "file_url": p.get("file_url"),
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tag_string", ""),
            "source_post_url": f"https://danbooru.donmai.us/posts/{p.get('id')}",
            "file_ext": p.get("file_ext", "").lower()
        })
    
    norm = _filter_posts(norm)
    return norm[:limit], total_count

def danbooru_random(tags):
    # Danbooru requires at least one positive tag. If only negative tags are present,
    # the API returns a 422 error. We add 'order:rank' as a default.
    if tags:
        tag_parts = tags.split()
        has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
        if not has_positive_tag:
            tags += " order:rank"

    params = {"tags": tags} if tags else None
    auth_tuple = danbooru_auth()
    for _ in range(6):
        data = http_get(DANBOORU_RANDOM, params=params, auth=auth_tuple)
        if data and data.get("file_url"):
            return {
                "id": str(data.get("id")),
                "preview_url": data.get("preview_file_url") or data.get("file_url"),
                "file_url": data.get("file_url"),
                "rating": data.get("rating"),
                "score": data.get("score"),
                "tags": data.get("tag_string", ""),
                "source_post_url": f"https://danbooru.donmai.us/posts/{data.get('id')}",
                "file_ext": data.get("file_ext", "").lower()
            }
    raise RuntimeError("No accessible Danbooru post found.")

def danbooru_tags_like(pattern, limit=20):
    params = {"search[name_matches]": pattern, "limit": min(1000, limit)}
    data = http_get(DANBOORU_TAGS, params=params, auth=danbooru_auth())
    return [t.get("name") for t in data if t.get("name")]

def danbooru_post_count(tags):
    auth_tuple = danbooru_auth()
    try:
        # Danbooru requires at least one positive tag.
        if tags:
            tag_parts = tags.split()
            has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
            if not has_positive_tag:
                tags += " order:rank"

        count_params = {"tags": tags}
        count_data = http_get(DANBOORU_COUNTS_POSTS, params=count_params, auth=auth_tuple)
        return count_data.get("counts", {}).get("posts", 0)
    except Exception:
        return "N/A"

# Konachan
def konachan_posts(tags, limit, page):
    # Konachan uses page numbers starting from 1
    if not SETTINGS.get("allow_explicit", False) and "rating:" not in tags:
        tags += " rating:safe"

    params = {"tags": tags, "limit": limit, "page": page + 1}
    all_posts_raw = http_get(KONACHAN_POSTS, params=params)

    data = all_posts_raw
    norm = []
    for p in data:
        norm.append({
            "id": str(p.get("id")),
            "preview_url": p.get("preview_url") or p.get("sample_url") or p.get("file_url"),
            "file_url": p.get("file_url"),
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://konachan.com/post/show/{p.get('id')}",
            "file_ext": p.get("file_url", "").split('.')[-1].lower() if p.get("file_url") else ""
        })
    
    norm = _filter_posts(norm)
    return norm[:limit], 0

def konachan_tags_like(pattern, limit=20):
    # Konachan tag API uses 'name' for pattern matching, wildcards should be appended
    params = {"name": pattern, "limit": limit}
    data = http_get(KONACHAN_TAGS, params=params)
    return [t.get("name") for t in data if t.get("name")]

# Yandere
def yandere_posts(tags, limit, page):
    # Yandere uses page numbers starting from 1
    params = {"tags": tags, "limit": limit, "page": page + 1}
    all_posts_raw = http_get(YANDERE_POSTS, params=params)

    data = all_posts_raw
    norm = []
    for p in data:
        norm.append({
            "id": str(p.get("id")),
            "preview_url": p.get("preview_url") or p.get("sample_url") or p.get("file_url"),
            "file_url": p.get("file_url"),
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://yande.re/post/show/{p.get('id')}",
            "file_ext": p.get("file_url", "").split('.')[-1].lower() if p.get("file_url") else ""
        })
    
    norm = _filter_posts(norm)
    return norm[:limit], 0

def yandere_tags_like(pattern, limit=20):
    # Yandere tag API uses 'name' for pattern matching, wildcards should be appended
    params = {"name": pattern, "limit": limit}
    data = http_get(YANDERE_TAGS, params=params)
    return [t.get("name") for t in data if t.get("name")]

# Rule34
def rule34_posts(tags, limit, pid):
    params = {"tags": tags, "limit": limit, "pid": pid, "json": 1}
    r34 = SETTINGS.get("rule34", {})
    if r34.get("user_id") and r34.get("api_key"):
        params["user_id"] = r34["user_id"]
        params["api_key"] = r34["api_key"]
    
    data = http_get(RULE34_POSTS, params=params)
    
    if not isinstance(data, list): data = []

    norm = []
    for p in data:
        preview_url = p.get("preview_url")
        if preview_url and preview_url.startswith('//'): preview_url = f"https:{preview_url}"
        
        sample_url = p.get("sample_url")
        if sample_url and sample_url.startswith('//'): sample_url = f"https:{sample_url}"

        file_url = p.get("file_url")
        if file_url and file_url.startswith('//'): file_url = f"https:{file_url}"

        norm.append({
            "id": str(p.get("id")),
            "preview_url": preview_url or sample_url or file_url,
            "file_url": file_url,
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://rule34.xxx/index.php?page=post&s=view&id={p.get('id')}",
            "file_ext": file_url.split('.')[-1].lower().split('?')[0] if file_url else ""
        })
    
    norm = _filter_posts(norm)
    return norm[:limit], 0

def rule34_tags_like(pattern, limit=20):
    """Fetch tag suggestions from Rule34."""
    # Rule34 tag autocomplete API
    params = {"q": pattern}
    data = http_get(RULE34_TAGS, params=params)
    # Response is like [{"label": "tag", "value": "tag"}, ...]
    return [t.get("value") for t in data if t.get("value")][:limit]

# Zerochan
def zerochan_posts(tags, limit, page):
    # Zerochan expects spaces in tags to be replaced by '+'.
    processed_tags = urllib.parse.quote_plus(tags)

    # The API endpoint is different for tagged vs. untagged searches
    if processed_tags:
        url = f"{ZEROCHAN_API}/{processed_tags}"
    else:
        url = f"{ZEROCHAN_API}/"

    custom_headers = {}
    if SETTINGS.get("zerochan_user"):
        from snekbooru_linux.common.constants import USER_AGENT
        custom_headers["User-Agent"] = f"{USER_AGENT} - {SETTINGS['zerochan_user']}"
    else:
        from snekbooru_linux.common.constants import USER_AGENT
        custom_headers["User-Agent"] = f"{USER_AGENT} - Anonymous"

    params = {"p": page + 1, "l": limit, "xml": 1}
    try:
        r = requests.get(url, params=params, headers=custom_headers, timeout=30)
        r.raise_for_status()
        
        root = ET.fromstring(r.content)
        # Namespaces in the RSS feed
        namespaces = {
            'media': 'http://search.yahoo.com/mrss/',
            'atom': 'http://www.w3.org/2005/Atom'
        }
        
        items = root.findall('./channel/item')
        norm = []
        
        for item in items:
            link = item.find('link').text
            post_id = link.split('/')[-1] if link else str(random.randint(100000, 999999))
            
            # Find media:content for the file URL (usually 'sample' size, but better than nothing)
            media_content = item.find('media:content', namespaces)
            file_url = media_content.attrib['url'] if media_content is not None else None
            
            # Find media:thumbnail for preview
            media_thumb = item.find('media:thumbnail', namespaces)
            preview_url = media_thumb.attrib['url'] if media_thumb is not None else None
            
            # Find keywords for tags
            media_keywords = item.find('media:keywords', namespaces)
            tags_text = media_keywords.text if media_keywords is not None else ""
            tags = [t.strip().replace(' ', '_') for t in tags_text.split(',')] if tags_text else []
            
            if file_url:
                norm.append({
                    "id": post_id, 
                    "preview_url": preview_url or file_url, 
                    "file_url": file_url,
                    "rating": "safe", # Zerochan RSS doesn't explicitly state rating easily
                    "score": 0, 
                    "tags": " ".join(tags),
                    "source_post_url": link,
                    "file_ext": file_url.split('.')[-1].lower()
                })
                
        return norm, 0
    except Exception as e:
        print(f"Zerochan fetch error: {e}")
        return [], 0

def zerochan_tags_like(pattern, limit=20):
    # Zerochan API documentation does not specify a tag suggestion endpoint.
    return []

# Hypnohub
def hypnohub_posts(tags, limit, pid):
    # Hypnohub uses a 0-indexed 'pid' for page number
    params = {"tags": tags}
    params.update({"limit": limit, "pid": pid})
    data = http_get(HYPNOHUB_POSTS, params=params)
    all_posts_raw = data if data else []

    data = all_posts_raw
    norm = []
    if not data:
        return [], 0
    for p in data:
        file_url = p.get("file_url")
        if file_url and file_url.startswith('//'):
            file_url = f"https:{file_url}"
        
        preview_url = p.get("preview_url")
        if preview_url and preview_url.startswith('//'):
            preview_url = f"https:{preview_url}"

        norm.append({
            "id": str(p.get("id")),
            "preview_url": preview_url or file_url,
            "file_url": file_url,
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://hypnohub.net/post/show/{p.get('id')}",
            "file_ext": file_url.split('.')[-1].lower() if file_url else ""
        })
    
    norm = _filter_posts(norm)
    return norm[:limit], 0

def waifu_pics_posts(category, limit):
    """
    Fetches posts from waifu.pics using the bulk endpoint.
    """
    import os
    from PyQt5.QtCore import QThread
    from snekbooru_linux.common.constants import USER_AGENT

    is_nsfw = category in WAIFU_PICS_NSFW_CATEGORIES
    
    if is_nsfw and not SETTINGS.get("allow_explicit", False):
        return [], 0 # Don't fetch NSFW if not allowed

    endpoint_type = "nsfw" if is_nsfw else "sfw"
    
    # If no category, pick a random SFW one
    if not category:
        category = random.choice(WAIFU_PICS_SFW_CATEGORIES)

    if category not in WAIFU_PICS_SFW_CATEGORIES and category not in WAIFU_PICS_NSFW_CATEGORIES:
        return [], 0 # Invalid category

    try:
        # The 'many' endpoint returns max 30. We need to call it multiple times to meet the limit.
        num_requests = (limit + 29) // 30 # Ceiling division
        all_img_urls = []
        
        for _ in range(num_requests):
            url = f"{WAIFU_PICS_API}/many/{endpoint_type}/{category}"
            # The API expects a POST request for the 'many' endpoint
            r = requests.post(url, json={}, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            data = r.json()
            all_img_urls.extend(data.get("files", []))
            # Small delay to potentially get different results on next call
            QThread.msleep(50)

        # The API can return duplicates, especially if called quickly. Remove them.
        unique_urls = list(dict.fromkeys(all_img_urls))
        
        img_urls = unique_urls[:limit]
        posts = []
        for img_url in img_urls:
            file_ext = os.path.splitext(img_url)[1][1:].lower() if '.' in os.path.basename(img_url) else 'jpg'
            posts.append({
                "id": f"wp_{os.path.basename(img_url).split('.')[0]}",
                "preview_url": img_url, "file_url": img_url,
                "rating": "explicit" if is_nsfw else "safe", "score": 0, "tags": category,
                "source_post_url": img_url, "file_ext": file_ext
            })
        return posts, len(posts)
    except Exception:
        return [], 0

def hentai_haven_episodes(url):
    """
    Scrapes a Hentai Haven series page to get a list of episodes.
    """
    from bs4 import BeautifulSoup
    from snekbooru_linux.common.constants import USER_AGENT

    try:
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, 'html.parser')
        
        episodes = []
        # Find all list items for chapters/episodes
        episode_items = soup.select('.wp-manga-chapter')

        for item in episode_items:
            link = item.find('a')
            if link and link.has_attr('href'):
                episode_url = link['href']
                episode_title = link.text.strip()
                episodes.append({'title': episode_title, 'url': episode_url})
        
        # The episodes are usually listed in descending order, so we reverse them
        return list(reversed(episodes)), None
    except Exception as e:
        return [], str(e)

def hentai_haven_video_url(episode_url):
    """
    Scrapes a Hentai Haven episode page to get the direct video URL.
    """
    from bs4 import BeautifulSoup
    from snekbooru_linux.common.constants import USER_AGENT

    try:
        headers = {"User-Agent": USER_AGENT}
        # The episode URL often redirects to an 'inter' page first
        r = requests.get(episode_url, headers=headers, timeout=30, allow_redirects=True)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Find the iframe with the player
        iframe = soup.find('iframe', src=lambda s: s and 'player.php' in s)
        if not iframe:
            return None, "Player iframe not found."

        # Now fetch the content of the iframe
        player_r = requests.get(iframe['src'], headers=headers, timeout=30)
        player_r.raise_for_status()
        return player_r.json().get('video'), None
    except Exception as e:
        return None, str(e)

def fetch_multiple_sources(sources, tags, limit, page, custom_boorus):
    """Fetches posts from a list of specified sources and combines them."""
    if not sources:
        return [], 0

    # Distribute the limit among the sources.
    limit_per_source = max(1, limit // len(sources))
    all_posts = []
    total_count = 0 # Not reliably calculable for multi-source

    # This can be parallelized in the future for better performance
    for source_name in sources:
        try:
            if source_name == "Waifu.pics":
                posts, _ = waifu_pics_posts(tags, limit_per_source)
            else:
                posts, _ = _do_fetch_single_source(source_name, tags, limit_per_source, page, custom_boorus)
            all_posts.extend(posts)
        except Exception as e:
            print(f"Failed to fetch from {source_name}: {e}")

    # Interleave results for a mixed feel, or just shuffle
    random.shuffle(all_posts)
    
    # Deduplicate based on file_url
    seen_urls = set()
    unique_posts = []
    for post in all_posts:
        file_url = post.get('file_url')
        if file_url and file_url not in seen_urls:
            unique_posts.append(post)
            seen_urls.add(file_url)
        elif not file_url: # Keep posts without a file_url (e.g., some errors)
            unique_posts.append(post)

    return unique_posts, total_count

def _do_fetch_single_source(source_name, tags, limit, page, custom_boorus):
    """Helper function to call the correct API function for a single source name."""
    # Map source names to their respective API functions
    source_function_map = {
        "Gelbooru": gelbooru_posts,
        "Danbooru": danbooru_posts,
        "Konachan": konachan_posts,
        "Yandere": yandere_posts,
        "Rule34": rule34_posts,
        "Hypnohub": hypnohub_posts,
        "Zerochan": zerochan_posts,
    }

    # Find the correct function to call
    fetch_function = source_function_map.get(source_name)

    if fetch_function:
        # Danbooru uses 'page' (1-indexed), others use 'pid' (0-indexed)
        if source_name == "Danbooru":
            return fetch_function(tags, limit, page)
        else:
            return fetch_function(tags, limit, page) # Most functions use 'page' as 'pid'
    else:
        # Check if it's a custom booru
        custom_booru_config = next((b for b in custom_boorus if b['name'] == source_name), None)
        if custom_booru_config:
            return fetch_custom_booru_posts(custom_booru_config, tags, limit, page)
        else:
            # Fallback for an unknown source name
            raise ValueError(f"Unknown source specified: {source_name}")

def fetch_custom_booru_posts(config, tags, limit, page):
    """A generic function to fetch and parse posts from a custom booru configuration."""
    from snekbooru_linux.common.constants import USER_AGENT
    
    # For Danbooru-like APIs, a positive tag is required. If only negative tags
    # are present, the API returns a 422 error. We add 'order:rank' as a default.
    if "Danbooru" in config.get("response_format", ""):
        tag_parts = tags.split()
        has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
        if not has_positive_tag:
            tags += " order:rank"

    # Handle authentication first - replace credential placeholders before other substitutions
    posts_url = config['posts_url']
    auth = None
    
    # For custom boorus, prioritize custom credentials over the main app's Danbooru auth
    if config.get("username") and config.get("api_key"):
        # Use custom booru credentials
        username = config.get("username", "").strip()
        api_key = config.get("api_key", "").strip()
        # Replace placeholder credentials in URL - support both {login} and {id}/{username}
        posts_url = posts_url.replace('{login}', username).replace('{id}', username).replace('{api_key}', api_key).replace('{username}', username)
    elif config['auth_type'] == "Login & API Key":
        # Fall back to the main app's Danbooru credentials
        auth = danbooru_auth()
    
    # Now replace query parameter placeholders
    posts_url = posts_url.replace('{tags}', tags).replace('{limit}', str(limit)).replace('{pid}', str(page)).replace('{page}', str(page + 1))


    # Make the request
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(posts_url, headers=headers, timeout=30, auth=auth)
    r.raise_for_status()

    # Parse based on format
    response_format = config['response_format']
    if "XML" in response_format:
        root = ET.fromstring(r.content)
        posts_xml = root.findall('post')
        posts = []
        for p_xml in posts_xml:
            posts.append(p_xml.attrib)
        total_count = int(root.attrib.get('count', 0))
    else: # JSON
        posts = r.json()
        total_count = 0 # Most custom JSON APIs won't provide this easily

    # Normalize the data
    norm = []
    if response_format == "Gelbooru JSON":
        if isinstance(posts, dict):
            posts = posts.get("post", [])
        for p in posts:
            norm.append({
                "id": str(p.get("id")), "preview_url": p.get("preview_url"), "file_url": p.get("file_url"),
                "rating": p.get("rating"), "score": p.get("score"), "tags": p.get("tags", ""),
                "source_post_url": f"{config.get('base_url', '')}/index.php?page=post&s=view&id={p.get('id')}",
                "file_ext": p.get("file_url", "").split('.')[-1].lower() if p.get("file_url") else ""
            })
    elif response_format == "Danbooru JSON":
        # Danbooru can return a list directly, or wrapped in a "posts" key (e.g., e621)
        if isinstance(posts, dict):
            posts = posts.get("posts", posts.get("post", []))
        for p in posts:
            # Handle different tag formats: string (Danbooru) or dict with categories (e621)
            tags_str = p.get("tag_string", "")
            if isinstance(p.get("tags"), dict):
                # e621 format: tags are in a dict with categories
                tags_list = []
                for category in ["general", "artist", "copyright", "character", "species"]:
                    tags_list.extend(p.get("tags", {}).get(category, []))
                tags_str = " ".join(tags_list)
            
            # Handle different rating formats
            rating = p.get("rating", "")
            
            # Handle different score formats: int (Danbooru) or dict with up/down/total (e621)
            score = p.get("score", 0)
            if isinstance(score, dict):
                score = score.get("total", 0)
            
            file_url = p.get("file_url") or p.get("file", {}).get("url")
            if not file_url:
                continue
            norm.append({
                "id": str(p.get("id")), 
                "preview_url": p.get("preview_file_url") or p.get("preview", {}).get("url"),
                "file_url": file_url,
                "rating": rating, 
                "score": score, 
                "tags": tags_str,
                "source_post_url": f"{config.get('base_url', '')}/posts/{p.get('id')}",
                "file_ext": p.get("file_ext", p.get("file", {}).get("ext", "")).lower()
            })
    elif response_format == "Rule34 XML":
        for p in posts:
            norm.append({
                "id": str(p.get("id")),
                "preview_url": p.get("preview_url"),
                "file_url": p.get("file_url"),
                "rating": p.get("rating"),
                "score": p.get("score"),
                "tags": p.get("tags", ""),
                "source_post_url": f"{config.get('base_url', '')}/index.php?page=post&s=view&id={p.get('id')}",
                "file_ext": p.get("file_url", "").split('.')[-1].lower() if p.get("file_url") else ""
            })
    
    return norm, total_count

def suggest_custom_booru_tags(config, pattern, limit):
    """Generic function to fetch tag suggestions from a custom booru."""
    if not config.get("tags_url"): return [], None

    tags_url = config['tags_url']
    
    # Handle authentication first - replace credential placeholders before other substitutions
    auth = None
    # For custom boorus, prioritize custom credentials over the main app's Danbooru auth
    if config.get("username") and config.get("api_key"):
        # Use custom booru credentials
        username = config.get("username", "").strip()
        api_key = config.get("api_key", "").strip()
        # Replace placeholder credentials in URL - support both {login} and {id}/{username}
        tags_url = tags_url.replace('{login}', username).replace('{id}', username).replace('{api_key}', api_key).replace('{username}', username)
    elif config['auth_type'] == "Login & API Key":
        # Fall back to the main app's Danbooru credentials
        auth = danbooru_auth()
    
    # Now replace other query parameter placeholders
    tags_url = tags_url.replace('{pattern}', pattern).replace('{limit}', str(limit))

    data = http_get(tags_url, auth=auth)
    
    if config['response_format'] == "Gelbooru JSON":
        tags = data.get("tag", [])
        return [t.get("name") for t in tags if t.get("name")], None
    elif config['response_format'] == "Danbooru JSON":
        return [t.get("name") for t in data if t.get("name")], None
    elif config['response_format'] == "Rule34 XML":
        return [t.get("value") for t in data if t.get("value")], None
    
    return [], "Unsupported tag format"

def suggest_all_tags(pattern, limit=40):
    """Fetches tag suggestions from all booru sources."""
    num_sources = 7 # Added Zerochan
    gel_limit = limit // num_sources
    dan_limit = limit // num_sources
    kona_limit = limit // num_sources
    yandere_limit = limit // num_sources
    r34_limit = limit // num_sources
    hypno_limit = limit - (gel_limit + dan_limit + kona_limit + yandere_limit + r34_limit)
    
    gel_tags, dan_tags, kona_tags, yandere_tags, r34_tags, hypno_tags, zero_tags = [], [], [], [], [], [], []
    try: gel_tags = gelbooru_tags_like(pattern, gel_limit)
    except Exception: pass
    try:
        patt = pattern if "*" in pattern else (pattern + "*")
        dan_tags = danbooru_tags_like(patt, dan_limit)
    except Exception: pass
    try:
        # Konachan uses a wildcard at the end for pattern matching
        patt = pattern if pattern.endswith('*') else pattern + '*'
        kona_tags = konachan_tags_like(patt, kona_limit)
    except Exception: pass
    try:
        # Yandere uses a wildcard at the end for pattern matching
        patt = pattern if pattern.endswith('*') else pattern + '*'
        yandere_tags = yandere_tags_like(patt, yandere_limit)
    except Exception: pass
    try:
        r34_tags = rule34_tags_like(pattern, r34_limit)
    except Exception: pass
    try:
        # Hypnohub dapi does not support tag searching by name
        hypno_tags = hypnohub_tags_like(pattern, hypno_limit)
    except Exception: pass
    try:
        zero_tags = zerochan_tags_like(pattern, 0) # No limit param, no suggestions
    except Exception: pass
    
    combined = gel_tags + dan_tags + kona_tags + yandere_tags + r34_tags + hypno_tags + zero_tags
    # Remove duplicates while preserving order
    seen = set()
    return [t for t in combined if not (t in seen or seen.add(t))]

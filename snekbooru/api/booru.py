import random
import re
import json
import urllib.parse
import xml.etree.ElementTree as ET
import time
import time
_zerochan_last_request_time = 0


def filter_posts_by_blacklist(posts, blacklisted_tags):
    if not blacklisted_tags:
        return posts
    
    filtered = []
    blacklist_set = set(t.lower() for t in blacklisted_tags if t)
    
    for post in posts:
        tags = post.get("tags", "").lower()
        tags_set = set(tags.split())
        
        if not tags_set.intersection(blacklist_set):
            filtered.append(post)
    
    return filtered
import requests

from snekbooru.api.utils import http_get
from snekbooru.common.constants import (DANBOORU_COUNTS_POSTS, DANBOORU_POSTS,
                                        DANBOORU_RANDOM, DANBOORU_TAGS,
                                        GELBOORU_POSTS, GELBOORU_TAGS,
                                        HYBOORU_POSTS, HYBOORU_TAGS,
                                        HYPNOHUB_POSTS, HYPNOHUB_TAGS,
                                        KONACHAN_POSTS, KONACHAN_TAGS,
                                        RULE34_POSTS, RULE34_TAGS,
                                        XBOORU_POSTS, XBOORU_TAGS,
                                        SAFEBOORU_POSTS, SAFEBOORU_TAGS,
                                        SZURUBOORU_POSTS, SZURUBOORU_TAGS,
                                        YANDERE_POSTS, YANDERE_TAGS,
                                        ZEROCHAN_API)
from snekbooru.core.config import SETTINGS

def _get_blacklist_tags():
    blacklisted = SETTINGS.get("blacklisted_tags", "").split()
    return [tag.strip().lower() for tag in blacklisted if tag.strip()]

def _get_content_filter_tags():
    filter_tags = set()
    if not SETTINGS.get("allow_loli_shota", False):
        filter_tags.update(["loli", "shota"])
    if not SETTINGS.get("allow_bestiality", False):
        filter_tags.add("bestiality")
    if not SETTINGS.get("allow_guro", False):
        filter_tags.update(["guro", "gore", "blood", "injury"])
    return filter_tags

def _is_rating_allowed(post):
    rating = post.get("rating", "").lower()
    
    if rating in ["safe", "unknown", "", "s"]:
        return True
    
    if not SETTINGS.get("allow_explicit", False):
        return False
    
    return True

def _post_should_be_filtered(post, blacklist_tags, content_filter_tags):
    if not _is_rating_allowed(post):
        return True
    
    post_tags_str = post.get("tags", "") or post.get("tag_string", "")
    post_tags_lower = {tag.lower() for tag in post_tags_str.split()}
    
    if blacklist_tags and any(bl_tag in post_tags_lower for bl_tag in blacklist_tags):
        return True
    
    if content_filter_tags and any(cf_tag in post_tags_lower for cf_tag in content_filter_tags):
        return True
    
    return False

def _filter_posts(posts):
    blacklist = _get_blacklist_tags()
    content_filters = _get_content_filter_tags()
    
    return [p for p in posts if not _post_should_be_filtered(p, blacklist, content_filters)]

def _parse_gelbooru_html(html):
    results = []
    post_blocks = re.findall(r'<article[^>]*class="thumbnail-preview"[^>]*>(.*?)</article>', html, re.DOTALL)
    if not post_blocks:
        return results

    for block in post_blocks:
        id_match = re.search(r'id=(\d+)', block)
        img_match = re.search(r'<img[^>]+src=["\']([^"\']*(?:sample|thumbnail)[^"\']*)["\']', block, re.IGNORECASE)
        tags_match = re.findall(r'<a[^>]+href=["\'][^"\']*tags=[^"\']*["\'][^>]*>([^<]+)</a>', block)
        file_match = re.search(r'<a[^>]+href=["\']([^"\']*\.(?:jpg|jpeg|png|gif|webm|mp4|swf|webp)[^"\']*)["\']', block, re.IGNORECASE)

        if not img_match:
            continue

        pid = id_match.group(1) if id_match else ""
        preview_url = img_match.group(1)
        if preview_url.startswith("//"):
            preview_url = "https:" + preview_url
        file_url = file_match.group(1) if file_match else preview_url
        if file_url.startswith("//"):
            file_url = "https:" + file_url
        tags = " ".join(tags_match) if tags_match else ""

        results.append({
            "id": pid,
            "preview_url": preview_url,
            "file_url": file_url,
            "rating": "unknown",
            "score": 0,
            "tags": tags,
            "source_post_url": f"https://gelbooru.com/index.php?page=post&s=view&id={pid}" if pid else "",
            "file_ext": file_url.split('.')[-1].lower().split('?')[0] if file_url else ""
        })

    return results


def gelbooru_posts(tags, limit, pid):
    import cloudscraper
    from snekbooru.common.constants import USER_AGENT

    params = {"tags": tags}
    gb = SETTINGS.get("gelbooru", {})
    if gb.get("user_id") and gb.get("api_key"):
        params["user_id"] = gb["user_id"]
        params["api_key"] = gb["api_key"]

    total_count = 0
    fetch_limit = limit * 3
    params.update({"limit": fetch_limit, "pid": pid})

    all_posts_raw = []
    data = {}

    try:
        data = http_get(GELBOORU_POSTS, params=params)
        if isinstance(data, list):
            all_posts_raw = data
        elif isinstance(data, dict):
            if "post" in data:
                all_posts_raw = data.get("post", [])
            elif "@attributes" in data:
                if "count" in data["@attributes"]:
                    try: total_count = int(data["@attributes"]["count"])
                    except (ValueError, TypeError): pass
                all_posts_raw = data.get("post", [])
            else:
                all_posts_raw = [data]
        if isinstance(all_posts_raw, dict):
            all_posts_raw = [all_posts_raw]
    except Exception:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        try:
            r = scraper.get(GELBOORU_POSTS, params=params, timeout=60)
            r.raise_for_status()
            if r.content:
                try:
                    data = r.json()
                    if isinstance(data, dict):
                        all_posts_raw = data.get("post", [])
                    elif isinstance(data, list):
                        all_posts_raw = data
                    if isinstance(all_posts_raw, dict):
                        all_posts_raw = [all_posts_raw]
                except (json.JSONDecodeError, ValueError):
                    if r.text and ("<html" in r.text.lower() or "<article" in r.text):
                        parsed = _parse_gelbooru_html(r.text)
                        if parsed:
                            norm = _filter_posts(parsed)
                            return norm[:limit], total_count
        except Exception:
            pass

    if not all_posts_raw:
        try:
            html_url = GELBOORU_POSTS.replace("&json=1", "")
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            r = scraper.get(html_url, params=params, timeout=60, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            if r.text:
                parsed = _parse_gelbooru_html(r.text)
                if parsed:
                    norm = _filter_posts(parsed)
                    return norm[:limit], total_count
        except Exception:
            pass

    norm = []
    for p in all_posts_raw:
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

def danbooru_auth():
    db = SETTINGS.get("danbooru", {})
    if db.get("login") and db.get("api_key"):
        return (db["login"], db["api_key"])
    return None


def danbooru_posts(tags, limit, page):
    auth_tuple = danbooru_auth()

    tag_parts = tags.split()
    has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
    if not has_positive_tag:
        tags += " order:rank"

    total_count = 0
    try:
        count_params = {"tags": tags}
        count_data = http_get(DANBOORU_COUNTS_POSTS, params=count_params, auth=auth_tuple)
        total_count = count_data.get("counts", {}).get("posts", 0)
    except Exception:
        pass 

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

def konachan_posts(tags, limit, page):
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
    params = {"name": pattern, "limit": limit}
    data = http_get(KONACHAN_TAGS, params=params)
    return [t.get("name") for t in data if t.get("name")]

def yandere_posts(tags, limit, page):
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
    params = {"name": pattern, "limit": limit}
    data = http_get(YANDERE_TAGS, params=params)
    return [t.get("name") for t in data if t.get("name")]

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
    params = {"q": pattern}
    data = http_get(RULE34_TAGS, params=params)
    return [t.get("value") for t in data if t.get("value")][:limit]

def zerochan_posts(tags, limit, page):
    global _zerochan_last_request_time
    from snekbooru.common.constants import USER_AGENT
    
    now = time.time()
    elapsed = now - _zerochan_last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _zerochan_last_request_time = time.time()

    tag_list = tags.split()
    sanitized_tags = []
    for t in tag_list:
        if t.lower().startswith("rating:"):
            continue
        if t:
            sanitized_tags.append(t[0].upper() + t[1:])
            
    processed_tags = '+'.join(sanitized_tags) if sanitized_tags else ''

    if processed_tags:
        url = f"{ZEROCHAN_API}/{processed_tags}"
    else:
        url = f"{ZEROCHAN_API}/"

    zerochan_user = SETTINGS.get("zerochan_user", "Anonymous")
    custom_headers = {
        "User-Agent": f"Snekbooru - {zerochan_user}"
    }

    params = {"json": "1", "p": page + 1, "l": min(limit, 100)}

    try:
        r = requests.get(url, params=params, headers=custom_headers, timeout=30)
        r.raise_for_status()
        
        data = r.json()
        items = data.get("items", [])
        if not items and isinstance(data, list):
            items = data
        
        norm = []
        for item in items:
            post_id = str(item.get("id", ""))
            if not post_id:
                continue
            
            thumb = item.get("thumbnail", "")
            file_url = item.get("full") or item.get("large") or thumb
            
            if thumb and thumb.startswith("//"):
                thumb = f"https:{thumb}"
            
            if thumb and thumb.endswith(".avif"):
                thumb = thumb.replace(".avif", ".jpg")
                
            if file_url and file_url.startswith("//"):
                file_url = f"https:{file_url}"
                
            if file_url == thumb and thumb:
                if ".75." in file_url:
                    file_url = file_url.replace(".75.", ".full.")
                elif ".240." in file_url:
                    file_url = file_url.replace(".240.", ".full.")
                elif "s1.zerochan.net" in file_url:
                    file_url = file_url.replace("s1.zerochan.net", "static.zerochan.net").replace(".thumb.", ".full.")

            entry_tags = item.get("tags", [])
            if isinstance(entry_tags, list):
                tags_text = " ".join(t.replace(' ', '_') if isinstance(t, str) else str(t) for t in entry_tags)
            elif isinstance(entry_tags, str):
                tags_text = entry_tags
            else:
                tags_text = ""
            
            primary = item.get("primary", "")
            if primary and primary not in tags_text:
                tags_text = f"{primary.replace(' ', '_')} {tags_text}"
            
            if file_url:
                norm.append({
                    "id": post_id,
                    "preview_url": thumb or file_url,
                    "file_url": file_url,
                    "rating": "safe",
                    "score": item.get("fav", 0),
                    "tags": tags_text.strip(),
                    "source_post_url": f"https://www.zerochan.net/{post_id}",
                    "file_ext": file_url.split('.')[-1].lower().split('?')[0] if file_url else "jpg"
                })
        
        return norm[:limit], 0
    except Exception as e:
        print(f"Zerochan fetch error: {e}")
        return [], 0

def zerochan_tags_like(pattern, limit=20):
    return []

def hypnohub_posts(tags, limit, pid):
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

def hypnohub_tags_like(pattern, limit=20):
    params = {"name_pattern": pattern, "limit": limit}
    data = http_get(HYPNOHUB_TAGS, params=params)
    tags = data.get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]
    return [t.get("name") for t in tags if t.get("name")]

def hentai_haven_episodes(url):
    from bs4 import BeautifulSoup
    from snekbooru.common.constants import USER_AGENT

    try:
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, 'html.parser')
        
        episodes = []
        episode_items = soup.select('.wp-manga-chapter')

        for item in episode_items:
            link = item.find('a')
            if link and link.has_attr('href'):
                episode_url = link['href']
                episode_title = link.text.strip()
                episodes.append({'title': episode_title, 'url': episode_url})
        
        return list(reversed(episodes)), None
    except Exception as e:
        return [], str(e)

def hentai_haven_video_url(episode_url):
    from bs4 import BeautifulSoup
    from snekbooru.common.constants import USER_AGENT

    try:
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(episode_url, headers=headers, timeout=30, allow_redirects=True)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, 'html.parser')
        
        iframe = soup.find('iframe', src=lambda s: s and 'player.php' in s)
        if not iframe:
            return None, "Player iframe not found."

        player_r = requests.get(iframe['src'], headers=headers, timeout=30)
        player_r.raise_for_status()
        return player_r.json().get('video'), None
    except Exception as e:
        return None, str(e)

def fetch_multiple_sources(sources, tags, limit, page, custom_boorus):
    if not sources:
        return [], 0

    limit_per_source = max(1, limit // len(sources))
    all_posts = []
    total_count = 0 

    for source_name in sources:
        try:
            posts, _ = _do_fetch_single_source(source_name, tags, limit_per_source, page, custom_boorus)
            all_posts.extend(posts)
        except Exception as e:
            print(f"Failed to fetch from {source_name}: {e}")

    random.shuffle(all_posts)
    
    seen_urls = set()
    unique_posts = []
    for post in all_posts:
        file_url = post.get('file_url')
        if file_url and file_url not in seen_urls:
            unique_posts.append(post)
            seen_urls.add(file_url)
        elif not file_url: 
            unique_posts.append(post)

    return unique_posts, total_count

def _do_fetch_single_source(source_name, tags, limit, page, custom_boorus):
    source_function_map = {
        "Gelbooru": gelbooru_posts,
        "Danbooru": danbooru_posts,
        "Konachan": konachan_posts,
        "Yandere": yandere_posts,
        "Rule34": rule34_posts,
        "Hypnohub": hypnohub_posts,
        "Zerochan": zerochan_posts,
        "e621": e621_posts,
        "e926": e926_posts,
        "E621": e621_posts,
        "E926": e926_posts,
        "XBooru": xbooru_posts,
        "Safebooru": safebooru_posts,
        "Szurubooru": szurubooru_posts,
        "Mikubooru": hybooru_posts,
    }

    fetch_function = source_function_map.get(source_name)

    if fetch_function:
        if source_name == "Danbooru":
            return fetch_function(tags, limit, page)
        else:
            return fetch_function(tags, limit, page) 
    else:
        pass
        custom_booru_config = next((b for b in custom_boorus if b['name'] == source_name), None)
        if custom_booru_config:
            return fetch_custom_booru_posts(custom_booru_config, tags, limit, page)
        else:
            raise ValueError(f"Unknown source specified: {source_name}")

def fetch_custom_booru_posts(config, tags, limit, page):
    from snekbooru.common.constants import USER_AGENT
    
    if "Danbooru" in config.get("response_format", ""):
        tag_parts = tags.split()
        has_positive_tag = any(not part.startswith(('-', '~')) and ':' not in part for part in tag_parts)
        if not has_positive_tag:
            tags += " order:rank"

    posts_url = config['posts_url']
    auth = None
    if config.get("username") and config.get("api_key"):
        username = config.get("username", "").strip()
        api_key = config.get("api_key", "").strip()
        posts_url = posts_url.replace('{login}', username).replace('{id}', username).replace('{api_key}', api_key).replace('{username}', username)
    elif config.get('auth_type') == "Login & API Key":
        auth = danbooru_auth()

    encoded_tags = urllib.parse.quote_plus(tags)
    posts_url = posts_url.replace('{tags}', encoded_tags).replace('{limit}', str(limit)).replace('{pid}', str(page)).replace('{page}', str(page + 1)).replace('{offset}', str(page * limit))


    headers = {"User-Agent": USER_AGENT}
    r = requests.get(posts_url, headers=headers, timeout=30, auth=auth)
    r.raise_for_status()

    response_format = config['response_format']
    if "XML" in response_format:
        root = ET.fromstring(r.content)
        posts_xml = root.findall('post')
        posts = []
        for p_xml in posts_xml:
            posts.append(p_xml.attrib)
        total_count = int(root.attrib.get('count', 0))
    else: 
        posts = r.json()
        total_count = 0

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
        if isinstance(posts, dict):
            posts = posts.get("posts", posts.get("post", []))
        for p in posts:
            tags_str = p.get("tag_string", "")
            if isinstance(p.get("tags"), dict):
                tags_list = []
                for category in ["general", "artist", "copyright", "character", "species"]:
                    tags_list.extend(p.get("tags", {}).get(category, []))
                tags_str = " ".join(tags_list)
            
            rating = p.get("rating", "")
            
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
    elif response_format == "Szurubooru JSON":
        results = posts.get("results", []) if isinstance(posts, dict) else []
        if isinstance(posts, list):
            results = posts
        total_count = posts.get("total", 0) if isinstance(posts, dict) else 0
        for p in results:
            content_url = p.get("contentUrl", "")
            file_ext = ""
            if content_url:
                file_ext = content_url.split('.')[-1].lower().split('?')[0]
            tags_str = ""
            tags_list = p.get("tags", [])
            if isinstance(tags_list, list):
                tag_names = []
                for t in tags_list:
                    names = t.get("names", []) if isinstance(t, dict) else [str(t)]
                    tag_names.extend(names)
                tags_str = " ".join(tag_names)
            norm.append({
                "id": str(p.get("id")),
                "preview_url": p.get("thumbnailUrl", ""),
                "file_url": content_url,
                "rating": p.get("safety", "unknown"),
                "score": p.get("score", 0),
                "tags": tags_str,
                "source_post_url": f"{config.get('base_url', '')}/post/{p.get('id')}",
                "file_ext": file_ext
            })
    elif response_format == "Mikubooru JSON":
        results = posts.get("posts", []) if isinstance(posts, dict) else []
        if isinstance(posts, list):
            results = posts
        total_count = posts.get("total", 0) if isinstance(posts, dict) else 0
        base = config.get("base_url", "")
        for p in results:
            pid = p.get("id", "")
            ext = (p.get("extension") or "").lstrip(".")
            content_url = f"{base}/api/file/{pid}.{ext}" if pid and ext else ""
            thumb_url = f"{base}/api/file/{pid}.thumbnail.{ext}" if pid and ext else ""
            tags_str = ""
            tags_obj = p.get("tags", {})
            if isinstance(tags_obj, dict):
                tags_str = " ".join(tags_obj.keys())
            norm.append({
                "id": str(pid),
                "preview_url": thumb_url,
                "file_url": content_url,
                "rating": "safe" if p.get("rating") is not None and p["rating"] < 0.5 else "sketchy",
                "score": int((p.get("rating") or 0) * 100),
                "tags": tags_str,
                "source_post_url": f"{base}/post/{pid}",
                "file_ext": ext
            })
    
    return norm, total_count

def suggest_custom_booru_tags(config, pattern, limit):
    if not config.get("tags_url"): return [], None

    tags_url = config['tags_url']
    auth = None
    if config.get("username") and config.get("api_key"):
        username = config.get("username", "").strip()
        api_key = config.get("api_key", "").strip()
        tags_url = tags_url.replace('{login}', username).replace('{id}', username).replace('{api_key}', api_key).replace('{username}', username)
    elif config['auth_type'] == "Login & API Key":
        auth = danbooru_auth()
    
    tags_url = tags_url.replace('{pattern}', pattern).replace('{limit}', str(limit))

    data = http_get(tags_url, auth=auth)
    
    if config['response_format'] == "Gelbooru JSON":
        tags = data.get("tag", [])
        return [t.get("name") for t in tags if t.get("name")], None
    elif config['response_format'] == "Danbooru JSON":
        return [t.get("name") for t in data if t.get("name")], None
    elif config['response_format'] == "Rule34 XML":
        return [t.get("value") for t in data if t.get("value")], None
    elif config['response_format'] == "Szurubooru JSON":
        results = data.get("results", []) if isinstance(data, dict) else []
        tag_names = []
        for t in results:
            names = t.get("names", [])
            if isinstance(names, list):
                tag_names.extend(names)
        return tag_names, None
    elif config['response_format'] == "Mikubooru JSON":
        tags_obj = data.get("tags", {}) if isinstance(data, dict) else {}
        if isinstance(tags_obj, dict):
            return list(tags_obj.keys()), None
        return [], None
    
    return [], "Unsupported tag format"

def suggest_all_tags(pattern, limit=40):
    num_sources = 13
    src_limit = limit // num_sources
    gel_limit = src_limit
    dan_limit = src_limit
    kona_limit = src_limit
    yandere_limit = src_limit
    r34_limit = src_limit
    e621_limit = src_limit
    e926_limit = src_limit
    xbooru_limit = src_limit
    safebooru_limit = src_limit
    szuru_limit = src_limit
    hybooru_limit = src_limit
    hypno_limit = limit - (gel_limit + dan_limit + kona_limit + yandere_limit + r34_limit + e621_limit + e926_limit + xbooru_limit + safebooru_limit + szuru_limit + hybooru_limit)
    
    gel_tags, dan_tags, kona_tags, yandere_tags, r34_tags, hypno_tags, zero_tags, e621_tags, e926_tags, xbooru_tags, safebooru_tags, szuru_tags, hybooru_tags = [], [], [], [], [], [], [], [], [], [], [], [], []
    try: gel_tags = gelbooru_tags_like(pattern, gel_limit)
    except Exception: pass
    try:
        patt = pattern if "*" in pattern else (pattern + "*")
        dan_tags = danbooru_tags_like(patt, dan_limit)
    except Exception: pass
    try:
        patt = pattern if pattern.endswith('*') else pattern + '*'
        kona_tags = konachan_tags_like(patt, kona_limit)
    except Exception: pass
    try:
        patt = pattern if pattern.endswith('*') else pattern + '*'
        yandere_tags = yandere_tags_like(patt, yandere_limit)
    except Exception: pass
    try:
        r34_tags = rule34_tags_like(pattern, r34_limit)
    except Exception: pass
    try:
        hypno_tags = hypnohub_tags_like(pattern, hypno_limit)
    except Exception: pass
    try:
        zero_tags = zerochan_tags_like(pattern, 0)
    except Exception: pass
    try:
        patt = pattern if "*" in pattern else (pattern + "*")
        e621_tags = e621_tags_like(patt, e621_limit)
    except Exception: pass
    try:
        patt = pattern if "*" in pattern else (pattern + "*")
        e926_tags = e926_tags_like(patt, e926_limit)
    except Exception: pass
    try:
        xbooru_tags = xbooru_tags_like(pattern, xbooru_limit)
    except Exception: pass
    try:
        safebooru_tags = safebooru_tags_like(pattern, safebooru_limit)
    except Exception: pass
    try:
        szuru_tags = szurubooru_tags_like(pattern, szuru_limit)
    except Exception: pass
    try:
        hybooru_tags = hybooru_tags_like(pattern, hybooru_limit)
    except Exception: pass
    
    combined = gel_tags + dan_tags + kona_tags + yandere_tags + r34_tags + hypno_tags + zero_tags + e621_tags + e926_tags + xbooru_tags + safebooru_tags + szuru_tags + hybooru_tags
    seen = set()
    return [t for t in combined if not (t in seen or seen.add(t))]


def e621_posts_generic(source_name, posts_url, tags, limit, page):
    # E621 / E926 auth
    auth_tuple = None
    cred = SETTINGS.get(source_name.lower(), {})
    login = cred.get("login", "")
    api_key = cred.get("api_key", "")
    if login and api_key:
        auth_tuple = (login, api_key)

    ua = "Snekbooru/6.0.1 (by anonymous on e621)"
    if login:
        ua = f"Snekbooru/6.0.1 (by {login} on e621)"
    custom_headers = {"User-Agent": ua}

    # E621/E926 uses 1-indexed page
    params = {"tags": tags, "limit": limit, "page": page + 1}
    try:
        data = http_get(posts_url, params=params, auth=auth_tuple, custom_headers=custom_headers)
    except Exception as e:
        print(f"Failed to fetch posts from {source_name}: {e}")
        return [], 0

    posts = []
    if isinstance(data, dict):
        posts = data.get("posts", [])
    elif isinstance(data, list):
        posts = data

    norm = []
    for p in posts:
        # Extract tags
        tags_str = ""
        ptags = p.get("tags")
        if isinstance(ptags, dict):
            tags_list = []
            for cat in ["general", "artist", "copyright", "character", "species", "meta"]:
                tags_list.extend(ptags.get(cat, []))
            tags_str = " ".join(tags_list)
        elif isinstance(ptags, list):
            tags_str = " ".join(ptags)
        elif isinstance(ptags, str):
            tags_str = ptags
        else:
            tags_str = p.get("tag_string", "")

        # Extract file_url
        file_url = ""
        pfile = p.get("file")
        if isinstance(pfile, dict):
            file_url = pfile.get("url")
        if not file_url:
            file_url = p.get("file_url")
        if not file_url:
            continue

        # Extract preview_url
        preview_url = ""
        pprev = p.get("preview")
        if isinstance(pprev, dict):
            preview_url = pprev.get("url")
        if not preview_url:
            preview_url = p.get("preview_file_url") or file_url

        # Extract rating
        rating = p.get("rating", "")

        # Extract score
        score = p.get("score", 0)
        if isinstance(score, dict):
            score = score.get("total", 0)

        # File extension
        file_ext = ""
        pfile = p.get("file")
        if isinstance(pfile, dict) and pfile.get("ext"):
            file_ext = pfile.get("ext").lower()
        if not file_ext:
            file_ext = p.get("file_ext", "").lower()
        if not file_ext and file_url:
            file_ext = file_url.split('.')[-1].lower().split('?')[0]

        norm.append({
            "id": str(p.get("id")),
            "preview_url": preview_url,
            "file_url": file_url,
            "rating": rating,
            "score": score,
            "tags": tags_str,
            "source_post_url": f"https://{source_name.lower()}.net/posts/{p.get('id')}",
            "file_ext": file_ext
        })

    norm = _filter_posts(norm)
    return norm[:limit], 0


def e621_posts(tags, limit, page):
    from snekbooru.common.constants import E621_POSTS
    return e621_posts_generic("e621", E621_POSTS, tags, limit, page)


def e926_posts(tags, limit, page):
    from snekbooru.common.constants import E926_POSTS
    return e621_posts_generic("e926", E926_POSTS, tags, limit, page)


def e621_tags_like_generic(source_name, tags_url, pattern, limit=20):
    auth_tuple = None
    cred = SETTINGS.get(source_name.lower(), {})
    login = cred.get("login", "")
    api_key = cred.get("api_key", "")
    if login and api_key:
        auth_tuple = (login, api_key)

    ua = "Snekbooru/6.0.1 (by anonymous on e621)"
    if login:
        ua = f"Snekbooru/6.0.1 (by {login} on e621)"
    custom_headers = {"User-Agent": ua}

    params = {"search[name_matches]": pattern + "*", "limit": limit}
    try:
        data = http_get(tags_url, params=params, auth=auth_tuple, custom_headers=custom_headers)
        if isinstance(data, list):
            return [t.get("name") for t in data if t.get("name")]
    except Exception as e:
        print(f"Failed to fetch tags from {source_name}: {e}")
    return []


def e621_tags_like(pattern, limit=20):
    from snekbooru.common.constants import E621_TAGS
    return e621_tags_like_generic("e621", E621_TAGS, pattern, limit)


def e926_tags_like(pattern, limit=20):
    from snekbooru.common.constants import E926_TAGS
    return e621_tags_like_generic("e926", E926_TAGS, pattern, limit)


def _dapi_posts(url, tags, limit, pid, source_name):
    import cloudscraper
    from snekbooru.common.constants import USER_AGENT

    params = {"tags": tags, "limit": limit, "pid": pid}
    all_posts_raw = []
    total_count = 0

    try:
        data = http_get(url, params=params)
        if isinstance(data, dict):
            if "@attributes" in data and "count" in data["@attributes"]:
                try:
                    total_count = int(data["@attributes"]["count"])
                except (ValueError, TypeError):
                    pass
            all_posts_raw = data.get("post", [])
        elif isinstance(data, list):
            all_posts_raw = data
        if isinstance(all_posts_raw, dict):
            all_posts_raw = [all_posts_raw]
    except Exception:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        try:
            r = scraper.get(url, params=params, timeout=60)
            r.raise_for_status()
            if r.content:
                try:
                    data = r.json()
                    if isinstance(data, dict):
                        all_posts_raw = data.get("post", [])
                    elif isinstance(data, list):
                        all_posts_raw = data
                except (json.JSONDecodeError, ValueError):
                    if r.text and ("<article" in r.text.lower() or "<html" in r.text.lower()):
                        parsed = _parse_gelbooru_html(r.text)
                        if parsed:
                            return _filter_posts(parsed)[:limit], total_count
        except Exception:
            pass

    norm = []
    for p in all_posts_raw:
        file_url = p.get("file_url")
        if file_url and file_url.startswith("//"):
            file_url = "https:" + file_url
        preview_url = p.get("preview_url") or p.get("sample_url") or file_url
        if preview_url and preview_url.startswith("//"):
            preview_url = "https:" + preview_url

        norm.append({
            "id": str(p.get("id")),
            "preview_url": preview_url,
            "file_url": file_url,
            "rating": p.get("rating"),
            "score": p.get("score"),
            "tags": p.get("tags", ""),
            "source_post_url": f"https://{source_name}.com/index.php?page=post&s=view&id={p.get('id')}"
            if source_name not in ("safebooru",)
            else f"https://safebooru.org/index.php?page=post&s=view&id={p.get('id')}",
            "file_ext": file_url.split('.')[-1].lower().split('?')[0] if file_url else ""
        })

    return _filter_posts(norm)[:limit], total_count


def xbooru_posts(tags, limit, pid):
    return _dapi_posts(XBOORU_POSTS, tags, limit, pid, "xbooru")


def xbooru_tags_like(pattern, limit=20):
    params = {"name_pattern": pattern, "limit": limit}
    data = http_get(XBOORU_TAGS, params=params)
    tags = data.get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]
    return [t.get("name") for t in tags if t.get("name")]


def safebooru_posts(tags, limit, pid):
    if "rating:" not in tags.lower() and not SETTINGS.get("allow_explicit", False):
        tags = f"{tags} rating:safe".strip()
    return _dapi_posts(SAFEBOORU_POSTS, tags, limit, pid, "safebooru")


def safebooru_tags_like(pattern, limit=20):
    params = {"name_pattern": pattern, "limit": limit}
    data = http_get(SAFEBOORU_TAGS, params=params)
    tags = data.get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]
    return [t.get("name") for t in tags if t.get("name")]


def szurubooru_posts(tags, limit, page):
    from snekbooru.common.constants import USER_AGENT

    offset = page * limit
    params = {"offset": offset, "limit": limit}
    if tags.strip():
        params["query"] = tags.strip()

    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        r = requests.get(SZURUBOORU_POSTS, params=params, headers=headers, timeout=30)
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        return [], 0

    data = r.json()
    if "results" not in data:
        return [], 0

    total = int(data.get("total", 0))
    results = data.get("results", [])
    base_url = "https://szuru.libre.moe"

    norm = []
    for p in results:
        content_url = p.get("contentUrl", "")
        thumb_url = p.get("thumbnailUrl", "")
        if content_url and content_url.startswith("data/"):
            content_url = f"{base_url}/{content_url}"
        if thumb_url and thumb_url.startswith("data/"):
            thumb_url = f"{base_url}/{thumb_url}"

        tags_str = ""
        tags_list = p.get("tags", [])
        if isinstance(tags_list, list):
            tag_names = []
            for t in tags_list:
                names = t.get("names", []) if isinstance(t, dict) else [str(t)]
                tag_names.extend(names)
            tags_str = " ".join(tag_names)

        file_ext = ""
        if content_url:
            file_ext = content_url.split('.')[-1].lower().split('?')[0]

        norm.append({
            "id": str(p.get("id")),
            "preview_url": thumb_url,
            "file_url": content_url,
            "rating": p.get("safety", "unknown"),
            "score": p.get("score", 0),
            "tags": tags_str,
            "source_post_url": f"{base_url}/post/{p.get('id')}",
            "file_ext": file_ext,
        })

    return _filter_posts(norm)[:limit], total


def szurubooru_tags_like(pattern, limit=20):
    from snekbooru.common.constants import USER_AGENT

    params = {"limit": limit}
    if pattern.strip():
        params["query"] = pattern.strip()

    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        r = requests.get(SZURUBOORU_TAGS, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        tag_names = []
        for t in results:
            names = t.get("names", [])
            if isinstance(names, list):
                tag_names.extend(names)
        return tag_names
    except Exception:
        return []


def hybooru_posts(tags, limit, page):
    from snekbooru.common.constants import USER_AGENT

    base_url = "https://booru.funmaker.moe"
    params = {"query": tags.strip(), "page": page, "pageSize": limit}
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(HYBOORU_POSTS, params=params, headers=headers, timeout=30)
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        return [], 0

    data = r.json()
    if "posts" not in data:
        return [], 0

    total = int(data.get("total", 0))
    results = data.get("posts", [])

    norm = []
    for p in results[:limit]:
        sha = p.get("sha256", "")
        ext = (p.get("extension") or "").lstrip(".")
        pid = str(p.get("id", ""))

        file_url = f"{base_url}/files/f{sha}.{ext}" if sha and ext else ""
        if not file_url:
            continue

        norm.append({
            "id": pid,
            "preview_url": file_url,
            "file_url": file_url,
            "rating": "sketchy",
            "score": 0,
            "tags": "",
            "source_post_url": f"{base_url}/post/{pid}",
            "file_ext": ext,
        })

    return _filter_posts(norm)[:limit], total


def hybooru_tags_like(pattern, limit=20):
    from snekbooru.common.constants import USER_AGENT

    params = {"query": pattern.strip(), "page": 0, "pageSize": limit}
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(HYBOORU_TAGS, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        tags_obj = data.get("tags", {})
        if isinstance(tags_obj, dict):
            return list(tags_obj.keys())[:limit]
        return []
    except Exception:
        return []

import os
import re

import requests

from snekbooru_linux.common.constants import USER_AGENT


_GALLERY_ID_RE = re.compile(r"/g/(\d+)")


def parse_gallery_id(url):
    if not isinstance(url, str):
        return None
    m = _GALLERY_ID_RE.search(url)
    if not m:
        return None
    return int(m.group(1))


def _get_http_client():
    try:
        import cloudscraper

        return cloudscraper.create_scraper()
    except Exception:
        return requests.Session()


def fetch_gallery_metadata(gallery_id, http_client=None):
    if http_client is None:
        http_client = _get_http_client()
    r = http_client.get(
        f"https://nhentai.net/api/gallery/{int(gallery_id)}",
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _page_extension(page_obj):
    t = None
    try:
        t = page_obj.get("t")
    except Exception:
        t = None
    mapping = {"j": "jpg", "p": "png", "g": "gif", "w": "webp"}
    return mapping.get(t, "jpg")


def build_page_urls(media_id, pages):
    urls = []
    for i, page in enumerate(pages, start=1):
        ext = _page_extension(page)
        urls.append(f"https://i.nhentai.net/galleries/{media_id}/{i}.{ext}")
    return urls


def download_gallery_pages(gallery_url, output_dir, http_client=None, progress_cb=None):
    gallery_id = parse_gallery_id(gallery_url)
    if not gallery_id:
        raise ValueError("Invalid nhentai gallery URL")

    if http_client is None:
        http_client = _get_http_client()

    meta = fetch_gallery_metadata(gallery_id, http_client=http_client)
    media_id = meta.get("media_id")
    images = meta.get("images") or {}
    pages = images.get("pages") or []
    title = None
    try:
        title = (meta.get("title") or {}).get("pretty") or (meta.get("title") or {}).get("english")
    except Exception:
        title = None
    if not media_id or not pages:
        raise RuntimeError("Could not parse gallery metadata")

    os.makedirs(output_dir, exist_ok=True)
    urls = build_page_urls(media_id, pages)

    for idx, url in enumerate(urls, start=1):
        ext = os.path.splitext(url)[1].lower() or ".jpg"
        file_path = os.path.join(output_dir, f"page_{idx:04d}{ext}")
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            if callable(progress_cb):
                progress_cb(idx, len(urls))
            continue

        r = http_client.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://nhentai.net/"}, timeout=60, stream=True)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)

        if callable(progress_cb):
            progress_cb(idx, len(urls))

    return {"gallery_id": gallery_id, "title": title or f"nhentai {gallery_id}", "output_dir": output_dir, "pages": len(urls)}


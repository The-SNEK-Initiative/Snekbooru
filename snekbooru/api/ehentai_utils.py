import os
import re
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup

from snekbooru.common.constants import USER_AGENT, EHENTAI_API


_GALLERY_ID_TOKEN_RE = re.compile(r"/g/(\d+)/([a-f0-9]+)")
_TITLE_RE = re.compile(r'<h1 id="gn">([^<]+)</h1>')
_FILE_COUNT_RE = re.compile(r'<td class="gdt1">Length:</td><td class="gdt2">(\d+) pages</td>')
_DIRECT_IMAGE_RE = re.compile(r'<img id="img" src="([^"]+)"')


def parse_gallery_id_token(url):
    if not isinstance(url, str):
        return None, None
    m = _GALLERY_ID_TOKEN_RE.search(url)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def fetch_gallery_metadata(gid, token, http_client=None):
    payload = {
        "method": "gdata",
        "gidlist": [[gid, token]],
        "namespace": 1
    }
    
    if http_client is None:
        http_client = requests.Session()
        
    r = http_client.post(
        EHENTAI_API,
        json=payload,
        headers={"User-Agent": USER_AGENT},
        timeout=30
    )
    r.raise_for_status()
    data = r.json()
    
    if "gmetadata" in data and data["gmetadata"]:
        meta = data["gmetadata"][0]
        if "error" in meta:
            raise RuntimeError(f"e-hentai API error: {meta['error']}")
        return meta
    
    raise RuntimeError("Could not parse e-hentai gallery metadata")


def _extract_image_url_from_page(page_html):
    match = _DIRECT_IMAGE_RE.search(page_html)
    if match:
        return match.group(1)
    return None


def download_gallery_pages(gallery_url, output_dir, http_client=None, progress_cb=None):
    gid, token = parse_gallery_id_token(gallery_url)
    if not gid:
        raise ValueError("Invalid e-hentai gallery URL. Must be in format: https://e-hentai.org/g/{gid}/{token}/")

    if http_client is None:
        scraper = cloudscraper.create_scraper()
    else:
        scraper = http_client
    
    r = scraper.get(gallery_url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    html = r.text

    title_match = _TITLE_RE.search(html)
    title = title_match.group(1) if title_match else f"e-hentai {gid}"
    
    count_match = _FILE_COUNT_RE.search(html)
    file_count = int(count_match.group(1)) if count_match else 0
    
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Could not create output directory {output_dir}: {e}")

    soup = BeautifulSoup(html, 'html.parser')
    image_page_urls = []
    
    for link in soup.find_all('a', href=re.compile(r'/s/[a-z0-9]+/\d+-\d+')):
        href = link.get('href')
        if href and href not in image_page_urls:
            image_page_urls.append(href)
    
    page_idx = 1
    while file_count > 0 and len(image_page_urls) < file_count:
        gurl = f"{gallery_url.rstrip('/')}/?p={page_idx}"
        try:
            r = scraper.get(gurl, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, 'html.parser')
            new_urls = 0
            for link in soup.find_all('a', href=re.compile(r'/s/[a-z0-9]+/\d+-\d+')):
                href = link.get('href')
                if href and href not in image_page_urls:
                    image_page_urls.append(href)
                    new_urls += 1
            
            if new_urls == 0:
                break
                
            page_idx += 1
            time.sleep(0.5)  
        except Exception as e:
            break

    downloaded_paths = []
    total_to_download = len(image_page_urls)

    for i, img_page_url in enumerate(image_page_urls, start=1):
        if progress_cb:
            progress_cb(i, total_to_download)
            
        try:
            r = scraper.get(img_page_url, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            
            img_url = _extract_image_url_from_page(r.text)
            if not img_url:
                continue
            
            ext = ".jpg"
            if "." in img_url:
                potential_ext = os.path.splitext(img_url.split("?")[0])[1].lower()
                if potential_ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                    ext = potential_ext
            
            file_path = os.path.join(output_dir, f"page_{i:04d}{ext}")
            
            ir = scraper.get(img_url, headers={"User-Agent": USER_AGENT, "Referer": img_page_url}, timeout=60)
            ir.raise_for_status()
            
            with open(file_path, "wb") as f:
                f.write(ir.content)
            
            downloaded_paths.append(file_path)
            time.sleep(0.5)
            
        except Exception as e:
            continue

    return {
        "gallery_id": gid,
        "title": title,
        "output_dir": output_dir,
        "pages": len(downloaded_paths),
        "total_expected": file_count,
        "metadata": {"title": title, "filecount": file_count}
    }

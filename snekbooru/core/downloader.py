import os
import requests

from snekbooru.common.helpers import convert_gif_to_webp, get_file_hash, get_media_headers
from snekbooru.common.translations import _tr
from snekbooru.core.config import (SETTINGS, load_downloads_data,
                                   save_downloads_data)


def download_media(post, parent_widget=None):
    url = post.get("file_url")
    if not url:
        return False, _tr("No file URL available.")
    try:
        download_dir = SETTINGS.get("download_dir")
        os.makedirs(download_dir, exist_ok=True)

        file_hash = get_file_hash(post)
        ext_part = os.path.splitext(url.split('?')[0])[1].lower()
        original_ext = "".join(c for c in ext_part if c.isalnum() or c == '.')
        if not original_ext:
            original_ext = f'.{post.get("file_ext", "jpg")}'
        
        downloads_data = load_downloads_data()
        if file_hash in downloads_data and os.path.exists(downloads_data[file_hash].get("local_path", "")):
            return True, _tr("File already exists.")

        r = requests.get(url, headers=get_media_headers(url), timeout=60)
        r.raise_for_status()
        
        media_data = r.content
        final_ext = original_ext
        if original_ext.lower() == '.gif' and SETTINGS.get("convert_gifs_to_webp", True):
            media_data, final_ext, _ = convert_gif_to_webp(media_data)
        
        file_path = os.path.join(download_dir, f"{file_hash}{final_ext}")

        with open(file_path, "wb") as f: f.write(media_data)

        post_copy = post.copy()
        post_copy['local_path'] = file_path
        post_copy['local_thumbnail_path'] = None
        post_copy['file_ext'] = final_ext.lstrip('.')
        downloads_data[file_hash] = post_copy
        save_downloads_data(downloads_data)

        return True, _tr("Saved to: {path}").format(path=file_path)
    except Exception as e:
        return False, str(e)

import os
import requests

from snekbooru_linux.common.constants import USER_AGENT
from snekbooru_linux.common.helpers import convert_gif_to_webp, get_file_hash
from snekbooru_linux.common.translations import _tr
from snekbooru_linux.core.config import (SETTINGS, load_downloads_data,
                                   save_downloads_data)


def _try_create_thumbnail(media_data, download_dir, file_hash):
    try:
        from PIL import Image
        import io
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(media_data)) as img:
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.thumbnail((256, 256))
            thumb_path = os.path.join(download_dir, f"{file_hash}_thumb.jpg")
            img.save(thumb_path, format="JPEG", quality=85, optimize=True)
            return thumb_path
    except Exception:
        return None


def download_media(post, parent_widget=None):
    """
    Downloads the media for a given post and saves metadata.
    Converts GIFs to WebP for storage.
    Returns a tuple (success, message).
    """
    url = post.get("file_url")
    if not url:
        return False, _tr("No file URL available.")
    try:
        download_dir = SETTINGS.get("download_dir")
        os.makedirs(download_dir, exist_ok=True)

        file_hash = get_file_hash(post)
        original_ext = os.path.splitext(url.split('?')[0])[1] or f'.{post.get("file_ext", "jpg")}'
        
        downloads_data = load_downloads_data()
        if file_hash in downloads_data and os.path.exists(downloads_data[file_hash].get("local_path", "")):
            return True, _tr("File already exists.")

        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        
        media_data = r.content
        final_ext = original_ext
        if original_ext.lower() == '.gif' and SETTINGS.get("convert_gifs_to_webp", True):
            media_data, final_ext, _ = convert_gif_to_webp(media_data)
        
        file_path = os.path.join(download_dir, f"{file_hash}{final_ext}")

        with open(file_path, "wb") as f: f.write(media_data)

        local_thumb = None
        if final_ext.lstrip('.').lower() in ["jpg", "jpeg", "png", "webp", "bmp", "gif"]:
            local_thumb = _try_create_thumbnail(media_data, download_dir, file_hash)

        post_copy = post.copy()
        post_copy['local_path'] = file_path
        post_copy['local_thumbnail_path'] = local_thumb
        post_copy['file_ext'] = final_ext.lstrip('.')
        downloads_data[file_hash] = post_copy
        save_downloads_data(downloads_data)

        return True, _tr("Saved to: {path}").format(path=file_path)
    except Exception as e:
        return False, str(e)

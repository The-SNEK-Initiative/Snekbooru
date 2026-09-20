import hashlib
import os
import sys

from PyQt5.QtCore import QStandardPaths

from snekbooru.common.constants import USER_AGENT
from snekbooru.core.config import SETTINGS


def get_media_headers(url):
    headers = {"User-Agent": USER_AGENT}
    if isinstance(url, str) and "gelbooru.com" in url:
        headers["Referer"] = "https://gelbooru.com/"
    return headers


def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def convert_gif_to_webp(gif_data):
    try:
        from PIL import Image
        import io
    except ImportError:
        return gif_data, '.gif', "Pillow library not found, saved as GIF. Install with 'pip install Pillow'."

    try:
        with Image.open(io.BytesIO(gif_data)) as img:
            webp_data = io.BytesIO()
            img.save(webp_data, format='WEBP', save_all=True, quality=85, lossless=False, method=6)
            return webp_data.getvalue(), '.webp', None 
    except Exception as e:
        return gif_data, '.gif', f"WebP conversion failed: {e}. Saved as GIF."

def get_file_hash(post):
    url_to_hash = post.get("source_post_url") or post.get("file_url")
    if not url_to_hash:
        url_to_hash = f"{post.get('id', '')}-{post.get('tags', '')[:50]}"
    return hashlib.sha256(url_to_hash.encode('utf-8')).hexdigest()

def load_pixmap_from_data(data):
    from PyQt5.QtGui import QPixmap, QImage
    pix = QPixmap()
    if pix.loadFromData(data):
        return pix
        
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        
        if img.mode != "RGBA":
            img = img.convert("RGBA")
            
        data = img.tobytes("raw", "BGRA")
        qimg = QImage(data, img.size[0], img.size[1], QImage.Format_ARGB32)
        return QPixmap.fromImage(qimg)
    except Exception as e:
        print(f"Pillow fallback failed: {e}")
        return QPixmap()

_THUMB_CACHE = {}
_THUMB_CACHE_ORDER = []
_THUMB_CACHE_MAX = 512


def _thumb_key(path, size):
    return (os.path.normcase(os.path.abspath(path)), int(size))


def _thumb_cache_get(key):
    return _THUMB_CACHE.get(key)


def _thumb_cache_put(key, pix):
    if pix is None or pix.isNull():
        return
    if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX and _THUMB_CACHE_ORDER:
        _THUMB_CACHE.pop(_THUMB_CACHE_ORDER.pop(0), None)
    if key not in _THUMB_CACHE:
        _THUMB_CACHE[key] = pix
        _THUMB_CACHE_ORDER.append(key)


def generate_thumbnail_pixmap(path, size, force_reload=False):
    from PyQt5.QtCore import QSize
    from PyQt5.QtGui import QImage, QImageReader, QPixmap
    if not path or not os.path.exists(path):
        return QPixmap()
    key = _thumb_key(path, size)
    if not force_reload:
        cached = _thumb_cache_get(key)
        if cached is not None:
            return cached
    pix = QPixmap()
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        if key[1] > 0:
            reader.setScaledSize(QSize(key[1], key[1]))
        img = reader.read()
        if not img.isNull():
            pix = QPixmap.fromImage(img)
    except Exception:
        pass
    if pix.isNull():
        try:
            from PIL import Image
            import io
            with open(path, "rb") as f:
                raw = f.read()
            img = Image.open(io.BytesIO(raw))
            if key[1] > 0:
                img.thumbnail((key[1], key[1]))
            if img.mode not in ("RGBA", "LA"):
                img = img.convert("RGBA")
            data = img.tobytes("raw", "BGRA")
            qimg = QImage(data, img.size[0], img.size[1], QImage.Format_ARGB32)
            pix = QPixmap.fromImage(qimg)
        except Exception:
            pass
    if pix.isNull():
        pix = QPixmap(path)
    _thumb_cache_put(key, pix)
    return pix


def load_video_thumbnail_pixmap(path, size):
    from PyQt5.QtGui import QPixmap
    pix = QPixmap()
    if not path or not os.path.exists(path):
        return pix
    key = _thumb_key(path, size)
    cached = _thumb_cache_get(key)
    if cached is not None:
        return cached
    try:
        import shutil
        import subprocess
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return pix
        cmd = [
            ffmpeg, "-v", "error", "-ss", "1", "-i", str(path),
            "-frames:v", "1", "-vf", f"scale='min({key[1]},iw)':-2",
            "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "5",
            "-pix_fmt", "yuvj420p", "pipe:1",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        if proc.returncode == 0 and proc.stdout:
            pix.loadFromData(proc.stdout)
    except Exception:
        pass
    _thumb_cache_put(key, pix)
    return pix
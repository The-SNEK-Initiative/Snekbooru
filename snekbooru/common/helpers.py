import hashlib
import os
import sys

from PyQt5.QtCore import QStandardPaths

from snekbooru.core.config import SETTINGS


def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def convert_gif_to_webp(gif_data):
    """Converts GIF data to WebP. Requires Pillow."""
    try:
        from PIL import Image
        import io
    except ImportError:
        return gif_data, '.gif', "Pillow library not found, saved as GIF. Install with 'pip install Pillow'."

    try:
        with Image.open(io.BytesIO(gif_data)) as img:
            webp_data = io.BytesIO()
            # The 'save_all' is crucial for animated GIFs. method=6 is slowest but best compression.
            img.save(webp_data, format='WEBP', save_all=True, quality=85, lossless=False, method=6)
            return webp_data.getvalue(), '.webp', None # No error message
    except Exception as e:
        return gif_data, '.gif', f"WebP conversion failed: {e}. Saved as GIF."

def get_file_hash(post):
    """Generates a unique and stable hash for a post object."""
    url_to_hash = post.get("source_post_url") or post.get("file_url")
    if not url_to_hash:
        url_to_hash = f"{post.get('id', '')}-{post.get('tags', '')[:50]}"
    return hashlib.sha256(url_to_hash.encode('utf-8')).hexdigest()

def load_pixmap_from_data(data):
    """
    Attempts to load a QPixmap from raw bytes.
    If QPixmap.loadFromData fails, falls back to using Pillow for decoding.
    """
    from PyQt5.QtGui import QPixmap, QImage
    pix = QPixmap()
    if pix.loadFromData(data):
        return pix
        
    # Fallback to Pillow
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        
        # Convert to RGBA if necessary
        if img.mode != "RGBA":
            img = img.convert("RGBA")
            
        data = img.tobytes("raw", "BGRA")
        qimg = QImage(data, img.size[0], img.size[1], QImage.Format_ARGB32)
        return QPixmap.fromImage(qimg)
    except Exception as e:
        print(f"Pillow fallback failed: {e}")
        return QPixmap()
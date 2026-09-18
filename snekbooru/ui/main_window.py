import os
import random
import shutil
import sys
import threading
import time
import re
import inspect
from types import SimpleNamespace
import qtawesome as qta

vendor_path = os.path.join(os.path.dirname(__file__), '..', 'vendor')
sys.path.insert(0, vendor_path)

import base64
import cloudscraper
import requests
from bs4 import BeautifulSoup
from multiprocessing import Process, Queue
from urllib.parse import quote_plus
try:
    from enma import CloudFlareConfig, Enma, Sources, infra
    from enma.application.core.handlers.error import Forbidden
    ENMA_AVAILABLE = True
except Exception:
    CloudFlareConfig = None
    Enma = None
    infra = None
    ENMA_AVAILABLE = False

    class Forbidden(Exception):
        pass

    class _SourcesFallback(list):
        NHENTAI = "NHENTAI"
        MANGADEX = "MANGADEX"

    Sources = _SourcesFallback()

try:
    from snekbooru.api.ehentai_repo import EHentaiRepo
except Exception:
    EHentaiRepo = None

if ENMA_AVAILABLE and EHentaiRepo is not None:
    _original_enma_init = Enma.__init__
    def _patched_enma_init(self, *args, **kwargs):
        _original_enma_init(self, *args, **kwargs)
        try:
            self.source_manager.add_source(Sources.NHENTAI, EHentaiRepo())
        except Exception as e:
            print(f"Failed to patch Enma NHENTAI source: {e}")
    Enma.__init__ = _patched_enma_init
from PyQt5.QtCore import (QCoreApplication, QEvent, QPoint, QStringListModel,
                          Qt, QThreadPool, QTimer, pyqtSignal, QThread, QUrl, QStandardPaths)
from PyQt5.QtGui import (QCursor, QIcon, QKeySequence, QMovie, QPixmap,
                         QTextCursor, QIntValidator)
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter,
                             QFormLayout, QFrame, QGridLayout, QGroupBox,
                             QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSizePolicy, QSpacerItem, QSpinBox, QStackedWidget, QFileDialog,
                             QSplitter, QTabWidget, QWidget, QVBoxLayout, QToolButton, QDialog, QTextBrowser, QTextEdit,
                             QSlider, QShortcut, QKeySequenceEdit)
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
import webbrowser, traceback
from PyQt5.QtWidgets import QDesktopWidget

_webengine_imported = False
def _ensure_webengine():
    global _webengine_imported, QWebEnginePage, QWebEngineProfile, QWebEngineView, QWebEngineScript, QWebEngineSettings
    if not _webengine_imported:
        from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView, QWebEngineScript
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        _webengine_imported = True

from snekbooru.api.ehentai_utils import download_gallery_pages, parse_gallery_id_token
from snekbooru.api.booru import (gelbooru_posts, danbooru_post_count, danbooru_random,
                                 fetch_multiple_sources,
                                 suggest_all_tags)
from snekbooru.api.utils import scrape_post_count
from snekbooru.common.constants import USER_AGENT
from snekbooru.common.helpers import get_file_hash, get_media_headers, get_resource_path
from snekbooru.common.translations import _tr
from snekbooru.core.config import (SETTINGS, find_post_in_favorites,
                                   load_custom_boorus, load_downloads_data,
                                   load_favorites, load_highscores,
                                   load_search_history, load_tag_profile,
                                   save_downloads_data, save_favorites,
                                   save_highscores, save_search_history,
                                   save_settings, save_tag_profile) # noqa: E501
from snekbooru.core.manga_utils import normalize_http_url, resolve_manga_url
from snekbooru.core.persona import (empty_profile, load_profile as load_persona,
                                    _derive_source as _persona_source,
                                    record_download, record_hentai_open,
                                    record_manga_open, record_post_open, record_search,
                                    save_profile as save_persona, top_affinity_tags)
from snekbooru.core.book_export import (cleanup_images_folder, export_epub_from_images,
                                        export_mobi_from_images, export_pdf_from_images,
                                        export_png_zip_from_images, list_image_files)
from snekbooru.core.temp_cache import cleanup_snekbooru_temp, snekbooru_temp_dir
from snekbooru.core.workers import (AIStreamWorker, ApiWorker, AsyncApiWorker, ImageWorker,
                                    RecommendationFetcher)
from snekbooru.ui.dialogs import (BaseDialog, BulkDownloadDialog,
                                  BookExportDialog, HentaiSeriesDialog,
                                  HentaiVideoPreviewDialog, HentaiViewerDialog, MangaBookDialog, MangaDownloadExportDialog, SettingsDialog)
from snekbooru.ui.styling import (DARK_STYLESHEET, INCOGNITO_STYLESHEET,
                                  LIGHT_STYLESHEET, get_fonts_path,
                                  load_custom_themes, preprocess_stylesheet)
from snekbooru.ui.apollo_player import ApolloVideoPlayer
from snekbooru.ui.minigames import (PostShowdownGame, ImageScrambleGame, TagGuesserGame)
from snekbooru.ui.widgets import (AdBlocker, HentaiThumbnailWidget,
                                  ImageDropLabel, MangaListItem, ThumbnailWidget)
def probe_entries_from_result(result):
    if result is None: return []
    if isinstance(result, (list, tuple)): return list(result)
    if isinstance(result, dict):
        for key in ("results", "data", "items", "result", "entries", "manga"):
            val = result.get(key)
            if isinstance(val, (list, tuple)): return list(val)
        return [result]
    for attr in ("results", "data", "items", "result", "entries", "manga"):
        if hasattr(result, attr):
            try:
                val = getattr(result, attr)
                if isinstance(val, (list, tuple)): return list(val)
            except Exception: pass
    return [result]

def _call_search_fn(search_fn, query, page):
    try:
        sig = inspect.signature(search_fn)
        params = sig.parameters
        kwargs = {}
        if "page" in params:
            kwargs["page"] = page
        if "query" in params:
            kwargs["query"] = query
        elif "text" in params:
            kwargs["text"] = query
        elif "term" in params:
            kwargs["term"] = query
        elif "search" in params:
            kwargs["search"] = query
        if kwargs:
            try:
                return search_fn(**kwargs)
            except TypeError:
                pass
    except Exception:
        pass

    last_type_error = None
    for args in ((query, page), (query,)):
        try:
            return search_fn(*args)
        except TypeError as e:
            last_type_error = e
            continue

    if last_type_error:
        raise last_type_error
    return search_fn(query, page)


def MangaWebPage(*args, **kwargs):
    _ensure_webengine()
    class _MangaWebPage(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
            if isinstance(message, str) and "Unrecognized feature: 'cross-origin-isolated'" in message:
                return
            return super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
    return _MangaWebPage(*args, **kwargs)

def _mangadex_og_image_from_url(url):
    if not isinstance(url, str): return None
    match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]+)", url)
    if not match: return None
    return f"https://og.mangadex.org/og-image/manga/{match.group(1)}"

def _mangadex_pick_title(attrs):
    title_map = (attrs or {}).get("title") or {}
    if isinstance(title_map, dict):
        for key in ("en", "ja-ro", "ja", "ko", "zh", "es", "fr"):
            v = title_map.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in title_map.values():
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None

def _mangadex_cover_from_relationships(manga_id, relationships):
    for rel in (relationships or []):
        if isinstance(rel, dict) and rel.get("type") == "cover_art":
            file_name = (rel.get("attributes") or {}).get("fileName")
            if file_name:
                return f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}"
    return None

def _dict_to_ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _dict_to_ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_dict_to_ns(v) for v in obj]
    return obj

def _fetch_ehentai_entries(query=None, page=1, limit=50):
    base_url = "https://e-hentai.org/"
    scraper = cloudscraper.create_scraper()
    if query:
        search_url = f"{base_url}?f_search={quote_plus(query)}&page={max(0, int(page) - 1)}"
    else:
        search_url = f"{base_url}?page={max(0, int(page) - 1)}"
    r = scraper.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    entries = []
    items = soup.select("table.itg tr") or soup.select("div.gl1t")
    for item in items:
        link = item.find("a", href=re.compile(r"/g/\d+/[a-f0-9]+/"))
        if not link:
            continue
        url = link.get("href")
        gid, token = parse_gallery_id_token(url)
        title_elem = item.select_one(".glink") or item.select_one(".gl3t")
        title = title_elem.get_text(strip=True) if title_elem else (url or "")
        thumb_elem = item.find("img")
        thumb_url = ""
        if thumb_elem:
            thumb_url = thumb_elem.get("src") or thumb_elem.get("data-src") or ""
        entries.append({
            "id": f"{gid}/{token}" if gid and token else (url or ""),
            "url": url,
            "title": title,
            "thumbnail": thumb_url,
        })
        if len(entries) >= limit:
            break
    return entries

def _extract_title_from_value(value):
    if value is None: return None
    if isinstance(value, str):
        v = value.strip()
        return v if v else None
    if isinstance(value, dict):
        for sub in ("pretty", "english", "en", "japanese", "jp", "other", "name", "title"):
            if sub in value and isinstance(value[sub], str):
                v = value[sub].strip()
                if v:
                    return v
        for vv in value.values():
            if isinstance(vv, str):
                v = vv.strip()
                if v:
                    return v
    for attr in ("pretty", "english", "en", "japanese", "jp", "other", "name", "title"):
        if hasattr(value, attr):
            try:
                v = getattr(value, attr)
                if isinstance(v, str):
                    vv = v.strip()
                    if vv:
                        return vv
            except Exception: pass
    return None

def extract_cover_url(manga_obj):
    if not manga_obj:
        return None
        
    keys = ("cover", "thumbnail", "image", "images", "cover_url", "thumbnail_url", "thumbnail")
    sub_keys = ("uri", "url", "src")
    
    def _validate_url(url):
        if not isinstance(url, str): return None
        url = normalize_http_url(url)
        if url.startswith("http"): return url
        return _mangadex_og_image_from_url(url)

    if isinstance(manga_obj, dict):
        for k in keys:
            val = manga_obj.get(k)
            if not val: continue
            
            res = _validate_url(val)
            if res: return res
            
            if isinstance(val, dict):
                for sk in sub_keys:
                    res = _validate_url(val.get(sk))
                    if res: return res
            
            for sk in sub_keys:
                if hasattr(val, sk):
                    try:
                        res = _validate_url(getattr(val, sk))
                        if res: return res
                    except Exception: pass
    
    for k in keys:
        if hasattr(manga_obj, k):
            try:
                val = getattr(manga_obj, k)
                if not val: continue
                
                res = _validate_url(val)
                if res: return res
                
                if isinstance(val, (list, tuple)) and val:
                    first = val[0]
                    res = _validate_url(first)
                    if res: return res
                    for sk in sub_keys:
                        if hasattr(first, sk):
                            res = _validate_url(getattr(first, sk))
                            if res: return res
                
                for sk in sub_keys:
                    if hasattr(val, sk):
                        res = _validate_url(getattr(val, sk))
                        if res: return res
            except Exception: pass
            
    return None

def extract_title(manga_obj):
    if not manga_obj:
        return "<no title>"
        
    keys = ("title", "name", "pretty", "english", "en", "japanese", "jp", "other")
    
    if isinstance(manga_obj, dict):
        for k in keys:
            title = _extract_title_from_value(manga_obj.get(k))
            if title: return title
            
    for k in keys:
        if hasattr(manga_obj, k):
            try:
                title = _extract_title_from_value(getattr(manga_obj, k))
                if title: return title
            except Exception: pass
            
    for attr in ("url", "uri", "link", "page", "source_url"):
        val = manga_obj.get(attr) if isinstance(manga_obj, dict) else getattr(manga_obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
            
    for attr in ("id", "identifier", "uuid", "manga_id"):
        val = manga_obj.get(attr) if isinstance(manga_obj, dict) else getattr(manga_obj, attr, None)
        if val is not None:
            return str(val).strip()
            
    return repr(manga_obj)[:120] if manga_obj else "<no title>"


def number_to_png_display(number):
    try:
        number_str = str(number).replace(',', '')
        html_parts = []
        for digit in number_str:
            if digit.isdigit():
                digit_path = get_resource_path(os.path.join("graphics", f"{digit}.png"))
                if os.path.exists(digit_path):
                    pixmap = QPixmap(digit_path)
                    if not pixmap.isNull():
                        screen = QApplication.primaryScreen()
                        viewport_height = screen.geometry().height()
                        responsive_height = max(14, int(viewport_height * 0.15))
                        
                        scaled = pixmap.scaledToHeight(responsive_height, Qt.SmoothTransformation)
                        buffer = QBuffer()
                        buffer.open(QIODevice.WriteOnly)
                        scaled.save(buffer, "PNG")
                        image_data = base64.b64encode(buffer.data()).decode()
                        html_parts.append(f"<img src='data:image/png;base64,{image_data}' style='vertical-align: middle; margin: 0 1px; max-width: 100%;' />")
                    else:
                        html_parts.append(digit)
                else:
                    html_parts.append(digit)
            elif digit == ',':
                html_parts.append(",")
            else:
                html_parts.append(digit)
        return "".join(html_parts) if html_parts else str(number)
    except Exception:
        return str(number)

def detect_source_from_query(query: str) -> list:
    query_lower = query.lower()
    source_keywords = {
        "gelbooru": ["gel", "gelbooru"],
        "danbooru": ["dan", "danbooru", "dan booru"],
        "konachan": ["kona", "konachan"],
        "yandere": ["yan", "yandere"],
        "rule34": ["rule34", "rule 34"],
        "hypnohub": ["hypno", "hypnohub"],
        "xbooru": ["xbooru", "x booru"],
        "safebooru": ["safebooru", "safe booru"],
        "szurubooru": ["szurubooru", "szuru"],
        "mikubooru": ["mikubooru", "miku booru", "booru.funmaker"],
    }
    
    detected_sources = []
    for source, keywords in source_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_sources.append(source.capitalize() if source != "rule34" else "Rule34")
    
    if not detected_sources:
        detected_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
    
    return detected_sources

def _hhaven_get(path, params=None, quiet=False):
    try:
        resp = requests.get("https://cms.hentaihaven.xxx/wp-json" + path,
                            params=params,
                            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                            timeout=25)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if not quiet and e.response is not None and e.response.status_code not in (400, 404):
            print(f"hhaven {path} error: {e}")
        return None
    except Exception as e:
        if not quiet:
            print(f"hhaven {path} error: {e}")
        return None

HHAVEN_SERIES_FIELDS = "id,slug,title,date,link,meta,wp-manga-genre,wp-manga-tag"
_HH_GENRE_NAMES = {}

def _hhaven_thumb(path_or_url):
    if not path_or_url:
        return ""
    if path_or_url.startswith("http://"):
        return "https://" + path_or_url[len("http://"):]
    if path_or_url.startswith("https://"):
        return path_or_url
    return f"https://img.hentaihaven.xxx/{path_or_url.lstrip('/')}"

def _do_hhaven_fetch(mode, page=0, per_page=24, query="", genre_id=0, slug=""):
    try:
        if mode == "search":
            data = _hhaven_get("/wp/v2/wp-manga", params={
                "search": query, "per_page": per_page, "page": page + 1,
                "orderby": "relevance", "_fields": HHAVEN_SERIES_FIELDS}, quiet=True)
            return data or []
        if mode == "new":
            data = _hhaven_get("/wp/v2/wp-manga", params={
                "per_page": per_page, "page": page + 1, "orderby": "date",
                "order": "desc", "_fields": HHAVEN_SERIES_FIELDS})
            return data or []
        if mode == "genre":
            data = _hhaven_get("/wp/v2/wp-manga", params={
                "wp-manga-genre": genre_id, "per_page": per_page, "page": page + 1,
                "orderby": "date", "order": "desc", "_fields": HHAVEN_SERIES_FIELDS})
            return data or []
        if mode == "trending":
            data = _hhaven_get("/hhaven/v1/catalog/trending", params={"period": "month"})
            items = (data or {}).get("items", [])
            return items[page * per_page:(page + 1) * per_page]
        if mode == "popular":
            data = _hhaven_get("/hhaven/v1/catalog/ranked", params={"period": "all-time"})
            items = (data or {}).get("items", [])
            return items[page * per_page:(page + 1) * per_page]
        if mode == "random":
            return _do_hhaven_random(per_page)
        if mode == "genres":
            data = _hhaven_get("/hhaven/v1/genres")
            items = (data or {}).get("items", [])
            _HH_GENRE_NAMES.clear()
            for it in items if isinstance(items, list) else []:
                gid = it.get("id")
                if gid:
                    _HH_GENRE_NAMES[int(gid)] = it.get("name") or it.get("slug") or ""
            return items
        if mode == "episodes":
            data = _hhaven_get(f"/hhaven/v1/manga/by-slug/{slug}/chapters")
            return data or []
        if mode == "detail":
            data = _hhaven_get("/wp/v2/wp-manga", params={
                "slug": slug, "per_page": 1,
                "_fields": "id,slug,title,date,content,meta,wp-manga-genre,wp-manga-tag"})
            if isinstance(data, list) and data:
                return data[0]
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"hhaven fetch {mode} error: {e}")
        return []
    return []

def _do_hhaven_random(page_size=24):
    try:
        head = requests.get("https://cms.hentaihaven.xxx/wp-json/wp/v2/wp-manga",
                            params={"per_page": 1, "page": 1, "_fields": "id"},
                            headers={"User-Agent": USER_AGENT}, timeout=20)
        total = 1
        try:
            total = int(head.headers.get("X-WP-Total", 1))
        except Exception:
            pass
        pages = max(1, min(5000, (total + page_size - 1) // page_size))
        rand_page = random.randint(1, pages)
        data = _hhaven_get("/wp/v2/wp-manga", params={
            "per_page": page_size, "page": rand_page, "orderby": "date",
            "order": "desc", "_fields": HHAVEN_SERIES_FIELDS})
        if isinstance(data, list) and data:
            random.shuffle(data)
            return data[:page_size]
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"hhaven random error: {e}")
        return []

class ChatBrowser(QTextBrowser):
    def setSource(self, name):
        pass

class MainWindowTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("main_window_title_bar")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setScaledContents(True)
        self.title_label = QLabel("Snekbooru")
        self.title_label.setObjectName("custom_title_bar_label")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.minimize_btn = QToolButton(); self.minimize_btn.clicked.connect(self.parent.showMinimized)
        self.maximize_btn = QToolButton(); self.maximize_btn.clicked.connect(self.parent.toggle_maximize)
        self.close_btn = QToolButton(); self.close_btn.clicked.connect(self.parent.close)
        self.close_btn.setObjectName("close_button")

        self.update_icons() 

        for btn in [self.minimize_btn, self.maximize_btn, self.close_btn]:
            btn.setFixedSize(46, 32)
            btn.setObjectName("title_bar_button") 

        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)

        self.start_move_pos = None

    def _get_icon_color(self):
        palette = self.palette()
        bg_color = palette.color(self.backgroundRole())
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        return '#ffffff' if luminance < 0.5 else '#000000'

    def update_icons(self):
        icon_color = self._get_icon_color()
        self.minimize_btn.setIcon(qta.icon('fa5s.window-minimize', color=icon_color))
        self.close_btn.setIcon(qta.icon('fa5s.times', color=icon_color))
        self.update_maximize_icon()

    def update_maximize_icon(self):
        icon_color = self._get_icon_color()
        if self.parent.isMaximized():
            self.maximize_btn.setIcon(qta.icon('fa5s.window-restore', color=icon_color))
        else:
            self.maximize_btn.setIcon(qta.icon('fa5s.window-maximize', color=icon_color))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: self.start_move_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.start_move_pos and not self.parent.isMaximized():
            delta = event.globalPos() - self.start_move_pos
            self.parent.move(self.parent.pos() + delta)
            self.start_move_pos = event.globalPos()

    def mouseReleaseEvent(self, event): self.start_move_pos = None

class MediaViewerDialog(BaseDialog):
    def __init__(self, posts_list, current_index, parent=None):
        qt_parent = parent if isinstance(parent, QWidget) else None
        super().__init__("Media Viewer", qt_parent)

        self.parent_app = parent
        self.posts_list = posts_list
        self.current_index = current_index
        self.post = self.posts_list[self.current_index]
        self._view_started_at = time.time()

        self.setMinimumSize(800, 600)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        self.media_stack = QStackedWidget()
        self.content_layout.addWidget(self.media_stack, 1)

        self.image_scroll_area = QScrollArea()
        self.image_scroll_area.setWidgetResizable(True)
        self.image_label = QLabel(_tr("Loading image..."))
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_scroll_area.setWidget(self.image_label)
        self.media_stack.addWidget(self.image_scroll_area)

        self.apollo_video_player = ApolloVideoPlayer()
        self.media_stack.addWidget(self.apollo_video_player)
        
        self.download_progress_bar = QProgressBar(self.apollo_video_player)
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setValue(0)
        self.download_progress_bar.setFixedHeight(10)
        self.download_progress_bar.setTextVisible(False)
        self.download_progress_bar.setStyleSheet("QProgressBar { background: transparent; border: none; } QProgressBar::chunk { background: #3498db; }")
        self.download_progress_bar.hide()
        
        self.cv_video_player = None  
        self.temp_video_file = None
        self.threadpool = QThreadPool()
        self.image_pixmap = None
        self.gif_movie = None
        self.zoom_factor = 1.0
        self.cleanup_thread = None
        self.video_mode_active = False

        self.video_controls = QWidget()
        video_controls_layout = QHBoxLayout(self.video_controls)
        video_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.play_pause_button = QPushButton(qta.icon('fa5s.play'), "")
        self.play_pause_button.setFocusPolicy(Qt.NoFocus)
        self.rewind_10_button = QPushButton(qta.icon('fa5s.redo'), " -10s")
        self.rewind_10_button.setFocusPolicy(Qt.NoFocus)
        self.forward_10_button = QPushButton(qta.icon('fa5s.undo'), "+10s ")
        self.forward_10_button.setLayoutDirection(Qt.RightToLeft)
        self.forward_10_button.setFocusPolicy(Qt.NoFocus)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.duration_label = QLabel("--:-- / --:--")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.fullscreen_button = QPushButton(qta.icon('fa5s.expand'), "")
        self.fullscreen_button.setToolTip(_tr("Fullscreen (F)"))
        self.fullscreen_button.setFocusPolicy(Qt.NoFocus)
        
        self.loop_button = QPushButton(qta.icon('fa5s.redo'), "")
        self.loop_button.setCheckable(True)
        self.loop_button.setToolTip(_tr("Loop Video"))
        self.loop_button.setFocusPolicy(Qt.NoFocus)
        
        video_controls_layout.addWidget(self.play_pause_button)
        video_controls_layout.addWidget(self.rewind_10_button)
        video_controls_layout.addWidget(self.forward_10_button)
        video_controls_layout.addWidget(self.seek_slider)
        video_controls_layout.addWidget(self.duration_label)
        video_controls_layout.addWidget(self.volume_slider)
        video_controls_layout.addSpacing(10)
        video_controls_layout.addWidget(self.loop_button)
        video_controls_layout.addWidget(self.fullscreen_button)
        self.video_controls.setVisible(False) 

        controls_layout = QHBoxLayout()
        self.prev_button = QPushButton(qta.icon('fa5s.arrow-left'), _tr(" Previous"))
        self.prev_button.setFocusPolicy(Qt.NoFocus)
        self.next_button = QPushButton(qta.icon('fa5s.arrow-right'), _tr("Next "))
        self.next_button.setFocusPolicy(Qt.NoFocus)
        self.next_button.setLayoutDirection(Qt.RightToLeft)

        self.zoom_in_button = QPushButton(qta.icon('fa5s.search-plus'), "")
        self.zoom_in_button.setFocusPolicy(Qt.NoFocus)
        self.zoom_out_button = QPushButton(qta.icon('fa5s.search-minus'), "")
        self.zoom_out_button.setFocusPolicy(Qt.NoFocus)
        self.zoom_fit_button = QPushButton(qta.icon('fa5s.compress'), "")
        self.zoom_fit_button.setFocusPolicy(Qt.NoFocus)
        self.zoom_label = QLabel("100%")
        self.zoom_controls = [self.zoom_in_button, self.zoom_out_button, self.zoom_fit_button, self.zoom_label]

        self.fav_button = QPushButton(qta.icon('fa5s.star'), _tr(" Favorite"))
        self.fav_button.setFocusPolicy(Qt.NoFocus)
        self.download_button = QPushButton(qta.icon('fa5s.download'), _tr(" Download"))
        self.download_button.setFocusPolicy(Qt.NoFocus)
        self.open_browser_button = QPushButton(qta.icon('fa5s.external-link-alt'), _tr(" Open in Browser"))
        self.open_browser_button.setFocusPolicy(Qt.NoFocus)

        controls_layout.addWidget(self.prev_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.addStretch()
        controls_layout.addWidget(self.zoom_out_button)
        controls_layout.addWidget(self.zoom_label)
        controls_layout.addWidget(self.zoom_in_button)
        controls_layout.addWidget(self.zoom_fit_button)
        controls_layout.addStretch()
        controls_layout.addWidget(self.fav_button)
        controls_layout.addWidget(self.download_button)
        controls_layout.addWidget(self.open_browser_button)

        self.content_layout.addWidget(self.video_controls)
        self.content_layout.addLayout(controls_layout)

        self.prev_button.clicked.connect(self.prev_media)
        self.next_button.clicked.connect(self.next_media)
        self.fav_button.clicked.connect(self.toggle_favorite)
        self.download_button.clicked.connect(self.download_media)
        self.open_browser_button.clicked.connect(self.open_in_browser)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.rewind_10_button.clicked.connect(lambda: self.skip_video(-10))
        self.forward_10_button.clicked.connect(lambda: self.skip_video(10))
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.volume_slider.valueChanged.connect(self.set_video_volume)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.zoom_in_button.clicked.connect(lambda: self.zoom_image(1.25))
        self.zoom_out_button.clicked.connect(lambda: self.zoom_image(0.8))
        self.zoom_fit_button.clicked.connect(self.fit_image_to_window)

        self.apollo_video_player.position_changed.connect(self.update_position)
        self.apollo_video_player.duration_changed.connect(self.update_duration)
        self.apollo_video_player.state_changed.connect(self.update_play_pause_button)
        self.apollo_video_player.download_progress.connect(self.update_download_progress)
        self.apollo_video_player.error.connect(self.on_apollo_error)
        
        self.load_media()
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        self._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._shortcut_prev.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_prev.activated.connect(self._handle_left_key)
        
        self._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._shortcut_next.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_next.activated.connect(self._handle_right_key)

        self._shortcut_play = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._shortcut_play.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_play.activated.connect(self.toggle_play_pause)

        self._shortcut_fs = QShortcut(QKeySequence(Qt.Key_F), self)
        self._shortcut_fs.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_fs.activated.connect(self.toggle_fullscreen)

    def _handle_left_key(self):
        current_widget = self.media_stack.currentWidget()
        is_video_playing = current_widget == self.apollo_video_player
        modifiers = QApplication.keyboardModifiers()
        
        if is_video_playing and int(modifiers) == 0:
            self.skip_video(-10)
        else:
            self.prev_media()

    def _handle_right_key(self):
        current_widget = self.media_stack.currentWidget()
        is_video_playing = current_widget == self.apollo_video_player
        modifiers = QApplication.keyboardModifiers()
        
        if is_video_playing and int(modifiers) == 0:
            self.skip_video(10)
        else:
            self.next_media()

    def wheelEvent(self, event):
        if self.media_stack.currentWidget() == self.image_scroll_area:
            self.zoom_image(1.1 if event.angleDelta().y() > 0 else 1 / 1.1)

    def update_controls(self):
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.posts_list) - 1)
        
        is_favorited = find_post_in_favorites(self.post.get('id'), self.parent_app.favorites) is not None
        fav_icon_color = 'yellow' if is_favorited else None
        self.fav_button.setIcon(qta.icon('fa5s.star', color=fav_icon_color))

    def load_media(self):
        self._stop_current_playback()
        self._update_window_title()
        self.update_controls()

        file_info = self._get_media_file_info()
        if not file_info["url"]:
            self.image_label.setText(_tr("Error: No file found."))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            return

        if file_info["is_video"]:
            self._handle_video_load(file_info)
        elif file_info["is_gif"]:
            self._handle_gif_load(file_info)
        else:
            self._handle_image_load(file_info)

    def _report_current_view(self):
        if getattr(self, '_view_started_at', None) is None:
            return
        elapsed = time.time() - self._view_started_at
        self._view_started_at = time.time()
        if elapsed < 1.0:
            return
        report = getattr(self.parent_app, 'report_view', None)
        if callable(report):
            try:
                report(self.post, elapsed)
            except Exception as e:
                print(f"Error reporting view: {e}")

    def _stop_current_playback(self):
        if self.video_mode_active or self.media_stack.currentWidget() == self.apollo_video_player:
            self.apollo_video_player.exit()
        self.video_mode_active = False
        if self.gif_movie: 
            self.gif_movie.stop()
        self.gif_movie = None
        self.image_pixmap = None
        self.zoom_factor = 1.0

    def _update_window_title(self):
        title = f"Snekbooru Media Viewer - Post {self.post.get('id')}"
        self.setWindowTitle(title)
        self.title_bar.title_label.setText(title)

    def _get_media_file_info(self):
        file_ext = self.post.get('file_ext', '').lower()
        local_path = self.post.get('local_path')
        use_local = local_path and os.path.exists(local_path)
        
        if use_local:
            local_ext = os.path.splitext(local_path)[1].lower().lstrip('.')
            if local_ext:
                file_ext = local_ext
        
        file_url = local_path if use_local else self.post.get('file_url')
        if not use_local and isinstance(file_url, str):
            file_url = normalize_http_url(file_url).replace("\\", "/")
            
        return {
            "url": file_url,
            "ext": file_ext,
            "is_local": use_local,
            "is_video": file_ext in ['mp4', 'webm', 'mov', 'avi', 'mkv'],
            "is_gif": file_ext == 'gif'
        }

    def _handle_video_load(self, info):
        self.video_mode_active = True
        self.video_controls.setVisible(True)
        for w in self.zoom_controls: w.setVisible(False)
        
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setValue(0)
        self.duration_label.setText("00:00 / 00:00")

        if info["is_local"]:
            self._load_video_file(info["url"])
        else:
            video_playback_method = SETTINGS.get("video_playback_method", _tr("Download First (Reliable)"))
            if video_playback_method == _tr("Stream (Experimental)"):
                self.media_stack.setCurrentWidget(self.apollo_video_player)
                self._load_video_stream(info["url"])
            else:
                self.image_label.setText(_tr("Loading video..."))
                self.media_stack.setCurrentWidget(self.image_scroll_area)
                worker = ApiWorker(self._download_video_to_temp, info["url"], self.post.get('id', 'temp'))
                worker.signals.finished.connect(self._on_video_downloaded)
                self.threadpool.start(worker)

    def _handle_gif_load(self, info):
        self.video_mode_active = False
        self.video_controls.setVisible(False)
        for w in self.zoom_controls: w.setVisible(False)
        self.image_label.setText(_tr("Loading GIF..."))
        self.media_stack.setCurrentWidget(self.image_scroll_area)
        
        if info["is_local"]:
            try:
                with open(info["url"], "rb") as f:
                    self._on_gif_data_loaded((f.read(), None), None)
            except Exception as e:
                self.image_label.setText(_tr("Error loading GIF: {error}").format(error=str(e)))
        else:
            worker = ApiWorker(self._fetch_raw_data, info["url"])
            worker.signals.finished.connect(self._on_gif_data_loaded)
            self.threadpool.start(worker)

    def _handle_image_load(self, info):
        self.video_mode_active = False
        self.video_controls.setVisible(False)
        for w in self.zoom_controls: w.setVisible(True)
        self.image_label.setText(_tr("Loading image..."))
        self.media_stack.setCurrentWidget(self.image_scroll_area)
        
        if info["is_local"]:
            self.on_image_loaded(QPixmap(info["url"]), self.post)
        else:
            worker = ImageWorker(info["url"], self.post)
            worker.signals.finished.connect(self.on_image_loaded)
            self.threadpool.start(worker)

    def on_image_loaded(self, pixmap, post):
        if post is not None and self.post is not None and post.get("id") != self.post.get("id"):
            return
        self.image_pixmap = pixmap
        if not pixmap.isNull():
            self.fit_image_to_window()
        else:
            self.image_label.setText(_tr("Error: Could not load image."))

    def _fetch_raw_data(self, url):
        try:
            if isinstance(url, str):
                url = normalize_http_url(url).replace("\\", "/")
            if os.path.exists(url):
                with open(url, "rb") as f:
                    return f.read(), None
            if url.startswith("file://"):
                local_path = QUrl(url).toLocalFile()
                if local_path and os.path.exists(local_path):
                    with open(local_path, "rb") as f:
                        return f.read(), None
            r = requests.get(url, headers=get_media_headers(url), timeout=30)
            r.raise_for_status()
            return r.content, None
        except Exception as e:
            return None, str(e)

    def _on_gif_data_loaded(self, data, err):
        gif_content, function_error = data

        if err or function_error or not gif_content:
            self.image_label.setText(_tr("Error loading GIF: {error}").format(error=err or "Unknown"))
            return

        self.gif_byte_array = QByteArray(gif_content)
        self.gif_buffer = QBuffer(self.gif_byte_array)
        self.gif_buffer.open(QIODevice.ReadOnly)

        self.gif_movie = QMovie()
        self.gif_movie.setDevice(self.gif_buffer)
        self.image_label.setMovie(self.gif_movie)
        self.gif_movie.start()

    def _download_video_to_temp(self, url, post_id):
        import tempfile
        try:
            file_ext = '.mp4'
            fd, self.temp_video_file = tempfile.mkstemp(dir=snekbooru_temp_dir("media"), suffix=file_ext)
            os.close(fd)
            
            try:
                if isinstance(url, str):
                    url = normalize_http_url(url).replace("\\", "/")
                response = requests.get(
                    url, 
                    timeout=300, 
                    headers=get_media_headers(url), 
                    stream=True
                )
                if response.status_code == 200:
                    with open(self.temp_video_file, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if os.path.getsize(self.temp_video_file) > 0:
                        try:
                            ct = str(response.headers.get("Content-Type") or "").lower()
                            with open(self.temp_video_file, "rb") as f:
                                head = f.read(2048)
                            head_low = head.lower()
                            if "text/" in ct or b"<html" in head_low or b"<!doctype" in head_low:
                                return None, "Downloaded content is not a video (blocked or HTML response)."
                        except Exception:
                            pass
                        return self.temp_video_file, None
                    else:
                        return None, "Downloaded file is empty"
                else:
                    return None, f"Download failed with status code {response.status_code}"
            except requests.Timeout:
                return None, "Video download timed out"
            except Exception as e:
                return None, f"Download failed: {str(e)}"
        except Exception as e:
            if os.path.exists(self.temp_video_file):
                try:
                    os.remove(self.temp_video_file)
                except:
                    pass
            return None, str(e)

    def _on_video_downloaded(self, data, err):
        if err or not data:
            self.image_label.setText(_tr("Error loading video: {error}").format(error=err or "Unknown"))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            return

        filepath, _ = data
        if not filepath or not os.path.exists(filepath):
            self.image_label.setText(_tr("Error: Video file not found"))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            return
        
        self.media_stack.setCurrentWidget(self.apollo_video_player)
        
        self._load_video_file(filepath)

    def _load_video_stream(self, url):
        try:
            if isinstance(url, str):
                url = normalize_http_url(url).replace("\\", "/")
            self.apollo_video_player.load(url)
            self.apollo_video_player.play()
        except Exception as e:
            self.image_label.setText(_tr("Error: Could not play video: {error}").format(error=str(e)))
            self.media_stack.setCurrentWidget(self.image_scroll_area)

    def _load_video_file(self, filepath):
        try:
            self.media_stack.setCurrentWidget(self.apollo_video_player)
            self.apollo_video_player.load(filepath)
            self.apollo_video_player.play()

        except Exception as e:
            self.image_label.setText(_tr("Error: Could not play video: {error}").format(error=str(e)))
            self.media_stack.setCurrentWidget(self.image_scroll_area)

    def on_apollo_error(self, error_msg):
        if not self.video_mode_active:
            return
        self.image_label.setText(_tr("Video Error: {error}").format(error=error_msg))
        self.media_stack.setCurrentWidget(self.image_scroll_area)
        self.video_controls.setVisible(False)
        self.download_progress_bar.hide()
    
    def update_download_progress(self, progress):
        if progress > 0 and progress < 100:
            self.download_progress_bar.show()
            self.download_progress_bar.setValue(int(progress))
            self.download_progress_bar.setGeometry(0, self.apollo_video_player.height() - 10, self.apollo_video_player.width(), 10)
        else:
            self.download_progress_bar.hide()
    
    def _format_time(self, seconds):
        if seconds < 0:
            seconds = 0
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def _on_slider_moved(self, slider_value):
        self.apollo_video_player.seek(slider_value)

    def update_position(self, position):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        
        duration = self.seek_slider.maximum()
        pos_str = self._format_time(position / 1000)
        dur_str = self._format_time(duration / 1000) if duration > 0 else "--:--"
        self.duration_label.setText(f"{pos_str} / {dur_str}")

    def update_duration(self, duration):
        if duration > 0:
            self.seek_slider.setRange(0, duration)
            self.seek_slider.setEnabled(True)
        else:
            self.seek_slider.setRange(0, 0)
            self.seek_slider.setEnabled(False)
    
    def _cleanup_temp_video(self, wait_on_close=False):
        if self.temp_video_file and os.path.exists(self.temp_video_file):
            filepath_to_delete = self.temp_video_file
            self.temp_video_file = None

            def robust_delete():
                max_attempts = 30 if wait_on_close else 120
                for _ in range(max_attempts):
                    if not os.path.exists(filepath_to_delete):
                        return
                    try:
                        os.remove(filepath_to_delete)
                        return 
                    except OSError:
                        time.sleep(0.5) 

            is_daemon = not wait_on_close
            thread = threading.Thread(target=robust_delete, daemon=is_daemon)
            thread.start()

            if wait_on_close:
                self.cleanup_thread = thread

    def prev_media(self):
        self._report_current_view()
        self.apollo_video_player.exit()
        if self.gif_movie: self.gif_movie.stop()
        self._cleanup_temp_video()
        if self.current_index > 0:
            self.current_index -= 1
            self.post = self.posts_list[self.current_index]
            self.load_media()

    def next_media(self):
        self._report_current_view()
        self.apollo_video_player.exit()
        if self.gif_movie: self.gif_movie.stop()
        self._cleanup_temp_video()
        if self.current_index < len(self.posts_list) - 1:
            self.current_index += 1
            self.post = self.posts_list[self.current_index]
            self.load_media()

    def toggle_favorite(self):
        if self.parent_app:
            self.parent_app.toggle_favorite(self.post)
            self.update_controls()

    def download_media(self):
        if self.parent_app:
            self.parent_app.download_post(self.post)

    def toggle_play_pause(self):
        if self.apollo_video_player.is_playing:
            self.apollo_video_player.pause()
        else:
            self.apollo_video_player.play()

    def update_play_pause_button(self, state):
        is_playing = (state == 'playing')
        if is_playing:
            self.play_pause_button.setIcon(qta.icon('fa5s.pause'))
        else:
            self.play_pause_button.setIcon(qta.icon('fa5s.play'))
            if state == 'stopped' and self.loop_button.isChecked():
                self.apollo_video_player.play()

    def skip_video(self, seconds):
        if self.apollo_video_player.player:
            current_pos = self.apollo_video_player.player.get_position_ms()
            self.apollo_video_player.seek(current_pos + (seconds * 1000))

    def set_video_volume(self, volume):
        self.apollo_video_player.set_volume(volume)

    def toggle_fullscreen(self):
        self.apollo_video_player.toggle_fullscreen()
        if self.isFullScreen():
            self.fullscreen_button.setIcon(qta.icon('fa5s.compress'))
        else:
            self.fullscreen_button.setIcon(qta.icon('fa5s.expand'))

    def zoom_image(self, factor):
        if not self.image_pixmap: return
        self.zoom_factor *= factor
        self.update_zoomed_image()

    def fit_image_to_window(self):
        if not self.image_pixmap: return
        pixmap_size = self.image_pixmap.size()
        viewport_size = self.image_scroll_area.viewport().size()
        if pixmap_size.width() == 0 or pixmap_size.height() == 0: return

        w_ratio = viewport_size.width() / pixmap_size.width()
        h_ratio = viewport_size.height() / pixmap_size.height()
        self.zoom_factor = min(w_ratio, h_ratio)
        self.update_zoomed_image()

    def update_zoomed_image(self):
        if not self.image_pixmap: return
        new_size = self.image_pixmap.size() * self.zoom_factor
        self.image_label.setPixmap(self.image_pixmap.scaled(new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.zoom_label.setText(f"{self.zoom_factor:.0%}")

    def open_in_browser(self):
        url = self.post.get("source_post_url")
        if url:
            webbrowser.open(url)
            
    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return 
        
        if event.key() == Qt.Key_F:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.media_stack.currentWidget() == self.image_scroll_area:
            self.fit_image_to_window()

    def closeEvent(self, event):
        self._report_current_view()
        try:
            pass
        except Exception:
            pass
        
        if self.gif_movie:
            self.gif_movie.stop()
        
        self._cleanup_temp_video(wait_on_close=True)
        
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=6.0) 

        super().closeEvent(event)


class SourceFetchThread(QThread):
    finished = pyqtSignal(object, list, dict, object)
    progress = pyqtSignal(object, int)

    def __init__(self, source_identifier, parent_app, max_items=50, delay_between_pages=0.2, query=None):
        super().__init__()
        self.source_identifier = source_identifier
        self.parent_app = parent_app
        self.max_items = max_items
        self.delay_between_pages = delay_between_pages
        self.query = query

    def run(self):
        try:
            if not self.parent_app.enma:
                source_name = getattr(self.source_identifier, "name", str(self.source_identifier))
                source_meta = {"name": source_name, "query": self.query}
                entries = self.parent_app._fetch_manga_without_enma(source_name, self.query, self.max_items)
                self.progress.emit(self.source_identifier, len(entries))
                self.finished.emit(self.source_identifier, entries[:self.max_items], source_meta, None)
                return

            enma = self.parent_app.enma

            enma.source_manager.set_source(self.source_identifier)
            source = enma.source_manager.source
            source_name = getattr(source, "name", None) or getattr(self.source_identifier, "name", str(self.source_identifier))
            if source_name.upper() == "NHENTAI":
                source_name = "e-Hentai"
            source_meta = {"name": source_name}
            source_meta["query"] = self.query
            for attr in ("base_url", "base", "home_url", "site_url", "website", "url", "domain"):
                try:
                    val = getattr(source, attr, None)
                except Exception:
                    val = None
                if isinstance(val, str) and val.strip():
                    source_meta[attr] = val.strip()
            collected = []
            if isinstance(self.query, str) and self.query.strip():
                search_fn = getattr(source, "search", None) or getattr(source, "search_manga", None)
                if callable(search_fn):
                    page = 1
                    while len(collected) < self.max_items and page < 20:
                        if self.isInterruptionRequested():
                            break
                        try:
                            res = _call_search_fn(search_fn, self.query.strip(), page)
                        except Forbidden:
                            is_ehentai = False
                            try:
                                is_ehentai = self.source_identifier == Sources.NHENTAI
                            except Exception:
                                is_ehentai = False
                            if not is_ehentai and isinstance(self.source_identifier, str):
                                is_ehentai = "e-hentai" in self.source_identifier.lower()
                            
                            raise
                        entries = probe_entries_from_result(res)
                        if not entries:
                            break
                        collected.extend(entries)
                        self.progress.emit(self.source_identifier, len(collected))
                        page += 1
                        time.sleep(self.delay_between_pages)
            else:
                paginate_fn = getattr(source, "paginate", None)
                if callable(paginate_fn):
                    page = 1
                    while len(collected) < self.max_items and page < 20:
                        if self.isInterruptionRequested():
                            break
                        res = paginate_fn(page=page)
                        entries = probe_entries_from_result(res)
                        if not entries: break
                        collected.extend(entries)
                        self.progress.emit(self.source_identifier, len(collected))
                        page += 1
                        time.sleep(self.delay_between_pages)
            self.finished.emit(self.source_identifier, collected[:self.max_items], source_meta, None)
        except Exception as e:
            tb = traceback.format_exc()
            self.finished.emit(self.source_identifier, [], {}, {"exception": str(e), "trace": tb})


class ChatBubble(QFrame):
    edit_requested = pyqtSignal(object)
    retry_requested = pyqtSignal(object)

    def __init__(self, text="", is_user=False, parent=None, msg_index=-1):
        super().__init__(parent)
        self.is_user = is_user
        self.msg_index = msg_index
        self.setObjectName("chat_bubble")
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QFrame#chat_bubble { background: transparent; }")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(1)

        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 1, 0, 1)

        self.bubble = QFrame()
        self.bubble.setObjectName("bubble_inner")
        if is_user:
            self.bubble.setStyleSheet(
                "QFrame#bubble_inner { background: #2563eb; border-radius: 14px; "
                "border-bottom-right-radius: 4px; padding: 8px 10px; }"
            )
        else:
            self.bubble.setStyleSheet(
                "QFrame#bubble_inner { background: #1e293b; border-radius: 14px; "
                "border-bottom-left-radius: 4px; padding: 8px 10px; }"
            )
        screen_w = QApplication.primaryScreen().size().width()
        self.bubble.setMaximumWidth(int(screen_w * 0.5))

        self.bubble_layout = QVBoxLayout(self.bubble)
        self.bubble_layout.setContentsMargins(0, 0, 0, 0)
        self.bubble_layout.setSpacing(0)

        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.RichText)
        self.text_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.text_label.setOpenExternalLinks(False)
        self.text_label.setStyleSheet(
            "QLabel { background: transparent; color: %s; border: none; }" % (
                "#fff" if is_user else "#e2e8f0"
            )
        )
        self.text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.bubble_layout.addWidget(self.text_label)

        if is_user:
            self.row.addStretch()
            self.row.addWidget(self.bubble)
        else:
            self.row.addWidget(self.bubble)
            self.row.addStretch()

        self.main_layout.addLayout(self.row)

        self.btn_row = QHBoxLayout()
        self.btn_row.setContentsMargins(0, 0, 0, 0)
        self.btn_row.setSpacing(0)

        if is_user:
            self.btn_row.addStretch()
            self.edit_btn = QToolButton()
            self.edit_btn.setIcon(qta.icon('fa5s.pencil-alt', color='#94a3b8'))
            self.edit_btn.setAutoRaise(True)
            self.edit_btn.setToolTip(_tr("Edit"))
            self.edit_btn.setStyleSheet("QToolButton { border: none; background: transparent; padding: 2px; }")
            self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self))
            self.btn_row.addWidget(self.edit_btn)

            self.retry_btn = QToolButton()
            self.retry_btn.setIcon(qta.icon('fa5s.redo', color='#94a3b8'))
            self.retry_btn.setAutoRaise(True)
            self.retry_btn.setToolTip(_tr("Retry"))
            self.retry_btn.setStyleSheet("QToolButton { border: none; background: transparent; padding: 2px; }")
            self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self))
            self.btn_row.addWidget(self.retry_btn)

        self.main_layout.addLayout(self.btn_row)

    def _icon_color(self):
        try:
            w = self.window()
            if w:
                bg = w.palette().color(w.backgroundRole())
                lum = (0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()) / 255.0
                return '#ffffff' if lum < 0.5 else '#000000'
        except Exception:
            pass
        return '#94a3b8'

    def set_text(self, text):
        self.text_label.setText(text)

    def append_text(self, chunk):
        self.text_label.setText(self.text_label.text() + chunk)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            menu = QMenu(self)
            if self.is_user:
                edit_action = menu.addAction(qta.icon('fa5s.pencil-alt'), _tr("Edit"))
                edit_action.triggered.connect(lambda: self.edit_requested.emit(self))
            else:
                retry_action = menu.addAction(qta.icon('fa5s.redo'), _tr("Retry"))
                retry_action.triggered.connect(lambda: self.retry_requested.emit(self))
            menu.exec_(event.globalPos())
        super().mousePressEvent(event)


class ChatImageBubble(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, pixmap, post, parent=None):
        super().__init__(parent)
        self.post = post
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QFrame { background: transparent; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)

        screen_h = QApplication.primaryScreen().size().height()
        max_h = int(screen_h * 0.28)
        scaled = pixmap.scaledToHeight(min(max_h, pixmap.height()), Qt.SmoothTransformation)

        self.img_label = QLabel()
        self.img_label.setPixmap(scaled)
        self.img_label.setCursor(Qt.PointingHandCursor)
        self.img_label.setStyleSheet("QLabel { border-radius: 8px; background: transparent; }")
        layout.addWidget(self.img_label)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.post)
        super().mousePressEvent(event)


class ChatRefCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, title, pixmap, ref_data, parent=None):
        super().__init__(parent)
        self.ref_data = ref_data
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.img_label = QLabel()
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaledToHeight(60, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled)
        else:
            self.img_label.setFixedSize(80, 60)
            self.img_label.setText("N/A")
            self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setStyleSheet("background: #333; border-radius: 4px;")
        layout.addWidget(self.img_label)

        text_layout = QVBoxLayout()
        title_lbl = QLabel(f"<b>{title[:80]}</b>")
        title_lbl.setWordWrap(True)
        title_lbl.setTextFormat(Qt.RichText)
        text_layout.addWidget(title_lbl)
        subtitle = ref_data.get("type", "").title()
        if subtitle:
            cat = QLabel(subtitle)
            cat.setStyleSheet("color: #888; font-size: 10px;")
            text_layout.addWidget(cat)
        text_layout.addStretch()
        layout.addLayout(text_layout, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ref_data)
        super().mousePressEvent(event)


class ChatMessageList(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(4)
        self.layout.addStretch()
        self.setWidget(self.container)

        self.bubbles = []

    def add_bubble(self, bubble):
        self.layout.insertWidget(self.layout.count() - 1, bubble)
        self.bubbles.append(bubble)
        QTimer.singleShot(50, self._scroll_bottom)

    def _scroll_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


class GelDanApp(QWidget):
    def __init__(self, is_incognito=False):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.is_incognito_window = is_incognito

        self.title_bar = MainWindowTitleBar(self)

        self.setObjectName("main_window")
        self.apply_window_settings()
        self.center_on_screen()

        self.posts = []
        self.limit = QSpinBox()
        self.limit.setRange(1, 1000); self.limit.setValue(SETTINGS.get("posts_per_page", 60))
        self.limit.setSuffix(_tr(" posts"))
        self.limit.setToolTip(_tr("Number of posts to load per page."))
        self.pid = 0
        self.selected_for_bulk = set()
        self.post_to_widget_map = {}
        self.id_to_post_map = {}
        self.tag_profile = load_tag_profile()
        self.persona = empty_profile() if is_incognito else load_persona()
        self.favorites = load_favorites()
        self.custom_boorus = load_custom_boorus()
        self.search_history = load_search_history()
        self.last_suggestion_prefix = ""
        self.highscores = load_highscores()
        self.custom_themes = {}
        self.custom_fonts_path = ""
        self.incognito_windows = []
        self.fav_post_to_widget_map = {}
        self.current_favorites_category = "Uncategorized"
        self.open_dialogs = []
        self.last_selected = None
        self.downloads_data = {}
        self.media_viewer_processes = []
        try:
            if ENMA_AVAILABLE and Enma is not None:
                self.enma = Enma()
                scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "linux", "mobile": False})
                try:
                    scraper.headers.update(
                        {
                            "User-Agent": USER_AGENT,
                            "Accept": "*/*",
                            "Accept-Language": "en-US,en;q=0.9",
                        }
                    )
                except Exception:
                    pass
                self.enma.source_manager.http_client = scraper
                self._enma_scraper = scraper
            else:
                self.enma = None
                # print("Enma is unavailable in this Python environment. Manga/e-Hentai source features are disabled.")
                print("Stale Enma, don't worry about this warning.")
        except Exception as e:
            print(f"Could not initialize Enma: {e}")
            self.enma = None

        self.reco_posts = []
        self.reco_post_to_widget_map = {}
        self.downloads_posts = []
        self.downloads_post_to_widget_map = {}
        self.hotkey_sequences = {}
        self.hotkey_shortcuts = {}
        self.manga_entries_cache = {}
        self.manga_search_cache = {}
        self.manga_thumb_cache = {}
        self.manga_threads = {}
        self.manga_current_source_id = "ALL"
        self.ai_chat_ui = {}
        self.ai_search_results = {}
        self.ai_chat_displayed_posts = {}  
        self.ai_chat_message_count = {}  
        self.ai_input_areas = []
        self.ai_can_send = True
        self.ai_cooldown_timer = QTimer(self)

        self.threadpool = QThreadPool()

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("main_tabs")
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.home_tab = self.create_home_tab()
        self.home_tab.setObjectName("home_tab")
        self.browser_tab = self.create_browser_tab()
        self.browser_tab.setObjectName("browser_tab")
        self.favorites_tab = self.create_favorites_tab()
        self.favorites_tab.setObjectName("favorites_tab")
        self.downloads_tab = self.create_downloads_tab()
        self.downloads_tab.setObjectName("downloads_tab")
        self.manga_tab = self.create_manga_tab()
        self.manga_tab.setObjectName("manga_tab")
        self.hentai_tab = self.create_hentai_tab()
        self.ai_tab = self.create_ai_tab(); self.ai_tab.setObjectName("ai_tab")
        self.minigames_tab = self.create_minigames_tab()

        self.tabs.addTab(self.home_tab, qta.icon('fa5s.home'), _tr("Home")) #0
        self.tabs.addTab(self.browser_tab, qta.icon('fa5s.images'), _tr("Browser")) #1
        self.tabs.addTab(self.favorites_tab, qta.icon('fa5s.star', color='yellow'), _tr("Favorites")) #2
        self.tabs.addTab(self.downloads_tab, qta.icon('fa5s.download'), _tr("Downloads")) #3
        self.tabs.addTab(self.hentai_tab, qta.icon('fa5s.heart', color='#ff79c6'), _tr("Hentai")) #4
        self.tabs.addTab(self.manga_tab, qta.icon('fa5s.book-open'), _tr("Manga")) #4
        self.tabs.addTab(self.minigames_tab, qta.icon('fa5s.gamepad'), _tr("Minigames")) #6
        self.tabs.addTab(self.ai_tab, qta.icon('fa5s.robot'), _tr("AI")) #5
 
        top_controls_bar = QHBoxLayout()
        top_controls_bar.addStretch(1); self.source_title_label = QLabel(_tr("Source:"))
        self.source_lbl = QLabel(SETTINGS.get("source", "Gelbooru"))
        top_controls_bar.addWidget(self.source_title_label)
        top_controls_bar.addWidget(self.source_lbl, 1, Qt.AlignLeft)
        top_controls_bar.addSpacing(20)
        self.settings_btn = QPushButton(qta.icon('fa5s.cogs'), _tr(" Settings"))
        self.settings_btn.clicked.connect(self.open_settings)
        top_controls_bar.addWidget(self.settings_btn)
        outer.addWidget(self.title_bar)
        outer.addLayout(top_controls_bar)
        outer.addWidget(self.tabs)        
        
        self.load_app_icon()
        
        self.installEventFilter(self)
        try:
            QApplication.instance().installEventFilter(self)
        except Exception:
            pass

        os.makedirs(SETTINGS.get("download_dir"), exist_ok=True)

        self.media_viewer_queue = Queue()
        self.queue_checker = QTimer(self)
        self.queue_checker.timeout.connect(self.check_media_viewer_queue)
        self.queue_checker.start(100)

        self.load_hotkeys()
        self._configure_temp_cleanup_timer()
        self.update_source_label()
        self.fetch_site_stats()
        if self.is_incognito_window:
            self.settings_btn.setEnabled(False)
            self.tabs.setTabVisible(self.tabs.indexOf(self.home_tab), False)
            self.tabs.setTabVisible(self.tabs.indexOf(self.downloads_tab), False)
            self.tabs.setTabVisible(self.tabs.indexOf(self.favorites_tab), False)
            self.tabs.setTabVisible(self.tabs.indexOf(self.minigames_tab), False)
            self.tabs.setCurrentIndex(1) 
        else:
            self.tabs.setCurrentIndex(0) 
        
        self.apply_theme()

    def _configure_temp_cleanup_timer(self):
        if not hasattr(self, "temp_cleanup_timer"):
            self.temp_cleanup_timer = QTimer(self)
            self.temp_cleanup_timer.timeout.connect(self._run_temp_cleanup)
        minutes = int(SETTINGS.get("temp_cleanup_minutes", 5) or 5)
        minutes = max(1, min(minutes, 240))
        self.temp_cleanup_timer.start(60 * 1000)
        self._temp_cleanup_ttl_seconds = minutes * 60

    def _run_temp_cleanup(self):
        ttl = getattr(self, "_temp_cleanup_ttl_seconds", int(SETTINGS.get("temp_cleanup_minutes", 5) or 5) * 60)
        cleanup_snekbooru_temp(ttl)
        self.manga_thumb_cache.clear()

    def _mangadex_request(self, path, params=None, timeout=30):
        base = "https://api.mangadex.org"
        r = requests.get(f"{base}{path}", params=params or {}, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def _fetch_mangadex_entries(self, query=None, limit=50):
        params = {"limit": min(max(int(limit or 50), 1), 100), "offset": 0, "includes[]": ["cover_art"]}
        if query:
            params["title"] = query
            params["order[relevance]"] = "desc"
        else:
            params["order[followedCount]"] = "desc"
        payload = self._mangadex_request("/manga", params=params)
        entries = []
        for item in payload.get("data", []) or []:
            manga_id = item.get("id")
            attrs = item.get("attributes") or {}
            title = _mangadex_pick_title(attrs) or manga_id
            desc_map = attrs.get("description") or {}
            desc = desc_map.get("en") if isinstance(desc_map, dict) else None
            cover = _mangadex_cover_from_relationships(manga_id, item.get("relationships"))
            entries.append({
                "id": manga_id,
                "title": title,
                "url": f"https://mangadex.org/title/{manga_id}",
                "thumbnail": cover,
                "description": desc or "",
            })
        return entries

    def _fetch_mangadex_chapters_pages(self, manga_id):
        chapters = []
        offset = 0
        while True:
            params = {
                "manga": manga_id,
                "limit": 100,
                "offset": offset,
                "order[chapter]": "asc",
            }
            payload = self._mangadex_request("/chapter", params=params, timeout=45)
            rows = payload.get("data", []) or []
            if not rows:
                break
            for row in rows:
                chap_id = row.get("id")
                if not chap_id:
                    continue
                ch_attrs = row.get("attributes") or {}
                label = ch_attrs.get("title") or ch_attrs.get("chapter") or ch_attrs.get("volume") or chap_id
                at_home = self._mangadex_request(f"/at-home/server/{chap_id}", timeout=45)
                base_url = at_home.get("baseUrl")
                chapter_obj = at_home.get("chapter") or {}
                chap_hash = chapter_obj.get("hash")
                pages = chapter_obj.get("data") or []
                page_urls = []
                if base_url and chap_hash:
                    page_urls = [f"{base_url}/data/{chap_hash}/{name}" for name in pages]
                chapters.append({"label": str(label), "pages": page_urls})
            offset += len(rows)
            if len(rows) < 100:
                break
        return chapters

    def _fetch_manga_without_enma(self, source_name, query, max_items):
        src = str(source_name).upper()
        if src == "MANGADEX":
            return self._fetch_mangadex_entries(query=query, limit=max_items)
        if src in ("NHENTAI", "E-HENTAI", "EHENTAI"):
            return _fetch_ehentai_entries(query=query, page=1, limit=max_items)
        return []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'tabs') and SETTINGS.get("auto_scale_grid", False):
            self.refresh_visible_grid()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.update_maximize_icon()
        super().changeEvent(event)

    def center_on_screen(self):
        self.move(QApplication.desktop().screen().rect().center() - self.rect().center())

    def keyPressEvent(self, event):
        is_typing = isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QTextEdit, QTextBrowser, QKeySequenceEdit))

        for action, seq in self.hotkey_sequences.items():
            key_seq = QKeySequence(event.key() | int(event.modifiers()))
            alt_seq = None
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                mod_mask = int(Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
                mods = int(event.modifiers()) & mod_mask
                other_key = Qt.Key_Enter if event.key() == Qt.Key_Return else Qt.Key_Return
                alt_seq = QKeySequence(int(other_key) | mods)
            if seq.matches(key_seq) == QKeySequence.ExactMatch or (alt_seq and seq.matches(alt_seq) == QKeySequence.ExactMatch):
                self.handle_hotkey_action(action, is_typing)
                event.accept()
                return

        super().keyPressEvent(event)

    def handle_hotkey_action(self, action, is_typing):
        typing_sensitive_actions = {
            "next_page", "prev_page", "open_full_media", "select_all_visible", "deselect_all"
        }
        if is_typing and action in typing_sensitive_actions:
            return

        action_map = {
            "focus_search": lambda: self.search_input.setFocus(),
            "next_page": self._hotkey_next,
            "prev_page": self._hotkey_prev,
            "random_post": self.random_post,
            "open_full_media": self.open_selected_full,
            "download_selected": self.download_selected,
            "favorite_selected": self.toggle_inspector_favorite,
            "select_all_visible": self.select_all_visible,
            "deselect_all": self.deselect_all,
            "go_to_home": lambda: self.tabs.setCurrentWidget(self.home_tab),
            "go_to_browser": lambda: self.tabs.setCurrentWidget(self.browser_tab), 
            "go_to_favorites": lambda: self.tabs.setCurrentWidget(self.favorites_tab),
            "go_to_ai": lambda: self.tabs.setCurrentWidget(self.ai_tab)
        }

        if action in action_map:
            try:
                action_map[action]()
            except Exception as e:
                QMessageBox.warning(self, _tr("Error"), _tr("Action failed: {error}").format(error=str(e)))

    def _hotkey_next(self):
        current_tab = self.tabs.currentWidget()
        if current_tab == self.manga_tab:
            self._select_adjacent_manga(+1)
            return
        if current_tab == self.browser_tab:
            self._select_adjacent_post(+1)
            return
        if current_tab == self.downloads_tab:
            self._select_adjacent_download(+1)
            return
        self.next_page()

    def _hotkey_prev(self):
        current_tab = self.tabs.currentWidget()
        if current_tab == self.manga_tab:
            self._select_adjacent_manga(-1)
            return
        if current_tab == self.browser_tab:
            self._select_adjacent_post(-1)
            return
        if current_tab == self.downloads_tab:
            self._select_adjacent_download(-1)
            return
        self.prev_page()

    def _select_adjacent_manga(self, delta):
        try:
            count = self.manga_items_list.count()
        except Exception:
            return
        if count <= 0:
            return
        cur = self.manga_items_list.currentRow()
        if cur < 0:
            cur = 0 if delta >= 0 else count - 1
        new_row = max(0, min(count - 1, cur + delta))
        self.manga_items_list.setCurrentRow(new_row)
        item = self.manga_items_list.item(new_row)
        if item:
            self.on_manga_item_clicked(item)

    def _select_adjacent_post(self, delta):
        posts = self.posts or []
        if not posts:
            return
        cur_id = None
        if isinstance(self.last_selected, dict):
            cur_id = self.last_selected.get("id")
        cur_idx = -1
        if cur_id is not None:
            for i, p in enumerate(posts):
                if p.get("id") == cur_id:
                    cur_idx = i
                    break
        if cur_idx < 0:
            new_idx = 0 if delta >= 0 else len(posts) - 1
        else:
            new_idx = max(0, min(len(posts) - 1, cur_idx + delta))
        post = posts[new_idx]
        widget = self.post_to_widget_map.get(post.get("id"))
        try:
            prev_id = getattr(self, "_single_selected_post_id", None)
            if prev_id and prev_id in self.post_to_widget_map and prev_id not in self.selected_for_bulk:
                self.post_to_widget_map[prev_id].set_selection(False)
            if widget and post.get("id") not in self.selected_for_bulk:
                widget.set_selection(True)
            self._single_selected_post_id = post.get("id")
        except Exception:
            pass
        self.on_thumbnail_clicked(post, widget)
        try:
            if widget:
                self.scroll.ensureWidgetVisible(widget)
        except Exception:
            pass

    def _select_adjacent_download(self, delta):
        posts = getattr(self, "downloads_posts", None) or []
        if not posts:
            return
        cur_id = None
        if isinstance(self.last_selected, dict):
            cur_id = self.last_selected.get("id")
        cur_idx = -1
        if cur_id is not None:
            for i, p in enumerate(posts):
                if p.get("id") == cur_id:
                    cur_idx = i
                    break
        if cur_idx < 0:
            new_idx = 0 if delta >= 0 else len(posts) - 1
        else:
            new_idx = max(0, min(len(posts) - 1, cur_idx + delta))
        post = posts[new_idx]
        widget = self.downloads_post_to_widget_map.get(post.get("id"))
        self.on_downloads_thumbnail_clicked(post, widget)
        try:
            if widget:
                self.downloads_scroll.ensureWidgetVisible(widget)
        except Exception:
            pass

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress:
            fw = QApplication.focusWidget()
            if isinstance(fw, QKeySequenceEdit):
                return False
            typing_widgets = (QLineEdit, QPlainTextEdit, QSpinBox, QComboBox)
            is_typing = isinstance(fw, typing_widgets)
            try:
                if fw in (
                    getattr(self, "search_input", None),
                    getattr(self, "manga_search_input", None),
                    getattr(self, "hentai_search_input", None),
                    getattr(self, "fav_search_input", None),
                    getattr(self, "downloads_search_input", None),
                ):
                    is_typing = False
            except Exception:
                pass
            try:
                if is_typing and hasattr(fw, "isReadOnly") and callable(getattr(fw, "isReadOnly")) and fw.isReadOnly():
                    is_typing = False
            except Exception:
                pass

        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if isinstance(source, QLineEdit):
                source.selectAll()
        
        if event.type() == QEvent.KeyPress and source in self.ai_input_areas:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
                try:
                    self.send_ai_message()
                except Exception as e:
                    QMessageBox.warning(self, _tr("Error"), _tr("Could not send message: {error}").format(error=str(e)))
                return True

        if event.type() == QEvent.KeyPress and hasattr(source, '_is_ai_edit') and source._is_ai_edit:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                source._save_callback()
                return True
            if event.key() == Qt.Key_Escape:
                source._cancel_callback()
                return True 

        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            try:
                fw = QApplication.focusWidget()
                if isinstance(fw, QKeySequenceEdit):
                    return super().eventFilter(source, event)
                typing_widgets = (QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QTextEdit, QTextBrowser)
                is_typing = isinstance(fw, typing_widgets)
                try:
                    if is_typing and hasattr(fw, "isReadOnly") and callable(getattr(fw, "isReadOnly")) and fw.isReadOnly():
                        is_typing = False
                except Exception:
                    pass
                if is_typing:
                    return super().eventFilter(source, event)

                seq = self.hotkey_sequences.get("open_full_media")
                if seq and not seq.isEmpty():
                    key_seq = QKeySequence(event.key() | int(event.modifiers()))
                    mod_mask = int(Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
                    mods = int(event.modifiers()) & mod_mask
                    other_key = Qt.Key_Enter if event.key() == Qt.Key_Return else Qt.Key_Return
                    alt_seq = QKeySequence(int(other_key) | mods)
                    if seq.matches(key_seq) == QKeySequence.ExactMatch or seq.matches(alt_seq) == QKeySequence.ExactMatch:
                        self.handle_hotkey_action("open_full_media", is_typing=False)
                        return True
            except Exception:
                pass

        return super().eventFilter(source, event)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def load_app_icon(self):
        if self.is_incognito_window:
            self.title_bar.title_label.setText(_tr("Snekbooru (Incognito)"))
            icon_color = self.title_bar._get_icon_color()
            self.title_bar.icon_label.setPixmap(qta.icon('fa5s.user-secret', color=icon_color).pixmap(24, 24))
            return

        icon_path = get_resource_path(os.path.join("graphics", "logo.png"))
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            self.title_bar.icon_label.setPixmap(icon.pixmap(24, 24))
        else:
            self.title_bar.icon_label.setPixmap(qta.icon('fa5s.dragon', color='white').pixmap(24, 24))

    def load_hotkeys(self):
        hotkeys = SETTINGS.get("hotkeys", {})
        for action, seq_str in hotkeys.items():
            self.hotkey_sequences[action] = QKeySequence(seq_str)
        self._rebuild_hotkey_shortcuts()

    def _rebuild_hotkey_shortcuts(self):
        for sc in self.hotkey_shortcuts.values():
            try:
                sc.setParent(None)
            except Exception:
                pass
        self.hotkey_shortcuts.clear()

        for action, seq in self.hotkey_sequences.items():
            if not seq or seq.isEmpty():
                continue

            if action == "open_full_media":
                try:
                    mod_mask = int(Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
                    key = int(seq[0]) & ~mod_mask
                    if key in (int(Qt.Key_Return), int(Qt.Key_Enter)):
                        continue
                except Exception:
                    pass

            sequences = [seq]
            try:
                mod_mask = int(Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
                key = int(seq[0]) & ~mod_mask
                mods = int(seq[0]) & mod_mask
                if key in (int(Qt.Key_Return), int(Qt.Key_Enter)):
                    other_key = int(Qt.Key_Enter) if key == int(Qt.Key_Return) else int(Qt.Key_Return)
                    sequences.append(QKeySequence(other_key | mods))
            except Exception:
                pass

            for idx, sseq in enumerate(sequences):
                sc = QShortcut(sseq, self)
                sc.setContext(Qt.WindowShortcut)
                sc.activated.connect(lambda a=action: self._handle_hotkey_shortcut(a))
                self.hotkey_shortcuts[f"{action}:{idx}"] = sc

    def _handle_hotkey_shortcut(self, action):
        fw = QApplication.focusWidget()
        if isinstance(fw, QKeySequenceEdit):
            return
        typing_widgets = (QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QTextEdit, QTextBrowser)
        is_typing = isinstance(fw, typing_widgets)
        try:
            if is_typing and hasattr(fw, "isReadOnly") and callable(getattr(fw, "isReadOnly")) and fw.isReadOnly():
                is_typing = False
        except Exception:
            pass
        self.handle_hotkey_action(action, is_typing)

    def check_media_viewer_queue(self):
        if not self.media_viewer_queue: return
        while not self.media_viewer_queue.empty():
            try:
                message_type, data = self.media_viewer_queue.get_nowait()
                if message_type == 'favorited':
                    self.toggle_favorite(data)
                elif message_type == 'viewed':
                    post, dwell = data
                    self._record_persona_view(post, dwell)
            except Exception as e:
                print(f"Error processing media viewer queue: {e}")
                break

    def _record_persona_view(self, post, dwell=0.0):
        if not post or not hasattr(self, 'persona') or self.persona is None:
            return
        if getattr(self, 'is_incognito_window', False):
            return
        try:
            category = find_post_in_favorites(post.get('id'), self.favorites)
            record_post_open(self.persona, post, context='viewer', category=category, dwell=dwell)
        except Exception as e:
            print(f"Error recording persona: {e}")
        self._schedule_persona_save()

    def _schedule_persona_save(self):
        if getattr(self, 'is_incognito_window', False):
            return
        try:
            QTimer.singleShot(2500, self._flush_persona)
        except Exception:
            pass

    def _flush_persona(self):
        if getattr(self, 'is_incognito_window', False):
            return
        try:
            if getattr(self, 'persona', None) is not None:
                save_persona(self.persona)
        except Exception as e:
            print(f"Error saving persona: {e}")

    def create_home_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        layout.addStretch(1)

        self.home_title = QLabel(_tr("Welcome to Snekbooru"))
        self.home_title.setObjectName("title")
        self.home_title.setAlignment(Qt.AlignCenter)
        self.home_title.setStyleSheet("font-size: 48px; font-weight: bold;")
        layout.addWidget(self.home_title)

        logo_label = QLabel()
        logo_path = get_resource_path(os.path.join("graphics", "logo.png"))
        if os.path.exists(logo_path):
            logo_label.setPixmap(QPixmap(logo_path).scaledToWidth(350, Qt.SmoothTransformation))
            layout.addWidget(logo_label, 0, Qt.AlignCenter)
            layout.addSpacing(20)
        
        self.home_subtitle = QLabel(_tr("Total posts available from supported sources:"))
        self.home_subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.home_subtitle)

        self.total_posts_label = QLabel(_tr("Loading..."))
        self.total_posts_label.setObjectName("total_posts_label")
        self.total_posts_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.total_posts_label)

        self.disclaimer_label = QLabel(_tr("(Note: Gelbooru & Danbooru totals are only accurate with an API key. Other counts are scraped.)"))
        self.disclaimer_label.setObjectName("disclaimer_label")
        self.disclaimer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.disclaimer_label)
        
        self.home_refresh_btn = QPushButton(qta.icon('fa5s.sync-alt'), _tr(" Refresh Stats"))
        self.home_refresh_btn.clicked.connect(self.fetch_site_stats)
        self.home_refresh_btn.setMaximumWidth(200)
        layout.addWidget(self.home_refresh_btn, 0, Qt.AlignCenter)
        
        layout.addStretch(1)

        self.credits_group = QGroupBox(_tr("Credits"))
        self.credits_group.setAlignment(Qt.AlignCenter)
        credits_layout = QVBoxLayout(self.credits_group)
        
        creator_label = QLabel(_tr("<b>Creator & Developer:</b> atroubledsnake"))
        developer_label = QLabel(_tr("<b>Contributors:</b>"))
        testers_label = QLabel(_tr("69st, nikolailol, and _shidouuu (all on Discord)"))
        thanks_label = QLabel(_tr("<i>...and a big thanks to all the users there!</i>"))
        
        for label in [creator_label, developer_label, testers_label, thanks_label]:
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setAlignment(Qt.AlignCenter)
            credits_layout.addWidget(label)

        discord_btn = QPushButton(qta.icon('fa5b.discord', color='#7289DA'), _tr(" Join our Discord server for updates!"))
        discord_btn.clicked.connect(lambda: webbrowser.open("https://discord.gg/BqNxn7ftqn"))
        credits_layout.addSpacing(10)
        credits_layout.addWidget(discord_btn, 0, Qt.AlignCenter)

        layout.addWidget(self.credits_group)
        layout.addStretch(2)
        return widget

    def create_manga_tab(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_pane.setMaximumWidth(320)

        search_group = QGroupBox(_tr("Manga Search"))
        search_layout = QVBoxLayout(search_group)
        self.manga_search_input = QLineEdit()
        self.manga_search_input.setPlaceholderText(_tr("manga or doujinshi title..."))
        self.manga_search_input.returnPressed.connect(self.apply_manga_filter)
        search_buttons = QHBoxLayout()
        self.manga_search_btn = QPushButton(qta.icon('fa5s.search'), _tr(" Search"))
        self.manga_search_btn.clicked.connect(self.apply_manga_filter)
        self.manga_clear_search_btn = QPushButton(qta.icon('fa5s.times'), _tr(" Clear"))
        self.manga_clear_search_btn.clicked.connect(self.clear_manga_search)
        search_buttons.addWidget(self.manga_search_btn)
        search_buttons.addWidget(self.manga_clear_search_btn)
        search_layout.addWidget(self.manga_search_input)
        search_layout.addLayout(search_buttons)
        left_layout.addWidget(search_group)

        source_group = QGroupBox(_tr("Sources"))
        source_layout = QVBoxLayout(source_group)
        self.manga_source_list = QListWidget()
        self.manga_source_list.itemClicked.connect(self.on_manga_source_selected)
        source_layout.addWidget(self.manga_source_list)
        left_layout.addWidget(source_group)

        controls_group = QGroupBox(_tr("Controls"))
        controls_layout = QVBoxLayout(controls_group)
        self.manga_refresh_btn = QPushButton(qta.icon('fa5s.sync-alt'), _tr(" Refresh"))
        self.manga_refresh_btn.setToolTip(_tr("Refresh the list for the selected source, or all sources if 'All' is selected."))
        self.manga_refresh_btn.clicked.connect(self.on_manga_refresh_clicked)
        controls_layout.addWidget(self.manga_refresh_btn)
        left_layout.addWidget(controls_group)

        status_group = QGroupBox(_tr("Status"))
        status_layout = QVBoxLayout(status_group)
        self.manga_progress = QProgressBar()
        self.manga_progress.setTextVisible(True)
        self.manga_progress.setRange(0, 100)
        self.manga_progress.setValue(0)
        self.manga_status_label = QLabel(_tr("Ready"))
        status_layout.addWidget(self.manga_progress)
        status_layout.addWidget(self.manga_status_label)
        left_layout.addWidget(status_group)

        left_layout.addStretch()
        layout.addWidget(left_pane)

        right_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(right_splitter)

        manga_list_pane = QWidget()
        manga_list_layout = QVBoxLayout(manga_list_pane)
        self.manga_results_label = QLabel(_tr("Ready"))
        self.manga_items_list = QListWidget()
        self.manga_items_list.setSpacing(6)
        self.manga_items_list.setUniformItemSizes(False)
        self.manga_items_list.itemClicked.connect(self.on_manga_item_clicked)
        manga_list_layout.addWidget(self.manga_results_label)
        manga_list_layout.addWidget(self.manga_items_list)
        right_splitter.addWidget(manga_list_pane)

        details_pane = QWidget()
        details_layout = QVBoxLayout(details_pane)
        inspector_group = QGroupBox(_tr("Manga Inspector"))
        inspector_layout = QVBoxLayout(inspector_group)
        self.manga_info = QPlainTextEdit()
        self.manga_info.setReadOnly(True)
        inspector_layout.addWidget(self.manga_info)
        inspector_buttons = QHBoxLayout()
        self.manga_open_btn = QPushButton(qta.icon('fa5s.book-open'), _tr(" Open"))
        self.manga_open_btn.clicked.connect(self.open_selected_manga_in_viewer)
        self.manga_open_browser_btn = QPushButton(qta.icon('fa5s.external-link-alt'), _tr(" Open on Website"))
        self.manga_open_browser_btn.clicked.connect(self.open_selected_manga_in_browser)
        self.manga_import_btn = QPushButton(qta.icon('fa5s.file-import'), _tr(" Import"))
        self.manga_import_btn.clicked.connect(self.import_manga_from_images)
        self.manga_export_btn = QPushButton(qta.icon('fa5s.file-export'), _tr(" Export"))
        self.manga_export_btn.clicked.connect(self.open_book_export_dialog)
        self.manga_download_pages_btn = QPushButton(qta.icon('fa5s.download'), _tr(" Download Pages"))
        self.manga_download_pages_btn.clicked.connect(lambda: self.download_selected_manga_pages(open_folder=True))
        self.manga_download_export_btn = QPushButton(qta.icon('fa5s.download'), _tr(" Download & Export"))
        self.manga_download_export_btn.clicked.connect(self.download_selected_manga_and_export)
        inspector_buttons.addWidget(self.manga_open_btn)
        inspector_buttons.addWidget(self.manga_open_browser_btn)
        inspector_buttons.addWidget(self.manga_import_btn)
        inspector_buttons.addWidget(self.manga_export_btn)
        inspector_buttons.addWidget(self.manga_download_pages_btn)
        inspector_buttons.addWidget(self.manga_download_export_btn)
        inspector_layout.addLayout(inspector_buttons)
        details_layout.addWidget(inspector_group)

        _ensure_webengine()
        self.manga_profile = QWebEngineProfile()
        self.manga_profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        try:
            web_cache_dir = snekbooru_temp_dir("webengine", "manga")
            self.manga_profile.setCachePath(web_cache_dir)
            self.manga_profile.setPersistentStoragePath(web_cache_dir)
        except Exception:
            pass
        self.manga_ad_blocker = AdBlocker()
        self.manga_profile.setUrlRequestInterceptor(self.manga_ad_blocker)
        polyfill = QWebEngineScript()
        polyfill.setName("object-hasOwn-polyfill")
        polyfill.setInjectionPoint(QWebEngineScript.DocumentCreation)
        polyfill.setRunsOnSubFrames(True)
        polyfill.setSourceCode("if (!Object.hasOwn) { Object.hasOwn = function(obj, prop) { return Object.prototype.hasOwnProperty.call(obj, prop); }; }")
        self.manga_profile.scripts().insert(polyfill)
        self.manga_web_view = QWebEngineView()
        self.manga_web_view.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        page = MangaWebPage(self.manga_profile, self.manga_web_view)
        self.manga_web_view.setPage(page)
        details_layout.addWidget(self.manga_web_view)
        right_splitter.addWidget(details_pane)
        right_splitter.setSizes([450, 750])

        self.manga_sources = []
        self.manga_selected_entry = None
        self.update_manga_inspector(None)

        if not self.enma:
            self.manga_status_label.setText(_tr("Enma missing: using MangaDex fallback mode."))
        QTimer.singleShot(100, self.populate_manga_sources)

        return widget

    def create_hentai_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls_group = QGroupBox(_tr("HentaiHaven"))
        controls_layout = QVBoxLayout(controls_group)
        row1 = QHBoxLayout()
        self.hentai_search_input = QLineEdit()
        self.hentai_search_input.setPlaceholderText(_tr("Search series by title or tag…"))
        self.hentai_search_input.returnPressed.connect(self.search_hentai)
        self.hentai_search_btn = QPushButton(qta.icon('fa5s.search'), _tr(" Search"))
        self.hentai_search_btn.clicked.connect(self.search_hentai)
        row1.addWidget(self.hentai_search_input, 1)
        row1.addWidget(self.hentai_search_btn)
        controls_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.hentai_trending_btn = QPushButton(qta.icon('fa5s.fire'), _tr(" Trending"))
        self.hentai_trending_btn.clicked.connect(self.trending_hentai)
        self.hentai_popular_btn = QPushButton(qta.icon('fa5s.chart-line'), _tr(" Popular"))
        self.hentai_popular_btn.clicked.connect(self.popular_hentai)
        self.hentai_new_btn = QPushButton(qta.icon('fa5s.clock'), _tr(" New"))
        self.hentai_new_btn.clicked.connect(self.newest_hentai)
        self.hentai_random_btn = QPushButton(qta.icon('fa5s.dice'), _tr(" Random"))
        self.hentai_random_btn.clicked.connect(self.random_hentai)
        self.hentai_load_more_btn = QPushButton(qta.icon('fa5s.plus-circle'), _tr(" Load More"))
        self.hentai_load_more_btn.clicked.connect(self.load_more_hentai)
        self.hentai_load_more_btn.setEnabled(False)
        row2.addWidget(self.hentai_trending_btn)
        row2.addWidget(self.hentai_popular_btn)
        row2.addWidget(self.hentai_new_btn)
        row2.addWidget(self.hentai_random_btn)
        row2.addWidget(self.hentai_load_more_btn)
        row2.addSpacing(12)
        row2.addWidget(QLabel(_tr("Genre:")))
        self.hentai_genre_combo = QComboBox()
        self.hentai_genre_combo.setMinimumWidth(180)
        self.hentai_genre_combo.currentIndexChanged.connect(self.on_hentai_genre_changed)
        row2.addWidget(self.hentai_genre_combo)
        row2.addStretch(1)
        controls_layout.addLayout(row2)
        layout.addWidget(controls_group)

        self.hentai_scroll = QScrollArea(); self.hentai_scroll.setWidgetResizable(True)
        self.hentai_grid_host = QWidget()
        self.hentai_grid = QGridLayout(self.hentai_grid_host)
        self.hentai_grid.setSpacing(10); self.hentai_grid.setContentsMargins(0, 0, 0, 0)
        self.hentai_grid.setAlignment(Qt.AlignTop)
        self.hentai_scroll.setWidget(self.hentai_grid_host)
        layout.addWidget(self.hentai_scroll)

        status_layout = QHBoxLayout()
        self.hentai_status_label = QLabel(_tr("Ready"))
        status_layout.addStretch()
        status_layout.addWidget(self.hentai_status_label)
        layout.addLayout(status_layout)

        self.hentai_post_to_widget_map = {}
        self.hentai_current_results = []
        self.hentai_current_page = 0
        self.hentai_current_query = ""
        self.hentai_current_mode = "new"
        self.hentai_page_size = 24

        QTimer.singleShot(0, self.load_hhaven_genres)
        QTimer.singleShot(0, self.newest_hentai)
        return widget

    def _start_hentai_fetch(self, append=False):
        mode = self.hentai_current_mode
        query = self.hentai_current_query if mode == "search" else ""
        genre_id = 0
        if mode == "genre" and getattr(self, "hentai_genre_combo", None):
            idx = self.hentai_genre_combo.currentIndex()
            genre_id = int(self.hentai_genre_combo.itemData(idx) or 0)
        self.hentai_status_label.setText(_tr("Loading…"))
        self.hentai_load_more_btn.setEnabled(False)
        worker = ApiWorker(_do_hhaven_fetch, mode, self.hentai_current_page,
                           self.hentai_page_size, query, genre_id)
        worker.signals.finished.connect(self.on_hentai_more_loaded if append else self.on_hentai_search_finished)
        self.threadpool.start(worker)

    def search_hentai(self):
        query = self.hentai_search_input.text().strip()
        if not query: return
        self.hentai_current_query = query
        self.hentai_current_mode = "search"
        self.hentai_current_page = 0
        self._start_hentai_fetch(append=False)

    def random_hentai(self):
        self.hentai_current_mode = "random"
        self.hentai_current_page = 0
        self.hentai_status_label.setText(_tr("Fetching random…"))
        self.hentai_load_more_btn.setEnabled(False)
        worker = ApiWorker(_do_hhaven_fetch, "random", 0, self.hentai_page_size)
        worker.signals.finished.connect(self.on_hentai_search_finished)
        self.threadpool.start(worker)

    def trending_hentai(self):
        self.hentai_current_mode = "trending"
        self.hentai_current_page = 0
        self._start_hentai_fetch(append=False)

    def popular_hentai(self):
        self.hentai_current_mode = "popular"
        self.hentai_current_page = 0
        self._start_hentai_fetch(append=False)

    def newest_hentai(self):
        self.hentai_current_mode = "new"
        self.hentai_current_page = 0
        self._start_hentai_fetch(append=False)

    def load_more_hentai(self):
        if self.hentai_current_mode == "random":
            self.random_hentai()
            return
        self.hentai_current_page += 1
        self._start_hentai_fetch(append=True)

    def load_hhaven_genres(self):
        worker = ApiWorker(_do_hhaven_fetch, "genres", 0, 0)
        worker.signals.finished.connect(self.on_hhaven_genres_loaded)
        self.threadpool.start(worker)

    def on_hhaven_genres_loaded(self, results, err):
        combo = getattr(self, "hentai_genre_combo", None)
        if combo is None: return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(_tr("All Genres"), 0)
        for g in (results or []):
            combo.addItem(f"{g.get('name') or g.get('slug') or g.get('id')}  ({g.get('count') or 0})", int(g.get('id') or 0))
        combo.blockSignals(False)
        combo.setCurrentIndex(0)

    def on_hentai_genre_changed(self):
        combo = getattr(self, "hentai_genre_combo", None)
        if combo is None or len(combo) == 0:
            return
        idx = combo.currentIndex()
        gid = int(combo.itemData(idx) or 0)
        if gid == 0:
            self.newest_hentai()
        else:
            self.hentai_current_mode = "genre"
            self.hentai_current_page = 0
            self.hentai_current_query = ""
            self._start_hentai_fetch(append=False)

    def on_hentai_search_finished(self, results, err):
        self.clear_grid(self.hentai_grid)
        self.hentai_post_to_widget_map.clear()
        if err:
            self.hentai_status_label.setText(_tr("Error: {error}").format(error=err))
            self.hentai_load_more_btn.setEnabled(False)
            return

        posts = [p for p in (self._adapt_hhaven_post(h) for h in (results or [])) if p][:150]
        self.hentai_current_results = posts
        if not posts:
            self.hentai_status_label.setText(_tr("No results found."))
            self.hentai_load_more_btn.setEnabled(False)
        else:
            self.hentai_status_label.setText(_tr("Loaded {count} series.").format(count=len(posts)))
            self.hentai_load_more_btn.setEnabled(len(posts) >= self.hentai_page_size)
        self._populate_hentai_grid(posts)

    def on_hentai_more_loaded(self, results, err):
        if err:
            self.hentai_status_label.setText(_tr("Error: {error}").format(error=err))
            self.hentai_load_more_btn.setEnabled(True)
            return
        new_posts = [p for p in (self._adapt_hhaven_post(h) for h in (results or [])) if p]
        if not new_posts:
            self.hentai_status_label.setText(_tr("No more results."))
            self.hentai_load_more_btn.setEnabled(False)
            return
        self.hentai_current_results.extend(new_posts)
        self.hentai_current_results = self.hentai_current_results[:150]
        self.hentai_status_label.setText(_tr("Loaded {count} series.").format(count=len(self.hentai_current_results)))
        self.hentai_load_more_btn.setEnabled(len(self.hentai_current_results) < 150)
        self._populate_hentai_grid(self.hentai_current_results)

    def _populate_hentai_grid(self, posts):
        self.clear_grid(self.hentai_grid)
        self.hentai_post_to_widget_map.clear()
        posts = [p for p in (posts or []) if isinstance(p, dict)]
        if not posts:
            return
        spacing = 10
        card_w = 170
        view_w = max(200, self.hentai_scroll.viewport().width() - 2)
        cols = max(1, int((view_w + spacing) // (card_w + spacing)))
        cols = min(cols, len(posts))
        for i, post in enumerate(posts):
            row, col = divmod(i, cols)
            thumb = HentaiThumbnailWidget(post)
            thumb.clicked.connect(self.on_hentai_thumbnail_clicked)
            self.hentai_grid.addWidget(thumb, row, col, Qt.AlignLeft | Qt.AlignTop)
            post_id = post.get("id") or f"hh_{i}"
            post["id"] = post_id
            self.hentai_post_to_widget_map[post_id] = thumb
            preview = post.get("preview_url")
            if preview:
                worker = ImageWorker(preview, post)
                worker.signals.finished.connect(self.on_thumbnail_loaded)
                self.threadpool.start(worker)
            else:
                thumb.set_text("No image")

    def on_hentai_thumbnail_clicked(self, post: dict, widget: HentaiThumbnailWidget):
        if not getattr(self, 'is_incognito_window', False) and hasattr(self, 'persona') and self.persona is not None:
            try:
                record_hentai_open(self.persona, post)
                self._schedule_persona_save()
            except Exception as e:
                print(f"Error recording hentai open: {e}")
        dialog = HentaiSeriesDialog(post, self)
        self.open_dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)
        dialog.show()

    def _adapt_hhaven_post(self, item):
        if not isinstance(item, dict):
            return None
        slug = item.get("slug", "")
        title = item.get("title")
        if isinstance(title, dict):
            title = title.get("rendered") or title.get("raw") or ""
        title = re.sub(r"<[^>]+>", "", str(title or "")).strip()
        thumb = item.get("preview_url") or item.get("thumbnail_url") or item.get("cover_url") or ""
        if not thumb:
            meta = item.get("meta") or {}
            thumb = meta.get("vraven_remote_thumbnail") or ""
        thumb = _hhaven_thumb(thumb)
        genre_ids = item.get("genre_ids") or item.get("wp-manga-genre") or []
        genre_names = []
        for gid in genre_ids or []:
            try:
                name = _HH_GENRE_NAMES.get(int(gid), "")
            except Exception:
                name = ""
            if name:
                genre_names.append(name)
        views = int(item.get("views") or item.get("score") or 0)
        return {
            "id": f"hh_{item.get('id', '') or slug}",
            "preview_url": thumb,
            "file_url": None,
            "rating": "explicit",
            "score": views,
            "tags": ", ".join(genre_names),
            "source_post_url": f"https://hentaihaven.xxx/watch/{slug}/" if slug else "",
            "hentai_slug": slug,
            "hentai_title": title,
            "hentai_views": views,
            "hentai_genres": genre_names,
            "hhaven_date": item.get("date") or item.get("created_at") or "",
            "hhaven_data": item,
            "file_ext": "png",
        }

    def fetch_site_stats(self):
        self.total_posts_label.setText(f"<i>{_tr('Loading...')}</i>")
        worker = ApiWorker(self._get_all_site_counts)
        worker.signals.finished.connect(self.on_site_stats_loaded)
        self.threadpool.start(worker)

    def _get_all_site_counts(self):
        total = 0
        has_error = False
        fetch_all = SETTINGS.get("fetch_all_site_stats", True)
        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])

        scrape_configs = {
            "Rule34": ("https://rule34.xxx/", 'serving_text'),
            "Hypnohub": ("https://hypnohub.net/", 'serving_text'),
            "Konachan": ("https://konachan.com/", 'posts_link'),
            "Yandere": ("https://yande.re/post", 'posts_link'),
        }

        for site, (url, method) in scrape_configs.items():
            if fetch_all or site in enabled_sources:
                try:
                    count = scrape_post_count(url, method)
                    if isinstance(count, int): total += count
                    else: has_error = True
                except Exception: has_error = True; print(f"Failed to get {site} count.")
                time.sleep(0.5)

        try:
            if fetch_all or "Gelbooru" in enabled_sources:
                _, count = gelbooru_posts('', 0, 0)
                if isinstance(count, int): total += count
        except Exception: has_error = True; print("Failed to get Gelbooru count.")

        try:
            if fetch_all or "Danbooru" in enabled_sources:
                from snekbooru.common.constants import DANBOORU_COUNTS_POSTS
                r = requests.get(f"{DANBOORU_COUNTS_POSTS}?tags=", headers={'User-Agent': USER_AGENT}, timeout=10)
                r.raise_for_status()
                count = r.json().get("counts", {}).get("posts")
                if isinstance(count, int): total += count
        except Exception as e: has_error = True; print(f"Failed to get Danbooru count via API: {e}")
        
        if total == 0 and not has_error:
            return "Idk bru", None
        return "Error" if total == 0 and has_error else total, None

    def on_site_stats_loaded(self, data, err):
        if err or data is None:
            self.total_posts_label.setText(_tr("Error"))
            return
        
        total_count, _ = data
        if isinstance(total_count, int):
            png_display = number_to_png_display(total_count)
            self.total_posts_label.setText(png_display)
        elif total_count == 0:
            self.total_posts_label.setText(_tr("Idk bru"))
        else:
            self.total_posts_label.setText(str(total_count))

    def create_browser_tab(self):
        browser_widget = QWidget()
        browser_widget.setObjectName("browser_tab_content")
        outer_layout = QVBoxLayout(browser_widget)

        self.controls_group = QGroupBox(_tr("Search Controls"))
        controls_layout = QVBoxLayout(self.controls_group)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText(_tr("tags (e.g. rating:safe cat_girl)"))
        
        self.search_completer_model = QStringListModel(self.search_history)
        self.search_completer = QCompleter(self.search_completer_model, self)
        self.search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.search_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.search_input.setCompleter(self.search_completer)
        self.suggestion_timer = QTimer(self)
        self.suggestion_timer.setSingleShot(True)
        self.suggestion_timer.setInterval(400)
        self.suggestion_timer.timeout.connect(self.fetch_suggestions)
        self.search_input.textChanged.connect(self.suggestion_timer.start)
        self.search_input.returnPressed.connect(self.search)        
        self.include_pref = QCheckBox(_tr("Include preferred tags")); self.include_pref.setChecked(True)
        search_row.addWidget(QLabel(_tr("Search:")), 0)
        search_row.addWidget(self.search_input, 4)
        search_row.addWidget(self.limit, 1)
        search_row.addWidget(self.include_pref, 2)
        controls_layout.addLayout(search_row)

        button_row = QHBoxLayout()
        self.suggest_btn = QPushButton(qta.icon('fa5s.lightbulb'), _tr(" Suggest Tags"))
        self.search_btn = QPushButton(qta.icon('fa5s.search'), _tr(" Search"))
        self.rand_btn = QPushButton(qta.icon('fa5s.random'), _tr(" Random Post"))
        self.rand_tag_btn = QPushButton(qta.icon('fa5s.tags'), _tr(" Random Tag"))
        for w in [self.suggest_btn, self.search_btn, self.rand_btn, self.rand_tag_btn]:
            w.setMinimumHeight(34)
        button_row.addWidget(self.suggest_btn)
        button_row.addWidget(self.search_btn)
        button_row.addWidget(self.rand_btn)
        button_row.addWidget(self.rand_tag_btn)
        button_row.addStretch(1)
        controls_layout.addLayout(button_row)

        outer_layout.addWidget(self.controls_group)

        splitter = QSplitter()
        outer_layout.addWidget(splitter, 1)

        self.browser_content_tabs = QTabWidget()
        self.browser_content_tabs.currentChanged.connect(self.on_browser_sub_tab_changed)
        splitter.addWidget(self.browser_content_tabs)

        newest_tab_content = self._create_newest_content_area()
        reco_tab_content = self._create_recommendations_content_area()
        reverse_search_tab_content = self._create_reverse_search_content_area()

        self.browser_content_tabs.addTab(newest_tab_content, qta.icon('fa5s.clock'), _tr("Newest"))
        self.browser_content_tabs.addTab(reco_tab_content, qta.icon('fa5s.magic'), _tr("Recommendations"))
        self.browser_content_tabs.addTab(reverse_search_tab_content, qta.icon('fa5s.search'), _tr("Reverse Search"))

        self.insp_group = QGroupBox(_tr("Post Inspector"))
        insp_layout = QVBoxLayout(self.insp_group)
        self.info = QPlainTextEdit(); self.info.setReadOnly(True);
        self.info.setObjectName("post_inspector_info")
        insp_layout.addWidget(self.info)

        inspector_button_row = QHBoxLayout()
        self.open_full = QPushButton(qta.icon('fa5s.expand-arrows-alt'), _tr(" Open Full Media"))
        self.quick_dl = QPushButton(qta.icon('fa5s.download'), _tr(" Quick Download"))
        self.inspector_fav_btn = QPushButton(qta.icon('fa5s.star'), _tr(" Favorite"))
        self.reverse_search_btn = QPushButton(qta.icon('fa5s.search'), _tr("Reverse Search"))
        inspector_button_row.addWidget(self.open_full)
        inspector_button_row.addWidget(self.quick_dl)
        inspector_button_row.addWidget(self.inspector_fav_btn)
        inspector_button_row.addWidget(self.reverse_search_btn)
        insp_layout.addLayout(inspector_button_row)

        self.bulk_group = QGroupBox(_tr("Bulk Download"))
        bulk_layout = QHBoxLayout(self.bulk_group)
        self.bulk_dl_btn = QPushButton(qta.icon('fa5s.cloud-download-alt'), _tr(" Download Selected"))
        self.select_all_btn = QPushButton(qta.icon('fa5s.check-square'), _tr(" Select All Visible"))
        self.deselect_all_btn = QPushButton(qta.icon('fa5s.square'), _tr(" Deselect All"))
        self.bulk_status_label = QLabel(_tr("0 selected. Ctrl/Shift+Click thumbnails to select."))
        bulk_layout.addWidget(self.bulk_dl_btn); bulk_layout.addWidget(self.select_all_btn)
        bulk_layout.addWidget(self.deselect_all_btn); bulk_layout.addStretch()
        bulk_layout.addWidget(self.bulk_status_label)
        insp_layout.addWidget(self.bulk_group)

        splitter.addWidget(self.insp_group)
        splitter.setSizes([1000, 300])

        self.search_btn.clicked.connect(self.search)
        self.rand_btn.clicked.connect(self.random_post)
        self.rand_tag_btn.clicked.connect(self.random_tag)
        self.open_full.clicked.connect(self.open_selected_full)
        self.quick_dl.clicked.connect(self.download_selected)        
        self.inspector_fav_btn.clicked.connect(self.toggle_inspector_favorite)
        self.reverse_search_btn.clicked.connect(self.reverse_search_selected)
        self.suggest_btn.clicked.connect(self.suggest_tags_dialog)
        self.bulk_dl_btn.clicked.connect(self.start_bulk_download)
        self.select_all_btn.clicked.connect(self.select_all_visible)
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        self.search_input.returnPressed.connect(self.start_new_search)

        return browser_widget

    def _create_newest_content_area(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget(); self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(10); self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, 1)

        pager_layout = QHBoxLayout()
        self.prev_btn = QPushButton(qta.icon('fa5s.arrow-left'), _tr(" Previous"))

        self.page_input = QLineEdit()
        from PyQt5.QtGui import QIntValidator
        self.page_input.setValidator(QIntValidator(1, 999999))
        self.page_input.setFixedWidth(80)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.setToolTip(_tr("Go to page... (Press Enter)"))
        self.page_input.returnPressed.connect(self.go_to_page)

        self.next_btn = QPushButton(qta.icon('fa5s.arrow-right'), _tr("Next "))
        self.next_btn.setLayoutDirection(Qt.RightToLeft)
        self.status = QLabel(_tr("Ready"))
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(12)
        self.page_count_label = QLabel("")
        self.page_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        pager_layout.addWidget(self.prev_btn)
        pager_layout.addWidget(self.page_input)
        pager_layout.addWidget(self.next_btn)
        pager_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        pager_layout.addWidget(self.status)
        pager_layout.addWidget(self.progress)
        pager_layout.addSpacing(10)
        pager_layout.addWidget(self.page_count_label)
        layout.addLayout(pager_layout)

        self.prev_btn.clicked.connect(self.prev_page) 
        self.next_btn.clicked.connect(self.next_page)

        return widget

    def _create_recommendations_content_area(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)

        controls_row = QHBoxLayout()
        self.reco_button = QPushButton(qta.icon('fa5s.magic'), _tr(" Get Recommendations"))
        self.reco_button.clicked.connect(self.fetch_recommendations)
        self.reco_status_label = QLabel(_tr("Click the button to get recommendations based on your favorites."))
        controls_row.addWidget(self.reco_button)
        controls_row.addWidget(self.reco_status_label, 1)
        layout.addLayout(controls_row)

        self.reco_scroll = QScrollArea(); self.reco_scroll.setWidgetResizable(True)
        self.reco_grid_host = QWidget()
        self.reco_grid = QGridLayout(self.reco_grid_host); self.reco_grid.setContentsMargins(0, 0, 0, 0)
        self.reco_grid.setSpacing(10); self.reco_grid.setAlignment(Qt.AlignTop)
        self.reco_scroll.setWidget(self.reco_grid_host); layout.addWidget(self.reco_scroll, 1)
        return widget

    def _create_reverse_search_content_area(self):
        widget = QWidget()
        self.reverse_search_image_data = None

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignTop)

        self.file_search_group = QGroupBox(_tr("Search by File or Paste"))
        file_search_layout = QVBoxLayout(self.file_search_group)

        preview_container = QWidget()
        preview_layout = QGridLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.reverse_search_preview_label = ImageDropLabel(_tr("Drop image here, paste, or click Upload"))
        self.reverse_search_preview_label.setMinimumSize(300, 200)
        self.reverse_search_preview_label.image_changed.connect(self.on_reverse_search_image_changed)

        self.reverse_search_clear_btn = QPushButton(qta.icon('fa5s.times-circle', color='white'), "")
        self.reverse_search_clear_btn.setToolTip(_tr("Clear Image"))
        self.reverse_search_clear_btn.setFixedSize(24, 24)
        self.reverse_search_clear_btn.setStyleSheet("QPushButton { border: none; border-radius: 12px; background-color: rgba(0,0,0,150); } QPushButton:hover { background-color: rgba(200,0,0,200); }")
        self.reverse_search_clear_btn.setCursor(Qt.PointingHandCursor)
        self.reverse_search_clear_btn.clicked.connect(self.clear_reverse_search_image)
        self.reverse_search_clear_btn.hide()

        preview_layout.addWidget(self.reverse_search_preview_label, 0, 0)
        preview_layout.addWidget(self.reverse_search_clear_btn, 0, 0, Qt.AlignTop | Qt.AlignRight)

        file_search_layout.addWidget(preview_container)

        upload_btn = QPushButton(qta.icon('fa5s.upload'), _tr("Upload Image..."))
        upload_btn.clicked.connect(self.upload_for_reverse_search)
        file_search_layout.addWidget(upload_btn, 0, Qt.AlignCenter)
        
        layout.addWidget(self.file_search_group)

        url_search_group = QGroupBox(_tr("Reverse Image Search by URL"))
        from PyQt5.QtWidgets import QFormLayout
        url_form_layout = QFormLayout(url_search_group)
        self.reverse_search_url_input = QLineEdit()
        self.reverse_search_url_input.setPlaceholderText(_tr("Paste an image URL here"))
        url_form_layout.addRow(_tr("Image URL:"), self.reverse_search_url_input)
        layout.addWidget(url_search_group)

        shared_controls_group = QGroupBox(_tr("Search Options"))
        shared_form_layout = QFormLayout(shared_controls_group)
        from PyQt5.QtWidgets import QComboBox
        self.reverse_search_engine_combo = QComboBox()
        self.reverse_search_engine_combo.addItems(["SauceNAO", "IQDB", "Google Lens"])
        shared_form_layout.addRow(_tr("Search Engine:"), self.reverse_search_engine_combo)
        
        self.perform_reverse_search_btn = QPushButton(qta.icon('fa5s.search'), _tr(" Search"))
        self.perform_reverse_search_btn.clicked.connect(self._perform_reverse_search)
        shared_form_layout.addRow(self.perform_reverse_search_btn)
        
        layout.addWidget(shared_controls_group)
        layout.addStretch()

        return widget

    def on_reverse_search_image_changed(self, pixmap):
        from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        self.reverse_search_image_data = ba

        self.reverse_search_preview_label.setPixmap(pixmap.scaled(
            self.reverse_search_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        self.reverse_search_url_input.clear()
        self.reverse_search_clear_btn.show()

    def clear_reverse_search_image(self):
        self.reverse_search_image_data = None
        self.reverse_search_preview_label.setPixmap(QPixmap())
        self.reverse_search_preview_label.setText(_tr("Drop image here, paste, or click Upload"))
        self.reverse_search_clear_btn.hide()

    def upload_for_reverse_search(self):
        from PyQt5.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getOpenFileName(self, _tr("Upload Image for Reverse Search"), "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if filepath:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                self.on_reverse_search_image_changed(pixmap)

    def _perform_reverse_search(self):
        engine = self.reverse_search_engine_combo.currentText()
        
        if self.reverse_search_image_data:
            if engine == "IQDB":
                self._perform_iqdb_upload()
            else:
                QMessageBox.information(self, _tr("Engine Not Supported"), _tr("Direct file upload is currently only supported for IQDB. For other engines, please use the URL option."))
            return

        image_url = self.reverse_search_url_input.text().strip()
        if not image_url:
            QMessageBox.warning(self, _tr("Reverse Image Search"), _tr("Please upload/paste an image or enter an image URL."))
            return
        
        import urllib.parse
        encoded_url = urllib.parse.quote_plus(image_url)
        if engine == "SauceNAO": search_url = f"https://saucenao.com/search.php?url={encoded_url}"
        elif engine == "IQDB": search_url = f"https://iqdb.org/?url={encoded_url}"
        elif engine == "Google Lens": search_url = f"https://lens.google.com/uploadbyurl?url={encoded_url}"
        else: return
        webbrowser.open(search_url)

    def _perform_iqdb_upload(self):
        self.status.setText(_tr("Uploading to IQDB..."))
        worker = ApiWorker(self._do_iqdb_upload, self.reverse_search_image_data)
        worker.signals.finished.connect(self._on_iqdb_upload_finished)
        self.threadpool.start(worker)

    def _do_iqdb_upload(self, image_data):
        import requests, urllib.parse
        files = {'file': ('image.png', image_data.data(), 'image/png')}
        try:
            r = requests.post('https://iqdb.org/', files=files, allow_redirects=False, timeout=30)
            r.raise_for_status()
            if r.status_code in [301, 302, 303, 307, 308] and 'Location' in r.headers:
                final_url = urllib.parse.urljoin(r.url, r.headers['Location'])
                return final_url, None
            else:
                return None, f"IQDB did not return a valid redirect. Status: {r.status_code}"
        except Exception as e:
            return None, str(e)

    def _on_iqdb_upload_finished(self, data, err):
        self.status.setText(_tr("Ready"))
        if err:
            QMessageBox.critical(self, _tr("IQDB Upload Failed"), err or _tr("An unknown error occurred."))
            return

        if not data:
            QMessageBox.critical(self, _tr("IQDB Upload Failed"), _tr("An unknown error occurred."))
            return

        url, function_error = data
        if function_error:
            QMessageBox.critical(self, _tr("IQDB Upload Failed"), function_error)
            return

        if url:
            webbrowser.open(url)
        else:
            QMessageBox.critical(self, _tr("IQDB Upload Failed"), _tr("An unknown error occurred."))

    def create_favorites_tab(self):
        favorites_widget = QWidget()
        outer_layout = QHBoxLayout(favorites_widget)

        category_pane = QWidget()
        category_layout = QVBoxLayout(category_pane)
        category_pane.setMaximumWidth(300)

        self.fav_category_group = QGroupBox(_tr("Categories"))
        fav_category_group_layout = QVBoxLayout(self.fav_category_group)

        self.fav_category_list = QListWidget()
        self.fav_category_list.currentItemChanged.connect(self.on_fav_category_changed)
        fav_category_group_layout.addWidget(self.fav_category_list)

        cat_button_row1 = QHBoxLayout()
        self.new_cat_btn = QPushButton(qta.icon('fa5s.plus'), _tr(" New"))
        self.rename_cat_btn = QPushButton(qta.icon('fa5s.edit'), _tr(" Rename"))
        self.delete_cat_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Delete"))
        cat_button_row1.addWidget(self.new_cat_btn)
        cat_button_row1.addWidget(self.rename_cat_btn)
        cat_button_row1.addWidget(self.delete_cat_btn)
        fav_category_group_layout.addLayout(cat_button_row1)

        category_layout.addWidget(self.fav_category_group)
        outer_layout.addWidget(category_pane)

        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        self.favorites_count_label = QLabel(_tr("0 favorites in this category"))
        top_row.addWidget(self.favorites_count_label)
        top_row.addStretch()
        self.fav_refresh_btn = QPushButton(qta.icon('fa5s.sync-alt'), _tr(" Refresh Grid"))
        self.fav_refresh_btn.clicked.connect(self.refresh_favorites_grid)
        top_row.addWidget(self.fav_refresh_btn)
        right_layout.addLayout(top_row)

        fav_search_row = QHBoxLayout()
        self.fav_search_input = QLineEdit()
        self.fav_search_input.setPlaceholderText(_tr("Filter by tags..."))
        self.fav_search_input.textChanged.connect(self.refresh_favorites_grid)
        self.fav_search_filter_label = QLabel(_tr("Filter:"))
        fav_search_row.addWidget(self.fav_search_filter_label)
        fav_search_row.addWidget(self.fav_search_input)
        right_layout.addLayout(fav_search_row)

        splitter = QSplitter(Qt.Horizontal)
        right_layout.addWidget(splitter)

        self.fav_scroll = QScrollArea(); self.fav_scroll.setWidgetResizable(True)
        self.fav_grid_host = QWidget()
        self.fav_grid = QGridLayout(self.fav_grid_host); self.fav_grid.setContentsMargins(0, 0, 0, 0)
        self.fav_grid.setSpacing(10); self.fav_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.fav_scroll.setWidget(self.fav_grid_host)
        splitter.addWidget(self.fav_scroll)

        self.fav_insp_group = QGroupBox(_tr("Post Inspector"))
        fav_insp_layout = QVBoxLayout(self.fav_insp_group)
        self.fav_info = QPlainTextEdit(); self.fav_info.setReadOnly(True)
        self.fav_info.setObjectName("favorites_inspector_info")
        fav_insp_layout.addWidget(self.fav_info)
        splitter.addWidget(self.fav_insp_group)

        splitter.setSizes([1000, 300])
        outer_layout.addWidget(right_pane)

        self.new_cat_btn.clicked.connect(self.add_favorite_category)
        self.rename_cat_btn.clicked.connect(self.rename_favorite_category)
        self.delete_cat_btn.clicked.connect(self.delete_favorite_category)

        self.populate_favorite_categories()

        return favorites_widget

    def create_downloads_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        top_row = QHBoxLayout()
        self.downloads_count_label = QLabel(_tr("0 downloaded files"))
        top_row.addWidget(self.downloads_count_label)
        top_row.addStretch()
        open_folder_btn = QPushButton(qta.icon('fa5s.folder-open'), _tr(" Open Folder"))
        open_folder_btn.clicked.connect(self.open_downloads_folder)
        top_row.addWidget(open_folder_btn)
        import_btn = QPushButton(qta.icon('fa5s.file-import'), _tr(" Import Local Folder"))
        import_btn.clicked.connect(self.import_local_folder)
        top_row.addWidget(import_btn)
        refresh_btn = QPushButton(qta.icon('fa5s.sync-alt'), _tr(" Refresh Grid"))
        refresh_btn.clicked.connect(self.refresh_downloads_grid)
        top_row.addWidget(refresh_btn)
        layout.addLayout(top_row)

        search_row = QHBoxLayout()
        self.downloads_search_input = QLineEdit()
        self.downloads_search_input.setPlaceholderText(_tr("Filter by tags..."))
        self.downloads_search_input.textChanged.connect(self.refresh_downloads_grid)
        search_row.addWidget(QLabel(_tr("Filter:")))
        search_row.addWidget(self.downloads_search_input)
        self.downloads_type_filter = QComboBox()
        self.downloads_type_filter.addItems([_tr("All"), _tr("Images"), _tr("GIFs"), _tr("Videos")])
        self.downloads_type_filter.currentIndexChanged.connect(self.refresh_downloads_grid)
        search_row.addWidget(self.downloads_type_filter)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Horizontal)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        self.downloads_scroll = QScrollArea()
        self.downloads_scroll.setWidgetResizable(True)
        self.downloads_grid_host = QWidget()
        self.downloads_grid = QGridLayout(self.downloads_grid_host)
        self.downloads_grid.setContentsMargins(0, 0, 0, 0)
        self.downloads_grid.setSpacing(10)
        self.downloads_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.downloads_scroll.setWidget(self.downloads_grid_host)
        left_layout.addWidget(self.downloads_scroll)
        splitter.addWidget(left_pane)

        inspector_group = QGroupBox(_tr("Download Inspector"))
        inspector_layout = QVBoxLayout(inspector_group)
        self.downloads_preview_label = QLabel(_tr("Select a download to preview."))
        self.downloads_preview_label.setAlignment(Qt.AlignCenter)
        self.downloads_preview_label.setFixedSize(260, 260)
        inspector_layout.addWidget(self.downloads_preview_label, 0, Qt.AlignCenter)
        self.downloads_info = QPlainTextEdit()
        self.downloads_info.setReadOnly(True)
        inspector_layout.addWidget(self.downloads_info)

        inspector_buttons = QHBoxLayout()
        self.downloads_open_btn = QPushButton(qta.icon('fa5s.expand'), _tr(" Open"))
        self.downloads_open_btn.clicked.connect(self.open_selected_download_in_viewer)
        self.downloads_open_folder_btn = QPushButton(qta.icon('fa5s.folder-open'), _tr(" Open Folder"))
        self.downloads_open_folder_btn.clicked.connect(self.open_selected_download_folder)
        self.downloads_copy_path_btn = QPushButton(qta.icon('fa5s.copy'), _tr(" Copy Path"))
        self.downloads_copy_path_btn.clicked.connect(self.copy_selected_download_path)
        self.downloads_delete_btn = QPushButton(qta.icon('fa5s.trash-alt', color='red'), _tr(" Delete"))
        self.downloads_delete_btn.clicked.connect(self.delete_selected_download)
        inspector_buttons.addWidget(self.downloads_open_btn)
        inspector_buttons.addWidget(self.downloads_open_folder_btn)
        inspector_buttons.addWidget(self.downloads_copy_path_btn)
        inspector_buttons.addWidget(self.downloads_delete_btn)
        inspector_layout.addLayout(inspector_buttons)

        splitter.addWidget(inspector_group)
        splitter.setSizes([1000, 320])
        layout.addWidget(splitter)

        self.update_downloads_inspector(None)
        return widget

    def create_ai_tab(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)

        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_pane.setMaximumWidth(300)

        chat_list_group = QGroupBox(_tr("Chats"))
        chat_list_layout = QVBoxLayout(chat_list_group)
        self.ai_chat_list = QListWidget()
        self.ai_chat_list.setToolTip(_tr("Your conversations with the AI. Click to switch between them."))
        self.ai_chat_list.currentItemChanged.connect(self.switch_ai_chat)
        chat_list_layout.addWidget(self.ai_chat_list)
        chat_buttons = QHBoxLayout()
        new_chat_btn = QPushButton(qta.icon('fa5s.plus'), _tr(" New"))
        rename_chat_btn = QPushButton(qta.icon('fa5s.edit'), _tr(" Rename"))
        delete_chat_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Delete"))
        new_chat_btn.clicked.connect(self.new_ai_chat)
        rename_chat_btn.clicked.connect(self.rename_ai_chat)
        delete_chat_btn.clicked.connect(self.delete_ai_chat)
        chat_buttons.addWidget(new_chat_btn)
        chat_buttons.addWidget(rename_chat_btn)
        chat_buttons.addWidget(delete_chat_btn)
        chat_list_layout.addLayout(chat_buttons)
        left_layout.addWidget(chat_list_group)

        preset_group = QGroupBox(_tr("AI Presets"))
        preset_layout = QVBoxLayout(preset_group)
        self.ai_preset_combo = QComboBox()
        self.ai_preset_combo.setToolTip(_tr("Switch between different AI models and personalities."))
        self.ai_preset_combo.currentIndexChanged.connect(self.on_ai_preset_changed)
        preset_layout.addWidget(self.ai_preset_combo)
        preset_buttons = QHBoxLayout()
        new_preset_btn = QPushButton(qta.icon('fa5s.plus-circle'), _tr(" New"))
        delete_preset_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Delete"))
        new_preset_btn.clicked.connect(self.new_ai_preset)
        delete_preset_btn.clicked.connect(self.delete_ai_preset)
        preset_buttons.addWidget(new_preset_btn)
        preset_buttons.addWidget(delete_preset_btn)
        preset_layout.addLayout(preset_buttons)
        left_layout.addWidget(preset_group)

        layout.addWidget(left_pane)

        right_tabs = QTabWidget()

        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)

        self.ai_chat_area_stack = QStackedWidget()

        self.ai_chat_tabs = QTabWidget()
        self.ai_chat_tabs.setTabsClosable(False)
        self.ai_chat_tabs.setMovable(True)
        self.ai_chat_area_stack.addWidget(self.ai_chat_tabs)

        self.ai_no_chats_widget = QWidget()
        no_chats_layout = QVBoxLayout(self.ai_no_chats_widget)
        no_chats_layout.setAlignment(Qt.AlignCenter)
        no_chats_label = QLabel(_tr("<h2>Send a message to begin a conversation!</h2>"))
        no_chats_label.setAlignment(Qt.AlignCenter)
        no_chats_label.setStyleSheet("color: #888;")
        no_chats_layout.addWidget(no_chats_label)
        self.ai_chat_area_stack.addWidget(self.ai_no_chats_widget)

        chat_layout.addWidget(self.ai_chat_area_stack)

        personalization_group = QGroupBox(_tr("Personalization"))
        personalization_layout = QFormLayout(personalization_group)
        self.ai_name_edit = QLineEdit()
        self.ai_persona_edit = QPlainTextEdit()

        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["OpenRouter", "Google Gemini", "Ollama (Local)"])
        self.ai_provider_combo.currentTextChanged.connect(self.on_ai_provider_changed)

        self.ai_model_edit = QLineEdit()
        self.ai_gemini_model_combo = QComboBox()
        self.ai_gemini_model_combo.addItems([
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ])
        self.ai_gemini_model_combo.setVisible(False)
        self.ai_ollama_model_combo = QComboBox()
        self.ai_ollama_model_combo.setEditable(True)
        self.ai_ollama_model_combo.setVisible(False)
        self.ai_allow_spicy_check = QCheckBox(_tr("Allow 'spicy' or suggestive content"))

        personalization_layout.addRow(_tr("Name:"), self.ai_name_edit)
        personalization_layout.addRow(_tr("System Prompt / Persona:"), self.ai_persona_edit)
        personalization_layout.addRow(_tr("AI Provider:"), self.ai_provider_combo)
        personalization_layout.addRow(_tr("Model:"), self.ai_model_edit)
        personalization_layout.addRow(_tr("Gemini Model:"), self.ai_gemini_model_combo)
        ollama_row = QHBoxLayout()
        ollama_row.addWidget(self.ai_ollama_model_combo)
        self.ai_ollama_refresh_btn = QPushButton(qta.icon('fa5s.sync-alt'), "")
        self.ai_ollama_refresh_btn.setToolTip(_tr("Refresh Ollama models"))
        self.ai_ollama_refresh_btn.clicked.connect(self._refresh_ollama_models)
        ollama_row.addWidget(self.ai_ollama_refresh_btn)
        personalization_layout.addRow(_tr("Ollama Model:"), ollama_row)
        personalization_layout.addRow(self.ai_allow_spicy_check)

        from PyQt5.QtWidgets import QSlider
        self.ai_formal_casual_slider = QSlider(Qt.Horizontal)
        self.ai_helpful_sassy_slider = QSlider(Qt.Horizontal)
        self.ai_concise_verbose_slider = QSlider(Qt.Horizontal)
        self.ai_creativity_slider = QSlider(Qt.Horizontal)

        personalization_layout.addRow(_tr("Formal <-> Casual:"), self.ai_formal_casual_slider)
        personalization_layout.addRow(_tr("Helpful <-> Sassy:"), self.ai_helpful_sassy_slider)
        personalization_layout.addRow(_tr("Concise <-> Verbose:"), self.ai_concise_verbose_slider)
        personalization_layout.addRow(_tr("Creativity:"), self.ai_creativity_slider)

        save_preset_btn = QPushButton(qta.icon('fa5s.save'), _tr("Save Current Preset"))
        save_preset_btn.clicked.connect(self.save_ai_preset)
        personalization_layout.addRow(save_preset_btn)

        personalization_tab_widget = QWidget()
        personalization_tab_layout = QVBoxLayout(personalization_tab_widget)
        personalization_tab_layout.addWidget(personalization_group)

        right_tabs.addTab(chat_widget, qta.icon('fa5s.comments'), _tr("Chat"))
        right_tabs.addTab(personalization_tab_widget, qta.icon('fa5s.user-cog'), _tr("Personalization"))
        layout.addWidget(right_tabs)

        self.populate_ai_presets()
        self.populate_ai_chats()

        return widget

    def create_minigames_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        game_tabs = QTabWidget()

        post_showdown_game = PostShowdownGame(self)
        game_tabs.addTab(post_showdown_game, _tr("Post Showdown"))

        tag_guesser_game = TagGuesserGame(self)
        game_tabs.addTab(tag_guesser_game, _tr("Tag Guesser"))

        image_scramble_game = ImageScrambleGame(self)
        game_tabs.addTab(image_scramble_game, _tr("Image Scramble"))

        layout.addWidget(game_tabs)
        return widget

    def on_tab_changed(self, index):
        if self.tabs.widget(index) == self.favorites_tab:
            self.refresh_favorites_grid()
        elif self.tabs.widget(index) == self.downloads_tab:
            self.refresh_downloads_grid()
        elif self.tabs.widget(index) == self.hentai_tab and self.hentai_grid.count() == 0:
            self.trending_hentai()

    def on_browser_sub_tab_changed(self, index):
        is_newest_tab = self.browser_content_tabs.widget(index) == self.browser_content_tabs.widget(0)
        self.controls_group.setVisible(is_newest_tab)

    def on_manga_refresh_clicked(self):
        item = self.manga_source_list.currentItem()
        if not item: return
        src = item.data(Qt.UserRole)
        if src == "ALL":
            total = len(self.manga_sources)
            self.manga_progress.setRange(0, total)
            self.manga_progress.setValue(0)
            for s in self.manga_sources:
                self.start_fetch_for_source(s)
        else:
            self.manga_progress.setRange(0, 0)
            self.start_fetch_for_source(src)

    def apply_manga_filter(self):
        item = self.manga_source_list.currentItem()
        if not item: return
        src = item.data(Qt.UserRole)
        query = self.manga_search_input.text().strip()
        query_norm = query.lower()
        if query_norm:
            if src == "ALL":
                self.manga_items_list.clear()
                self.manga_items_list.addItem(_tr("Searching for manga..."))
                self.manga_progress.setRange(0, 0)
                for s in self.manga_sources:
                    self.start_fetch_for_source(s, query=query)
                return
            if (src, query_norm) in self.manga_search_cache:
                self.populate_manga_items_for_source(src)
                return
            self.manga_items_list.clear()
            self.manga_items_list.addItem(_tr("Searching for manga..."))
            self.manga_progress.setRange(0, 0)
            self.start_fetch_for_source(src, query=query)
            return
        if src == "ALL":
            self.populate_manga_items_all()
        else:
            if src in self.manga_entries_cache:
                self.populate_manga_items_for_source(src)
            else:
                self.manga_items_list.clear()
                self.manga_items_list.addItem(_tr("Searching for manga..."))
                self.start_fetch_for_source(src, query=None)

    def clear_manga_search(self):
        self.manga_search_input.setText("")
        self.apply_manga_filter()

    def start_fetch_for_source(self, src, query=None):
        if src in self.manga_threads and self.manga_threads[src].isRunning():
            try:
                self.manga_threads[src].requestInterruption()
                self.manga_threads[src].wait(800)
            except Exception:
                pass
            if self.manga_threads[src].isRunning():
                self.manga_threads[src].terminate()
        self.manga_status_label.setText(_tr("Searching for manga..."))
        thread = SourceFetchThread(src, self, max_items=50, query=query)
        thread.finished.connect(self.on_manga_fetch_finished)
        thread.progress.connect(self.on_manga_fetch_progress)
        self.manga_threads[src] = thread
        thread.start()

    def on_manga_fetch_progress(self, src, count):
        try:
            name = getattr(src, "name", str(src))
            if name.upper() in ("NHENTAI", "E-HENTAI"):
                name = "e-Hentai"
            self.manga_status_label.setText(_tr("Fetching {source} ({count})...").format(source=name, count=count))
        except Exception: pass

    def on_manga_fetch_finished(self, src, entries, source_meta, err):
        processed = []
        for e in entries:
            try:
                title = extract_title(e)
                url = resolve_manga_url(e, src=src, source_meta=source_meta)
                thumb = extract_cover_url(e)
                processed.append({"title": title, "url": url, "thumb": thumb, "raw": e})
            except Exception:
                processed.append({"title": str(e)[:120], "url": None, "thumb": None, "raw": e})
        query_norm = ""
        try:
            query_norm = (source_meta.get("query") or "").strip().lower() if isinstance(source_meta, dict) else ""
        except Exception:
            query_norm = ""
        if query_norm:
            self.manga_search_cache[(src, query_norm)] = processed
        else:
            self.manga_entries_cache[src] = processed

        try:
            if self.manga_progress.maximum() == 0:
                self.manga_progress.setRange(0, 1)
                self.manga_progress.setValue(1)
            else:
                val = self.manga_progress.value() + 1
                self.manga_progress.setValue(min(self.manga_progress.maximum(), val))
        except Exception: pass

        current_item = self.manga_source_list.currentItem()
        if current_item:
            cur_src = current_item.data(Qt.UserRole)
            if cur_src == "ALL": self.populate_manga_items_all()
            elif cur_src == src: self.populate_manga_items_for_source(src)

        if err and not entries:
            QMessageBox.warning(self, f"Fetch error for {getattr(src,'name',str(src))}", f"Errors: {err}")
        if current_item:
            current_src = current_item.data(Qt.UserRole)
            active_q = self.manga_search_input.text().strip().lower()
            if current_src == "ALL":
                if active_q:
                    try:
                        count = sum(len(self.manga_search_cache.get((s, active_q), [])) for s in self.manga_sources)
                        count = min(count, 50)
                    except Exception:
                        count = 0
                else:
                    count = sum(len(self.filter_manga_entries(e)) for e in self.manga_entries_cache.values())
            else:
                if active_q:
                    count = len(self.manga_search_cache.get((current_src, active_q), []))
                else:
                    count = len(self.filter_manga_entries(self.manga_entries_cache.get(current_src, [])))
            self.manga_status_label.setText(_tr("Loaded {count} results.").format(count=count))

    def on_manga_source_selected(self, index=-1):
        item = self.manga_source_list.currentItem()
        if not item: return
        src = item.data(Qt.UserRole)
        self.manga_current_source_id = src
        self.update_manga_inspector(None)
        if src == "ALL":
            self.populate_manga_items_all()
        else:
            if src in self.manga_entries_cache:
                self.populate_manga_items_for_source(src)
            else:
                self.manga_items_list.clear()
                self.manga_items_list.addItem(_tr("Searching for manga..."))
                self.start_fetch_for_source(src)

    def on_manga_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data: return
        entry = data.get("entry")
        source_name = data.get("source")
        self.manga_selected_entry = {"entry": entry, "source": source_name}
        self.update_manga_inspector(self.manga_selected_entry)
        if not getattr(self, 'is_incognito_window', False) and hasattr(self, 'persona') and self.persona is not None:
            try:
                record_manga_open(self.persona, entry, source_name)
                self._schedule_persona_save()
            except Exception as e:
                print(f"Error recording manga open: {e}")

    def open_selected_manga_in_viewer(self):
        if not self.manga_selected_entry:
            return
        entry = self.manga_selected_entry.get("entry")
        if not entry:
            return
        url = entry.get("url")
        if not url:
            QMessageBox.information(self, _tr("No manga found."), _tr("This entry has no URL available to open."))
            return
        if "e-hentai.org/g/" in str(url):
            self.download_selected_manga_pages(open_reader=True)
            return
        if "mangadex.org/title/" in str(url):
            self.download_selected_manga_pages(open_reader=True)
            return
        self.manga_web_view.load(QUrl(url))

    def open_selected_manga_in_browser(self):
        if not self.manga_selected_entry:
            return
        entry = self.manga_selected_entry.get("entry")
        if not entry:
            return
        url = entry.get("url")
        if not url:
            QMessageBox.information(self, _tr("No manga found."), _tr("This entry has no URL available to open."))
            return
        webbrowser.open(url)

    def update_manga_inspector(self, selected):
        if not selected:
            self.manga_info.setPlainText(_tr("No manga found."))
            self.manga_open_btn.setEnabled(False)
            self.manga_open_browser_btn.setEnabled(False)
            self.manga_import_btn.setEnabled(True)
            self.manga_export_btn.setEnabled(True)
            self.manga_download_pages_btn.setEnabled(False)
            self.manga_download_export_btn.setEnabled(False)
            return
        entry = selected.get("entry")
        source_name = selected.get("source")
        lines = []
        title = entry.get("title") if entry else None
        if title:
            lines.append(_tr("Title: {title}").format(title=title))
        if source_name:
            lines.append(_tr("Source: {source}").format(source=source_name))
        url = entry.get("url") if entry else None
        if url:
            lines.append(url)
        self.manga_info.setPlainText("\n".join(lines))
        enabled = bool(url)
        self.manga_open_btn.setEnabled(enabled)
        self.manga_open_browser_btn.setEnabled(enabled)
        self.manga_import_btn.setEnabled(True)
        self.manga_export_btn.setEnabled(True)
        supports_download = bool(url) and (("e-hentai.org/g/" in str(url)) or ("mangadex.org/title/" in str(url)))
        self.manga_download_pages_btn.setEnabled(supports_download)
        self.manga_download_export_btn.setEnabled(supports_download)

        if url and ("mangadex.org/title/" in str(url)) and entry and (not title or len(str(title)) < 5 or str(title).startswith("http")):
            self._ensure_mangadex_title_async(entry)

    def open_book_export_dialog(self):
        dialog = BookExportDialog(self)
        self.open_dialogs.append(dialog)
        dialog.show()
        dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)

    def import_manga_from_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            _tr("Select Images"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not paths:
            return

        title, ok = QInputDialog.getText(self, _tr("Manga Title"), _tr("Enter a title for this manga:"))
        if not ok:
            return
        title = (title or "").strip() or _tr("Imported Manga")

        base_dir = snekbooru_temp_dir("manga", "imports")
        safe_title = re.sub(r"[\\\\/:*?\"<>|]+", "_", title).strip() or "import"
        import_dir = os.path.join(base_dir, safe_title)
        if os.path.exists(import_dir):
            import_dir = os.path.join(base_dir, f"{safe_title}_{int(time.time())}")
        os.makedirs(import_dir, exist_ok=True)

        def _natural_key(s):
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\\d+)", s)]

        ordered = sorted(paths, key=lambda p: _natural_key(os.path.basename(p)))
        for i, src in enumerate(ordered, start=1):
            ext = os.path.splitext(src)[1].lower() or ".png"
            dst = os.path.join(import_dir, f"page_{i:04d}{ext}")
            try:
                shutil.copy2(src, dst)
            except Exception:
                try:
                    shutil.copy(src, dst)
                except Exception:
                    pass

        dialog = MangaBookDialog(self, images_folder=import_dir, title=title)
        self.open_dialogs.append(dialog)
        dialog.show()
        dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)

    def _ensure_mangadex_title_async(self, entry):
        url = entry.get("url") if isinstance(entry, dict) else None
        if not url or "mangadex.org/title/" not in str(url):
            return
        match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]{36})", str(url))
        if not match:
            return
        manga_id = match.group(1)
        if entry.get("_title_fetching"):
            return
        entry["_title_fetching"] = True

        def work():
            if not ENMA_AVAILABLE or Enma is None:
                payload = self._mangadex_request(f"/manga/{manga_id}", params={"includes[]": ["cover_art"]})
                attrs = (payload.get("data") or {}).get("attributes") or {}
                return _mangadex_pick_title(attrs) or manga_id
            local_enma = Enma()
            local_enma.source_manager.http_client = cloudscraper.create_scraper()
            local_enma.source_manager.set_source(Sources.MANGADEX)
            src = local_enma.source_manager.source
            manga = src.get(manga_id)
            title_obj = getattr(manga, "title", None)
            title = _extract_title_from_value(title_obj)
            if not title:
                title = str(getattr(manga, "url", manga_id))
            return title

        worker = ApiWorker(work)
        worker.signals.finished.connect(lambda data, err: self._on_mangadex_title_ready(entry, data, err))
        self.threadpool.start(worker)

    def _on_mangadex_title_ready(self, entry, data, err):
        try:
            entry["_title_fetching"] = False
        except Exception:
            pass
        if err or not data:
            return
        try:
            entry["title"] = str(data)
        except Exception:
            return
        self._update_manga_list_title(entry)
        if self.manga_selected_entry and self.manga_selected_entry.get("entry") is entry:
            self.update_manga_inspector(self.manga_selected_entry)

    def _update_manga_list_title(self, entry):
        if not entry:
            return
        for i in range(self.manga_items_list.count()):
            item = self.manga_items_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue
            if data.get("entry") is entry:
                widget = self.manga_items_list.itemWidget(item) or data.get("widget")
                if widget and hasattr(widget, "set_title"):
                    widget.set_title(entry.get("title") or entry.get("url") or "")
                return

    def download_selected_manga_and_export(self):
        if not self.manga_selected_entry:
            return
        entry = self.manga_selected_entry.get("entry") or {}
        url = entry.get("url")
        if not url:
            QMessageBox.information(self, _tr("No manga found."), _tr("This entry has no URL available."))
            return

        title = entry.get("title") or "Manga"

        if "e-hentai.org/g/" in str(url):
            kind = "ehentai"
            spec = {"kind": kind, "url": str(url)}
            dialog = MangaDownloadExportDialog(self, title=title, source_label="E-HENTAI", download_spec=spec)
            self.open_dialogs.append(dialog)
            dialog.show()
            dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)
            return

        if "mangadex.org/title/" in str(url):
            match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]{36})", str(url))
            if not match:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not parse MangaDex ID."))
                return
            manga_id = match.group(1)

            self.manga_status_label.setText(_tr("Fetching MangaDex chapters..."))
            self.manga_progress.setRange(0, 0)

            def work():
                if not ENMA_AVAILABLE or Enma is None:
                    chapters = self._fetch_mangadex_chapters_pages(manga_id)
                    if not chapters:
                        raise RuntimeError("No chapters found.")
                    chapter_items = []
                    chapter_pages = []
                    for i, ch in enumerate(chapters, start=1):
                        urls = list(ch.get("pages") or [])
                        chapter_pages.append(urls)
                        label = f"Chapter {i}"
                        if ch.get("label"):
                            label += f" - {ch['label']}"
                        if urls:
                            label += f" ({len(urls)} pages)"
                        chapter_items.append(label)
                    return {"chapter_items": chapter_items, "chapter_pages": chapter_pages}, None
                local_enma = Enma()
                local_enma.source_manager.http_client = cloudscraper.create_scraper()
                local_enma.source_manager.set_source(Sources.MANGADEX)
                src = local_enma.source_manager.source
                manga = src.get(manga_id)
                chapters = list(getattr(manga, "chapters", []) or [])
                if not chapters:
                    raise RuntimeError("No chapters found.")
                chapter_items = []
                chapter_pages = []
                for i, ch in enumerate(chapters, start=1):
                    pages = list(getattr(ch, "pages", []) or [])
                    urls = []
                    for p in pages:
                        uri = getattr(p, "uri", None) or getattr(p, "url", None)
                        if uri:
                            urls.append(str(uri))
                    chapter_pages.append(urls)
                    label = f"Chapter {i}"
                    if urls:
                        label += f" ({len(urls)} pages)"
                    chapter_items.append(label)
                return {"chapter_items": chapter_items, "chapter_pages": chapter_pages}, None

            worker = ApiWorker(work)
            worker.signals.finished.connect(lambda data, err: self._on_mangadex_export_chapters_ready(data, err, entry, title))
            self.threadpool.start(worker)
            return

        QMessageBox.information(self, _tr("Not supported"), _tr("Export for this source is not supported yet."))

    def _on_mangadex_export_chapters_ready(self, data, err, entry, title):
        self.manga_progress.setRange(0, 100)
        self.manga_progress.setValue(0)
        if err or not data:
            self.manga_status_label.setText(_tr("Failed to load chapters."))
            QMessageBox.critical(self, _tr("MangaDex error"), str(err or "Unknown error"))
            return
        payload, function_error = data
        if function_error:
            self.manga_status_label.setText(_tr("Failed to load chapters."))
            QMessageBox.critical(self, _tr("MangaDex error"), str(function_error))
            return

        chapter_items = payload.get("chapter_items") or []
        chapter_pages = payload.get("chapter_pages") or []
        if not chapter_items or not chapter_pages:
            self.manga_status_label.setText(_tr("No chapters found."))
            QMessageBox.information(self, _tr("MangaDex"), _tr("No chapters found for this title."))
            return

        idx = 0
        if len(chapter_items) > 1:
            item, ok = QInputDialog.getItem(self, _tr("Select Chapter"), _tr("Chapter:"), chapter_items, 0, False)
            if not ok:
                self.manga_status_label.setText(_tr("Cancelled."))
                return
            try:
                idx = chapter_items.index(item)
            except Exception:
                idx = 0

        page_urls = chapter_pages[idx] if idx < len(chapter_pages) else []
        if not page_urls:
            QMessageBox.information(self, _tr("MangaDex"), _tr("No pages found for that chapter."))
            return

        spec = {"kind": "mangadex", "page_urls": page_urls}
        dialog = MangaDownloadExportDialog(self, title=title, source_label="MANGADEX", download_spec=spec)
        self.open_dialogs.append(dialog)
        dialog.show()
        dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)

    def download_selected_manga_pages(self, open_export=False, open_reader=False, open_folder=False, export_plan=None):
        if not self.manga_selected_entry:
            return
        entry = self.manga_selected_entry.get("entry") or {}
        url = entry.get("url")
        if not url:
            QMessageBox.information(self, _tr("Not supported"), _tr("This entry has no URL available."))
            return

        if "e-hentai.org/g/" in str(url):
            gid, token = parse_gallery_id_token(url)
            if not gid:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not parse gallery ID/token."))
                return

            out_dir = snekbooru_temp_dir("manga", "ehentai", str(gid))
            try:
                os.makedirs(out_dir, exist_ok=True)
                if not os.path.isdir(out_dir):
                    raise RuntimeError(f"Failed to create directory: {out_dir}")
            except Exception as e:
                QMessageBox.critical(self, _tr("Error"), _tr("Could not create download directory: {err}").format(err=str(e)))
                return

            self.manga_status_label.setText(_tr("Downloading pages..."))
            self.manga_progress.setRange(0, 0)

            def work():
                return download_gallery_pages(url, out_dir), None

            worker = ApiWorker(work)
            worker.signals.finished.connect(
                lambda data, err: self._on_manga_pages_downloaded(data, err, entry, out_dir, open_export, open_reader, open_folder, export_plan)
            )
            self.threadpool.start(worker)
            return

        if "mangadex.org/title/" in str(url):
            match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]{36})", str(url))
            if not match:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not parse MangaDex ID."))
                return
            manga_id = match.group(1)

            out_base_dir = snekbooru_temp_dir("manga", "mangadex", manga_id)
            os.makedirs(out_base_dir, exist_ok=True)

            self.manga_status_label.setText(_tr("Fetching MangaDex chapters..."))
            self.manga_progress.setRange(0, 0)

            def work():
                if not ENMA_AVAILABLE or Enma is None:
                    chapters_data = self._fetch_mangadex_chapters_pages(manga_id)
                    if not chapters_data:
                        raise RuntimeError("No chapters found.")
                    chapter_items = []
                    chapters = []
                    for i, ch in enumerate(chapters_data, start=1):
                        label = f"Chapter {i}"
                        if ch.get("label"):
                            label += f" - {ch['label']}"
                        if ch.get("pages"):
                            label += f" ({len(ch['pages'])} pages)"
                        chapter_items.append(label)
                        chapters.append(_dict_to_ns({"pages": [{"uri": u} for u in (ch.get("pages") or [])]}))
                    return {"manga": {"id": manga_id}, "chapters": chapters, "chapter_items": chapter_items, "selected_index": 0}, None
                local_enma = Enma()
                local_enma.source_manager.http_client = cloudscraper.create_scraper()
                local_enma.source_manager.set_source(Sources.MANGADEX)
                src = local_enma.source_manager.source
                manga = src.get(manga_id)
                chapters = list(getattr(manga, "chapters", []) or [])
                if not chapters:
                    raise RuntimeError("No chapters found.")

                chapter_items = []
                for i, ch in enumerate(chapters, start=1):
                    pages_count = getattr(ch, "pages_count", None)
                    label = f"Chapter {i}"
                    if isinstance(pages_count, int):
                        label += f" ({pages_count} pages)"
                    chapter_items.append(label)

                selected_index = 0
                return {"manga": manga, "chapters": chapters, "chapter_items": chapter_items, "selected_index": selected_index}, None

            worker = ApiWorker(work)
            worker.signals.finished.connect(
                lambda data, err: self._on_mangadex_chapters_ready(data, err, entry, out_base_dir, open_export, open_reader, open_folder, export_plan)
            )
            self.threadpool.start(worker)
            return

        QMessageBox.information(self, _tr("Not supported"), _tr("Downloading pages is not supported for this source yet."))

    def _on_manga_pages_downloaded(self, data, err, entry, out_dir, open_export, open_reader, open_folder, export_plan=None):
        self.manga_progress.setRange(0, 100)
        self.manga_progress.setValue(0)
        if err:
            self.manga_status_label.setText(_tr("Download failed."))
            QMessageBox.critical(self, _tr("Download failed"), str(err))
            return
        result, function_error = data
        if function_error:
            self.manga_status_label.setText(_tr("Download failed."))
            QMessageBox.critical(self, _tr("Download failed"), str(function_error))
            return
        self.manga_status_label.setText(_tr("Downloaded {count} pages.").format(count=result.get("pages", 0)))

        if export_plan:
            self.manga_status_label.setText(_tr("Exporting..."))
            self.manga_progress.setRange(0, 0)

            def work_export():
                image_paths = list_image_files(out_dir)
                if not image_paths:
                    raise RuntimeError("No images found to export.")
                fmt = (export_plan.get("fmt") or "").upper()
                out_path = export_plan.get("out_path")
                title = export_plan.get("title") or "Manga"
                if fmt == "PDF":
                    final = export_pdf_from_images(image_paths, out_path)
                elif fmt == "EPUB":
                    final = export_epub_from_images(image_paths, out_path, title=title)
                elif fmt == "PNG ZIP":
                    final = export_png_zip_from_images(image_paths, out_path)
                elif fmt == "MOBI":
                    final = export_mobi_from_images(image_paths, out_path, title=title)
                else:
                    raise RuntimeError("Unsupported export format.")

                if export_plan.get("cleanup"):
                    try:
                        shutil.rmtree(out_dir, ignore_errors=True)
                    except Exception:
                        pass
                return final, None

            worker = ApiWorker(work_export)
            worker.signals.finished.connect(lambda d, e: self._on_manga_export_finished(d, e))
            self.threadpool.start(worker)
            return

        if open_folder:
            try:
                os.startfile(out_dir)
            except Exception:
                pass

        if open_reader:
            title = entry.get("title") or result.get("title") or "Manga"
            if not os.path.isdir(out_dir):
                print(f"DEBUG: out_dir missing before reader: {out_dir}")
                os.makedirs(out_dir, exist_ok=True)
            
            image_files = list_image_files(out_dir)
            if not image_files:
                QMessageBox.warning(self, _tr("No images"), _tr("No images were downloaded for this gallery."))
                return

            dialog = MangaBookDialog(self, images_folder=out_dir, title=title)
            self.open_dialogs.append(dialog)
            dialog.show()
            dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)

        if open_export:
            dialog = BookExportDialog(self, initial_folder=out_dir, allow_cleanup=True)
            try:
                dialog.title_input.setText(entry.get("title") or result.get("title") or "Manga")
                dialog._suggest_output_path()
            except Exception:
                pass
            self.open_dialogs.append(dialog)
            dialog.show()
            dialog.destroyed.connect(lambda: self.open_dialogs.remove(dialog) if dialog in self.open_dialogs else None)

    def _on_manga_export_finished(self, data, err):
        self.manga_progress.setRange(0, 100)
        self.manga_progress.setValue(0)
        if err:
            self.manga_status_label.setText(_tr("Export failed."))
            QMessageBox.critical(self, _tr("Export failed"), str(err))
            return
        out_path, function_error = data
        if function_error:
            self.manga_status_label.setText(_tr("Export failed."))
            QMessageBox.critical(self, _tr("Export failed"), str(function_error))
            return
        self.manga_status_label.setText(_tr("Export complete."))
        QMessageBox.information(self, _tr("Export Complete"), _tr("Saved to: {path}").format(path=out_path))

    def _on_mangadex_chapters_ready(self, data, err, entry, out_base_dir, open_export, open_reader, open_folder, export_plan=None):
        self.manga_progress.setRange(0, 100)
        self.manga_progress.setValue(0)
        if err or not data:
            self.manga_status_label.setText(_tr("Failed to load chapters."))
            QMessageBox.critical(self, _tr("MangaDex error"), str(err or "Unknown error"))
            return
        payload, function_error = data
        if function_error:
            self.manga_status_label.setText(_tr("Failed to load chapters."))
            QMessageBox.critical(self, _tr("MangaDex error"), str(function_error))
            return

        chapters = payload.get("chapters") or []
        chapter_items = payload.get("chapter_items") or []
        if not chapters:
            self.manga_status_label.setText(_tr("No chapters found."))
            QMessageBox.information(self, _tr("MangaDex"), _tr("No chapters found for this title."))
            return

        if len(chapters) > 1:
            item, ok = QInputDialog.getItem(self, _tr("Select Chapter"), _tr("Chapter:"), chapter_items, 0, False)
            if not ok:
                self.manga_status_label.setText(_tr("Cancelled."))
                return
            try:
                idx = chapter_items.index(item)
            except Exception:
                idx = 0
        else:
            idx = 0

        out_dir = os.path.join(out_base_dir, f"chapter_{idx + 1:03d}")
        os.makedirs(out_dir, exist_ok=True)

        self.manga_status_label.setText(_tr("Downloading pages..."))
        self.manga_progress.setRange(0, 0)

        chapter = chapters[idx]

        def work_download():
            http = cloudscraper.create_scraper()
            pages = list(getattr(chapter, "pages", []) or [])
            if not pages:
                raise RuntimeError("No pages in chapter.")
            for i, page in enumerate(pages, start=1):
                uri = getattr(page, "uri", None) or getattr(page, "url", None)
                if not uri:
                    continue
                ext = os.path.splitext(str(uri))[1].split("?")[0].lower()
                if not ext or len(ext) > 6:
                    ext = ".jpg"
                file_path = os.path.join(out_dir, f"page_{i:04d}{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    continue
                r = http.get(str(uri), headers={"User-Agent": USER_AGENT, "Referer": "https://mangadex.org/"}, timeout=60, stream=True)
                r.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
            return {"title": entry.get("title") or entry.get("url"), "pages": len(pages), "output_dir": out_dir}, None

        worker = ApiWorker(work_download)
        worker.signals.finished.connect(
            lambda d, e: self._on_manga_pages_downloaded(d, e, entry, out_dir, open_export, open_reader, open_folder, export_plan)
        )
        self.threadpool.start(worker)

    def populate_manga_sources(self):
        self.manga_source_list.clear()
        if ENMA_AVAILABLE and self.enma:
            self.manga_sources = [s for s in Sources if 'manganato' not in str(s).lower()]
        else:
            self.manga_sources = ["MANGADEX", "E-HENTAI"]
        all_item = QListWidgetItem("All")
        all_item.setData(Qt.UserRole, "ALL")
        self.manga_source_list.addItem(all_item)
        for s in self.manga_sources:
            name = getattr(s, "name", str(s))
            if name.upper() in ("NHENTAI", "E-HENTAI"):
                name = "e-Hentai"
            w = QListWidgetItem(name)
            w.setData(Qt.UserRole, s)
            self.manga_source_list.addItem(w)
        self.manga_source_list.setCurrentRow(0)
        self.on_manga_source_selected(self.manga_source_list.currentItem())

    def filter_manga_entries(self, entries):
        filter_text = self.manga_search_input.text().strip().lower()
        if not filter_text:
            return entries
        return [e for e in entries if filter_text in (e.get("title") or "").lower()]

    def populate_manga_items_all(self):
        self.manga_items_list.clear()
        aggregates = []
        active_q = self.manga_search_input.text().strip().lower()
        if active_q:
            for s in self.manga_sources:
                name = getattr(s, "name", str(s))
                if name.upper() in ("NHENTAI", "E-HENTAI"):
                    name = "e-Hentai"
                for e in self.manga_search_cache.get((s, active_q), []):
                    aggregates.append((name, e))
                    if len(aggregates) >= 50:
                        break
                if len(aggregates) >= 50:
                    break
        else:
            for s, entries in self.manga_entries_cache.items():
                name = getattr(s, "name", str(s))
                if name.upper() in ("NHENTAI", "E-HENTAI"):
                    name = "e-Hentai"
                for e in self.filter_manga_entries(entries):
                    aggregates.append((name, e))
        if not aggregates:
            self.manga_results_label.setText(_tr("No manga found."))
            self.manga_status_label.setText(_tr("No manga found."))
            self.manga_items_list.addItem(_tr("No manga found."))
            return
        for source_name, e in aggregates:
            self.add_manga_item_to_list(e, source_name)
        loaded_text = _tr("Loaded {count} results.").format(count=len(aggregates))
        self.manga_results_label.setText(loaded_text)
        self.manga_status_label.setText(loaded_text)

    def populate_manga_items_for_source(self, src):
        self.manga_items_list.clear()
        active_q = self.manga_search_input.text().strip().lower()
        if active_q:
            entries = self.manga_search_cache.get((src, active_q), [])
        else:
            entries = self.filter_manga_entries(self.manga_entries_cache.get(src, []))
        source_name = getattr(src, "name", str(src))
        if source_name.upper() in ("NHENTAI", "E-HENTAI"):
            source_name = "e-Hentai"
        if not entries:
            self.manga_results_label.setText(_tr("No manga found."))
            self.manga_status_label.setText(_tr("No manga found."))
            self.manga_items_list.addItem(_tr("No manga found."))
            return
        for e in entries:
            self.add_manga_item_to_list(e, source_name)
        loaded_text = _tr("Loaded {count} results.").format(count=len(entries))
        self.manga_results_label.setText(loaded_text)
        self.manga_status_label.setText(loaded_text)

    def add_manga_item_to_list(self, entry_data, source_name):
        item = QListWidgetItem()
        thumb_url = entry_data.get("thumb")
        thumb_pm = self.get_manga_thumb_pixmap(thumb_url)
        widget = MangaListItem(entry_data.get("title"), source_name, thumb_pm, entry_data.get("url"))
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.UserRole, {"source": source_name, "entry": entry_data, "widget": widget})
        self.manga_items_list.addItem(item)
        self.manga_items_list.setItemWidget(item, widget)
        if thumb_url and thumb_pm is None:
            worker = ImageWorker(thumb_url, {"widget": widget, "url": thumb_url})
            worker.signals.finished.connect(self.on_manga_thumb_loaded)
            self.threadpool.start(worker)

    def get_manga_thumb_pixmap(self, url):
        if not url: return None
        if url in self.manga_thumb_cache: return self.manga_thumb_cache[url]
        return None


    def on_manga_cover_loaded(self, pixmap, post_data):
        widget = post_data.get("widget")
        if widget and not pixmap.isNull(): 
            widget.set_pixmap(pixmap)

    def add_favorite_category(self):
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, _tr("New Category"), _tr("Category Name:"))
        if ok and text and text not in self.favorites:
            self.favorites[text] = {}
            save_favorites(self.favorites)
            self.populate_favorite_categories()

    def rename_favorite_category(self):
        current_item = self.fav_category_list.currentItem()
        if not current_item or current_item.text() == "Uncategorized": return
        
        old_name = current_item.text()
        text, ok = QInputDialog.getText(self, _tr("Rename Category"), _tr("New Name:"), QLineEdit.Normal, old_name)
        
        if ok and text and text != old_name and text not in self.favorites:
            self.favorites[text] = self.favorites.pop(old_name)
            save_favorites(self.favorites)
            self.populate_favorite_categories()

    def delete_favorite_category(self):
        current_item = self.fav_category_list.currentItem()
        if not current_item or current_item.text() == "Uncategorized": return

        reply = QMessageBox.question(self, _tr("Delete Category"), 
                                     _tr("Are you sure you want to delete the category '{category}'?\n"
                                         "All favorites within it will be moved to 'Uncategorized'.")
                                     .format(category=current_item.text()),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            category_to_delete = current_item.text()
            posts_to_move = self.favorites.pop(category_to_delete, {})
            self.favorites["Uncategorized"].update(posts_to_move)
            save_favorites(self.favorites)
            self.populate_favorite_categories()

    def on_fav_category_changed(self, current, previous):
        if current:
            self.current_favorites_category = current.text()
            self.refresh_favorites_grid()

    def populate_favorite_categories(self):
        self.fav_category_list.clear()
        if "Uncategorized" in self.favorites:
            self.fav_category_list.addItem("Uncategorized")
        
        for category in sorted(self.favorites.keys()):
            if category != "Uncategorized":
                self.fav_category_list.addItem(category)
        
        items = self.fav_category_list.findItems(self.current_favorites_category, Qt.MatchExactly)
        if items:
            self.fav_category_list.setCurrentItem(items[0])
        elif self.fav_category_list.count() > 0:
            self.fav_category_list.setCurrentRow(0)

    def refresh_favorites_grid(self):
        self.clear_grid(self.fav_grid)
        self.fav_post_to_widget_map.clear()

        category_posts = self.favorites.get(self.current_favorites_category, {})
        filter_text = self.fav_search_input.text().lower()

        if filter_text:
            posts_to_show = {pid: post for pid, post in category_posts.items() if filter_text in post.get('tags', '').lower()}
        else:
            posts_to_show = category_posts

        self.favorites_count_label.setText(_tr("{count} favorites in this category").format(count=len(posts_to_show)))

        self.populate_grid(self.fav_grid, list(posts_to_show.values()), self.fav_post_to_widget_map, self.on_fav_thumbnail_clicked, viewport_width=self.fav_scroll.viewport().width())

    def on_fav_thumbnail_clicked(self, post, widget):
        self.fav_info.setPlainText(self.format_post_info(post))

    def refresh_downloads_grid(self):
        self.clear_grid(self.downloads_grid)
        self.downloads_post_to_widget_map.clear()
        self.downloads_data = load_downloads_data()

        filter_text = self.downloads_search_input.text().lower()
        type_filter_index = self.downloads_type_filter.currentIndex() if hasattr(self, "downloads_type_filter") else 0
        
        posts_to_show = []
        for post in self.downloads_data.values():
            local_path = post.get("local_path", "")
            if not os.path.exists(local_path):
                continue
            file_ext = post.get("file_ext") or os.path.splitext(local_path)[1].lstrip('.')
            file_ext = (file_ext or "").lower()
            if type_filter_index == 1 and file_ext not in ["jpg", "jpeg", "png", "webp", "bmp", "gif"]:
                continue
            if type_filter_index == 2 and file_ext != "gif":
                continue
            if type_filter_index == 3 and file_ext not in ["mp4", "webm", "mov", "avi", "mkv"]:
                continue
            if not filter_text or filter_text in post.get('tags', '').lower():
                posts_to_show.append(post)

        self.downloads_count_label.setText(_tr("{count} downloaded files").format(count=len(posts_to_show)))
        self.downloads_posts = posts_to_show
        self.populate_grid(self.downloads_grid, posts_to_show, self.downloads_post_to_widget_map, self.on_downloads_thumbnail_clicked, is_local=True, viewport_width=self.downloads_scroll.viewport().width())

    def on_downloads_thumbnail_clicked(self, post, widget):
        self.last_selected = post
        self.update_downloads_inspector(post)

    def update_downloads_inspector(self, post):
        if not post:
            self.downloads_info.setPlainText(_tr("No download selected."))
            self.downloads_preview_label.setText(_tr("Select a download to preview."))
            self.downloads_preview_label.setPixmap(QPixmap())
            for btn in [self.downloads_open_btn, self.downloads_open_folder_btn, self.downloads_copy_path_btn, self.downloads_delete_btn]:
                btn.setEnabled(False)
            return

        local_path = post.get("local_path", "")
        file_ext = post.get("file_ext") or os.path.splitext(local_path)[1].lstrip('.')
        file_ext = (file_ext or "").lower()
        info_lines = []
        info_lines.append(f"File: {local_path}")
        if file_ext:
            info_lines.append(f"Type: {file_ext}")
        if post.get("source_post_url"):
            info_lines.append(f"Source: {post.get('source_post_url')}")
        if post.get("tags"):
            info_lines.append(f"Tags: {post.get('tags')}")
        self.downloads_info.setPlainText("\n".join(info_lines))

        self.downloads_preview_label.setText("")
        self.downloads_preview_label.setPixmap(QPixmap())
        preview_loaded = False
        if local_path and os.path.exists(local_path) and file_ext in ["jpg", "jpeg", "png", "webp", "bmp", "gif"]:
            pix = QPixmap(local_path)
            if not pix.isNull():
                self.downloads_preview_label.setPixmap(pix.scaled(self.downloads_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                preview_loaded = True
        if not preview_loaded and post.get("preview_url"):
            self.downloads_preview_post_id = post.get("id")
            worker = ImageWorker(post.get("preview_url"), post)
            worker.signals.finished.connect(self.on_download_preview_loaded)
            self.threadpool.start(worker)
        if not preview_loaded and not post.get("preview_url"):
            self.downloads_preview_label.setText(_tr("No preview available."))

        has_local = bool(local_path and os.path.exists(local_path))
        for btn in [self.downloads_open_btn, self.downloads_open_folder_btn, self.downloads_copy_path_btn, self.downloads_delete_btn]:
            btn.setEnabled(has_local)

    def on_download_preview_loaded(self, pixmap, post):
        if post.get("id") != getattr(self, "downloads_preview_post_id", None):
            return
        if not pixmap.isNull():
            self.downloads_preview_label.setPixmap(pixmap.scaled(self.downloads_preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.downloads_preview_label.setText(_tr("No preview available."))

    def open_downloads_folder(self):
        download_dir = SETTINGS.get("download_dir")
        if download_dir and os.path.exists(download_dir):
            from PyQt5.QtGui import QDesktopServices
            from PyQt5.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(download_dir))

    def open_selected_download_in_viewer(self):
        if self.last_selected:
            self.open_post_full(self.last_selected)

    def open_selected_download_folder(self):
        if not self.last_selected:
            return
        local_path = self.last_selected.get("local_path")
        if local_path and os.path.exists(local_path):
            from PyQt5.QtGui import QDesktopServices
            from PyQt5.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(local_path)))

    def copy_selected_download_path(self):
        if self.last_selected:
            QApplication.clipboard().setText(self.last_selected.get("local_path", ""))

    def delete_selected_download(self):
        if not self.last_selected:
            return
        post = self.last_selected
        reply = QMessageBox.question(self, _tr("Confirm Delete"),
                                     _tr("Are you sure you want to permanently delete this file from your disk?\n\n{path}").format(path=post.get("local_path")),
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            file_hash = get_file_hash(post)
            if file_hash in self.downloads_data:
                del self.downloads_data[file_hash]
                save_downloads_data(self.downloads_data)
            try:
                if os.path.exists(post.get("local_path", "")):
                    os.remove(post.get("local_path"))
                if os.path.exists(post.get("local_thumbnail_path", "")):
                    os.remove(post.get("local_thumbnail_path"))
            except OSError as e:
                QMessageBox.warning(self, _tr("Delete Error"), str(e))
            self.refresh_downloads_grid()
            self.update_downloads_inspector(None)

    def import_local_folder(self):
        from PyQt5.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, _tr("Select Folder to Import"))
        if not dir_path: return

        QMessageBox.information(self, _tr("Importing"), _tr("Importing files... The app may freeze."))
        
        imported_count = 0
        for filename in os.listdir(dir_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')):
                file_path = os.path.join(dir_path, filename)
            mock_post = {
                    "id": f"local_{filename}",
                    "file_url": f"file:///{file_path}",
                    "source_post_url": f"file:///{file_path}",
                    "tags": "local_import",
                    "file_ext": filename.split('.')[-1].lower(),
                    "local_path": file_path,
                    "local_thumbnail_path": None 
                }
            file_hash = get_file_hash(mock_post)
            if file_hash not in self.downloads_data:
                self.downloads_data[file_hash] = mock_post
                imported_count += 1
        
        save_downloads_data(self.downloads_data)
        QMessageBox.information(self, _tr("Import Complete"), _tr("Imported {count} new files.").format(count=imported_count))
        self.refresh_downloads_grid()

    def populate_ai_presets(self):
        self.ai_preset_combo.clear()
        for preset in SETTINGS.get("ai_presets", []):
            self.ai_preset_combo.addItem(preset["name"])
        
        active_index = SETTINGS.get("ai_active_preset_index", 0)
        if 0 <= active_index < self.ai_preset_combo.count():
            self.ai_preset_combo.setCurrentIndex(active_index)
            self.load_ai_preset_settings(active_index)

    def on_ai_preset_changed(self, index):
        if index != -1:
            SETTINGS["ai_active_preset_index"] = index
            self.load_ai_preset_settings(index)

    def on_ai_provider_changed(self, provider):
        is_gemini = provider == "Google Gemini"
        is_ollama = provider == "Ollama (Local)"
        self.ai_model_edit.setVisible(not is_gemini and not is_ollama)
        self.ai_gemini_model_combo.setVisible(is_gemini)
        self.ai_ollama_model_combo.setVisible(is_ollama)
        self.ai_ollama_refresh_btn.setVisible(is_ollama)
        if is_ollama:
            self._ensure_ollama()

    def _ensure_ollama(self):
        try:
            import requests as _r
            resp = _r.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                self._refresh_ollama_models()
                return
        except Exception:
            pass

        ollama_exe = self._find_ollama_exe()
        if ollama_exe:
            try:
                import subprocess
                subprocess.Popen([ollama_exe, "serve"], creationflags=0x08000000 if os.name == 'nt' else 0)
                QTimer.singleShot(3000, self._refresh_ollama_models)
                return
            except Exception:
                pass

        reply = QMessageBox.question(
            self,
            _tr("Ollama Not Found"),
            _tr("Ollama is not installed. It lets you run AI models locally.\n\nDownload and install Ollama now?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self._download_and_install_ollama()

    def _find_ollama_exe(self):
        paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("USERPROFILE", ""), "ollama", "ollama.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        try:
            import shutil
            found = shutil.which("ollama")
            if found:
                return found
        except Exception:
            pass
        return None

    def _download_and_install_ollama(self):
        from PyQt5.QtWidgets import QProgressDialog
        url = "https://ollama.com/download/OllamaSetup.exe"
        installer_path = os.path.join(snekbooru_temp_dir("ollama"), "OllamaSetup.exe")
        os.makedirs(os.path.dirname(installer_path), exist_ok=True)

        progress = QProgressDialog(_tr("Downloading Ollama..."), _tr("Cancel"), 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        def _download():
            try:
                import requests as _r
                resp = _r.get(url, stream=True, timeout=300)
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                if total:
                    progress.setMaximum(total)
                downloaded = 0
                with open(installer_path, 'wb') as f:
                    for chunk in resp.iter_content(8192):
                        if progress.wasCanceled():
                            return False, "Cancelled"
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            progress.setValue(downloaded)
                return True, None
            except Exception as e:
                return False, str(e)

        def _on_download_done(data, err):
            progress.close()
            if err or not data:
                QMessageBox.warning(self, _tr("Download Failed"), str(err or "Unknown error"))
                return
            try:
                import subprocess
                subprocess.Popen([installer_path, "/S"], creationflags=0x08000000)
                QMessageBox.information(
                    self, _tr("Installing Ollama"),
                    _tr("Ollama is installing. Once complete, it will start automatically.\n\nAfter installation, pull a model by typing its name in the model field (e.g. 'llama3.2').")
                )
            except Exception as e:
                QMessageBox.warning(self, _tr("Install Failed"), str(e))

        worker = ApiWorker(_download)
        worker.signals.finished.connect(_on_download_done)
        self.threadpool.start(worker)

    def _refresh_ollama_models(self):
        self.ai_ollama_model_combo.clear()
        default_models = ["llama3.2", "llama3.1", "gemma3", "mistral", "phi3", "qwen2.5"]
        for m in default_models:
            self.ai_ollama_model_combo.addItem(m)
        self.ai_ollama_model_combo.setEditText("llama3.2")

        def _fetch():
            try:
                import requests as _r
                resp = _r.get("http://localhost:11434/api/tags", timeout=5)
                resp.raise_for_status()
                data = resp.json()
                return [m.get("name", "") for m in data.get("models", [])], None
            except Exception as e:
                return [], str(e)

        worker = ApiWorker(_fetch)
        def on_done(result, err):
            if result and not err:
                model_list = result[0] if isinstance(result, tuple) else result
                if not isinstance(model_list, list):
                    return
                current = self.ai_ollama_model_combo.currentText()
                self.ai_ollama_model_combo.clear()
                for m in model_list:
                    self.ai_ollama_model_combo.addItem(m)
                if current:
                    idx = self.ai_ollama_model_combo.findText(current)
                    if idx >= 0:
                        self.ai_ollama_model_combo.setCurrentIndex(idx)
        worker.signals.finished.connect(on_done)
        self.threadpool.start(worker)

    def load_ai_preset_settings(self, index):
        presets = SETTINGS.get("ai_presets", [])
        if 0 <= index < len(presets):
            preset = presets[index]
            self.ai_name_edit.setText(preset.get("name", ""))
            self.ai_persona_edit.setPlainText(preset.get("persona", ""))
            
            provider = preset.get("provider", "OpenRouter")
            self.ai_provider_combo.blockSignals(True)
            self.ai_provider_combo.setCurrentText(provider)
            self.ai_provider_combo.blockSignals(False)
            
            self.on_ai_provider_changed(provider)
            
            self.ai_model_edit.setText(preset.get("model", ""))
            
            if provider == "Google Gemini":
                gemini_model = preset.get("model", "gemini-2.5-flash")
                idx = self.ai_gemini_model_combo.findText(gemini_model)
                if idx >= 0:
                    self.ai_gemini_model_combo.setCurrentIndex(idx)
            elif provider == "Ollama (Local)":
                ollama_model = preset.get("model", "llama3.2")
                self.ai_ollama_model_combo.setEditText(ollama_model)
            
            self.ai_allow_spicy_check.setChecked(preset.get("allow_spicy", True))
            self.ai_formal_casual_slider.setValue(preset.get("formal_casual", 50))
            self.ai_helpful_sassy_slider.setValue(preset.get("helpful_sassy", 20))
            self.ai_concise_verbose_slider.setValue(preset.get("concise_verbose", 50))
            self.ai_creativity_slider.setValue(preset.get("creativity", 80))

    def save_ai_preset(self):
        active_index = SETTINGS.get("ai_active_preset_index", 0)
        presets = SETTINGS.get("ai_presets", [])
        if 0 <= active_index < len(presets):
            preset = presets[active_index]
            preset["name"] = self.ai_name_edit.text()
            preset["persona"] = self.ai_persona_edit.toPlainText()
            preset["provider"] = self.ai_provider_combo.currentText()
            
            if self.ai_provider_combo.currentText() == "Google Gemini":
                preset["model"] = self.ai_gemini_model_combo.currentText()
            elif self.ai_provider_combo.currentText() == "Ollama (Local)":
                preset["model"] = self.ai_ollama_model_combo.currentText()
            else:
                preset["model"] = self.ai_model_edit.text()
            
            preset["allow_spicy"] = self.ai_allow_spicy_check.isChecked()
            preset["formal_casual"] = self.ai_formal_casual_slider.value()
            preset["helpful_sassy"] = self.ai_helpful_sassy_slider.value()
            preset["concise_verbose"] = self.ai_concise_verbose_slider.value()
            preset["creativity"] = self.ai_creativity_slider.value()
            
            save_settings(SETTINGS)
            self.populate_ai_presets() 
            QMessageBox.information(self, _tr("Preset Saved"), _tr("AI preset '{name}' has been updated.").format(name=preset["name"]))

    def new_ai_preset(self):
        from snekbooru.common.constants import DEFAULT_AI_MODEL
        new_preset = {
            "name": "New Preset", "persona": "You are a helpful assistant.", "model": DEFAULT_AI_MODEL,
            "provider": "OpenRouter", "allow_spicy": True, "formal_casual": 50, "helpful_sassy": 50,
            "concise_verbose": 50, "creativity": 50
        }
        SETTINGS["ai_presets"].append(new_preset)
        SETTINGS["ai_active_preset_index"] = len(SETTINGS["ai_presets"]) - 1
        save_settings(SETTINGS)
        self.populate_ai_presets()

    def delete_ai_preset(self):
        if len(SETTINGS.get("ai_presets", [])) <= 1:
            QMessageBox.warning(self, _tr("Cannot Delete"), _tr("You must have at least one AI preset."))
            return

        active_index = SETTINGS.get("ai_active_preset_index", 0)
        del SETTINGS["ai_presets"][active_index]
        SETTINGS["ai_active_preset_index"] = 0
        save_settings(SETTINGS)
        self.populate_ai_presets()

    def populate_ai_chats(self):
        self.ai_chat_list.clear()
        self.ai_chat_tabs.clear()
        self.ai_chat_ui.clear()

        chats = SETTINGS.get("ai_chats", [])
        if not chats:
            self.ai_chat_area_stack.setCurrentWidget(self.ai_no_chats_widget)
            return

        from collections import defaultdict
        now = time.time()
        groups = defaultdict(list)
        for i, chat in enumerate(chats):
            created = chat.get("created", 0) or chat.get("last_active", 0)
            age_days = (now - created) / 86400
            if age_days < 1:
                groups[_tr("Today")].append((i, chat))
            elif age_days < 2:
                groups[_tr("Yesterday")].append((i, chat))
            elif age_days < 7:
                groups[_tr("This Week")].append((i, chat))
            elif age_days < 30:
                groups[_tr("This Month")].append((i, chat))
            else:
                groups[_tr("Older")].append((i, chat))

        ordered = ["Today", "Yesterday", "This Week", "This Month", "Older"]
        chat_index_map = {}
        for group_name in ordered:
            tr_name = _tr(group_name)
            items = groups.get(tr_name, [])
            if not items:
                continue
            header_item = QListWidgetItem(f"── {tr_name} ──")
            header_item.setFlags(Qt.NoItemFlags)
            header_item.setForeground(Qt.gray)
            font = header_item.font()
            font.setBold(True)
            header_item.setFont(font)
            self.ai_chat_list.addItem(header_item)
            for idx, chat in items:
                item = QListWidgetItem(chat["name"])
                item.setData(Qt.UserRole, idx)
                self.ai_chat_list.addItem(item)
                chat_index_map[idx] = True

        self.ai_chat_area_stack.setCurrentWidget(self.ai_chat_tabs)

        for i, chat in enumerate(chats):
            self.add_ai_chat_tab(chat["name"], chat.get("history", []))

        active_chat_index = SETTINGS.get("ai_active_chat_index", 0)
        if 0 <= active_chat_index < self.ai_chat_list.count():
            for row in range(self.ai_chat_list.count()):
                item = self.ai_chat_list.item(row)
                if item and item.data(Qt.UserRole) == active_chat_index:
                    self.ai_chat_list.setCurrentRow(row)
                    self.ai_chat_tabs.setCurrentIndex(active_chat_index)
                    break

    def add_ai_chat_tab(self, name, history):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        chat_list = ChatMessageList()
        layout.addWidget(chat_list, 1)

        input_row = QHBoxLayout()
        input_area = QPlainTextEdit()
        input_area.setObjectName("ai_chat_input_area")
        input_area.setPlaceholderText(_tr("Type your message here... Press Ctrl+Enter to send."))
        input_area.setMaximumHeight(100)
        input_area.installEventFilter(self)
        self.ai_input_areas.append(input_area)

        send_btn = QPushButton(qta.icon('fa5s.paper-plane'), _tr(" Send"))
        send_btn.clicked.connect(lambda checked=None: self._send_from_tab())

        stop_btn = QPushButton(qta.icon('fa5s.stop'), _tr(" Stop"))
        stop_btn.setToolTip(_tr("Stop the current AI response"))
        stop_btn.clicked.connect(lambda: self._stop_ai_generation())
        stop_btn.setVisible(False)

        input_row.addWidget(input_area)
        input_row.addWidget(send_btn)
        input_row.addWidget(stop_btn)
        layout.addLayout(input_row)

        self.ai_chat_tabs.addTab(tab, name)

        tab_index = self.ai_chat_tabs.indexOf(tab)
        self.ai_chat_ui[tab_index] = {
            "chat_list": chat_list,
            "input_area": input_area,
            "send_btn": send_btn,
            "stop_btn": stop_btn,
        }

        self._rebuild_chat_display(tab_index)


    def switch_ai_chat(self, current, previous):
        if current and current.data(Qt.UserRole) is not None:
            index = current.data(Qt.UserRole)
            if index < self.ai_chat_tabs.count():
                self.ai_chat_tabs.setCurrentIndex(index)
                SETTINGS["ai_active_chat_index"] = index
                self._rebuild_chat_display(index)

    def new_ai_chat(self):
        chat_num = len(SETTINGS["ai_chats"]) + 1
        SETTINGS["ai_chats"].append({
            "name": f"Chat {chat_num}",
            "history": [],
            "memory": "",
            "created": time.time(),
            "last_active": time.time()
        })
        SETTINGS["ai_active_chat_index"] = len(SETTINGS["ai_chats"]) - 1
        save_settings(SETTINGS)
        self.populate_ai_chats()

    def rename_ai_chat(self):
        active_index = SETTINGS.get("ai_active_chat_index", 0)
        if active_index < 0: return
        
        from PyQt5.QtWidgets import QInputDialog
        old_name = SETTINGS["ai_chats"][active_index]["name"]
        new_name, ok = QInputDialog.getText(self, _tr("Rename Chat"), _tr("Enter new name:"), text=old_name)
        
        if ok and new_name:
            SETTINGS["ai_chats"][active_index]["name"] = new_name
            save_settings(SETTINGS)
            self.populate_ai_chats()

    def delete_ai_chat(self):
        active_index = SETTINGS.get("ai_active_chat_index", 0)
        if active_index < 0 or not SETTINGS.get("ai_chats"): return
        
        del SETTINGS["ai_chats"][active_index]
        
        if active_index in self.ai_chat_displayed_posts:
            del self.ai_chat_displayed_posts[active_index]
        
        if not SETTINGS.get("ai_chats"):
            SETTINGS["ai_active_chat_index"] = -1
        else:
            SETTINGS["ai_active_chat_index"] = 0
            
        save_settings(SETTINGS)
        self.populate_ai_chats()

    def _send_from_tab(self):
        active_index = self.ai_chat_tabs.currentIndex()
        if active_index < 0: return
        self.send_ai_message(active_index)

    def send_ai_message(self, chat_index=None, retry_from=None):
        if chat_index is None:
            active_index = self.ai_chat_tabs.currentIndex()
        else:
            active_index = chat_index

        if active_index < 0 and not SETTINGS.get("ai_chats"):
            SETTINGS["ai_chats"] = [{"name": "Chat 1", "history": [], "memory": "", "created": time.time()}]
            SETTINGS["ai_active_chat_index"] = 0
            save_settings(SETTINGS)
            self.populate_ai_chats()
            active_index = 0

        if active_index < 0: return

        ui = self.ai_chat_ui[active_index]
        input_area = ui["input_area"]
        chat = SETTINGS["ai_chats"][active_index]
        chat.setdefault("history", [])
        chat.setdefault("memory", "")
        chat.setdefault("created", time.time())

        if not self.ai_can_send:
            return

        if retry_from is not None:
            history = chat["history"]
            if retry_from >= len(history) or history[retry_from]["role"] != "user":
                return
            user_message = history[retry_from]["content"]
            del history[retry_from:]
        else:
            user_message = input_area.toPlainText().strip()
            if not user_message:
                return

        chat["history"].append({"role": "user", "content": user_message})
        chat["last_active"] = time.time()

        if chat.get("name", "").startswith("Chat ") and len(chat["history"]) == 1:
            auto_name = user_message[:40].replace("\n", " ").strip()
            if auto_name:
                chat["name"] = auto_name
                save_settings(SETTINGS)
                self.populate_ai_chats()

        if retry_from is not None:
            self._rebuild_chat_display(active_index)
        else:
            import markdown
            bubble = ChatBubble(markdown.markdown(user_message, extensions=['fenced_code', 'tables']), is_user=True)
            ui["chat_list"].add_bubble(bubble)

        self._send_ai_request(active_index)

    def _build_ai_messages(self, chat_index):
        chat = SETTINGS["ai_chats"][chat_index]
        history = chat.get("history", [])
        memory = chat.get("memory", "")

        active_preset = SETTINGS["ai_presets"][SETTINGS["ai_active_preset_index"]]
        system_prompt = self._prepare_ai_system_prompt(active_preset)

        if memory:
            system_prompt += f"\n\n[USER_MEMORY]\n{memory}\n[/USER_MEMORY]"

        messages = [{"role": "system", "content": system_prompt}]
        recent = history[-40:]
        messages.extend(recent)
        return messages

    def _compact_ai_context(self, chat_index):
        chat = SETTINGS["ai_chats"][chat_index]
        history = chat.get("history", [])
        if len(history) < 30:
            return

        active_preset = SETTINGS["ai_presets"][SETTINGS["ai_active_preset_index"]]
        model = active_preset.get("model", "")

        summary_prompt = (
            "Summarize the following conversation into a concise memory block. "
            "Keep key facts, user preferences, names, and important context. "
            "Output ONLY the summary text, no preamble."
        )
        msgs = [{"role": "system", "content": summary_prompt}]
        for h in history[:20]:
            role = "user" if h["role"] == "user" else "assistant"
            msgs.append({"role": role, "content": h["content"][:2000]})

        try:
            headers = {
                "Authorization": f"Bearer {SETTINGS.get('ai_api_key')}",
                "Content-Type": "application/json",
            }
            payload = {"model": model or DEFAULT_AI_MODEL, "messages": msgs, "temperature": 0.3}
            resp = requests.post(
                SETTINGS.get('ai_endpoint', 'https://openrouter.ai/api/v1/chat/completions'),
                headers=headers, json=payload, timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                summary = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if summary:
                    chat["memory"] = summary.strip()
                    chat["history"] = history[-15:]
                    save_settings(SETTINGS)
        except Exception:
            pass

    def _trim_conversation_history(self, history, max_messages=40):
        if len(history) <= max_messages:
            return history
        trimmed = history[-max_messages:]
        if trimmed[0]["role"] == "assistant":
            trimmed = trimmed[1:]
        return trimmed

    def _stop_ai_generation(self):
        if hasattr(self, '_current_ai_worker') and self._current_ai_worker:
            self._current_ai_worker.stop()
            try:
                self._current_ai_worker.signals.chunk.disconnect()
                self._current_ai_worker.signals.finished.disconnect()
                self._current_ai_worker.signals.error.disconnect()
            except Exception:
                pass
            self._current_ai_worker = None

        active_index = self.ai_chat_tabs.currentIndex()
        if active_index >= 0 and active_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[active_index]
            stopped_bubble = ChatBubble("[Stopped]", is_user=False)
            ui["chat_list"].add_bubble(stopped_bubble)
            self.reset_ai_cooldown(active_index)

    def on_ai_chunk_received(self, chunk, chat_index):
        if chat_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[chat_index]
            bubble = ui.get("_streaming_bubble")
            if bubble:
                if not getattr(bubble, '_started', False):
                    bubble._started = True
                    bubble.set_text("")
                bubble.append_text(chunk)

    def on_ai_finished(self, full_response, chat_index):
        if chat_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[chat_index]
            bubble = ui.pop("_streaming_bubble", None)
            if bubble:
                import markdown
                clean = re.sub(r'\{+(?:SEARCH|search|SET|set|UPDATE_SETTING|update_setting|OPEN_TAB|open_tab|HENTAI_SEARCH|hentai_search|MANGA_SEARCH|manga_search|HENTAI_TRENDING|hentai_trending|DOWNLOAD|download|FAVORITE_ADD|favorite_add|FAVORITE_REMOVE|favorite_remove|FAVORITE_CREATE|favorite_create|FAVORITE_RENAME|favorite_rename|FAVORITE_DELETE|favorite_delete|FAVORITE_MERGE|favorite_merge|CURATE|curate):\s*[^}]+\}+', '', full_response, flags=re.DOTALL)
                clean = re.sub(r'\{+(?:RANDOM_FAVORITE|random_favorite|HENTAI_RANDOM|hentai_random|SHOW_SIMILAR|show_similar):?\s*[^}]*\}+', '', clean)
                bubble.set_text(markdown.markdown(clean.strip(), extensions=['fenced_code', 'tables']))

        self._ai_pending_settings = {}
        self.process_ai_actions(full_response, chat_index)

        if self._ai_pending_settings:
            old_lang = SETTINGS.get("language")
            SETTINGS.update(self._ai_pending_settings)
            save_settings(SETTINGS)
            self.reapply_settings(old_lang)
            if chat_index in self.ai_chat_ui:
                keys = ", ".join(self._ai_pending_settings.keys())
                confirm = ChatBubble(_tr("Applied: {keys}").format(keys=keys), is_user=False)
                self.ai_chat_ui[chat_index]["chat_list"].add_bubble(confirm)
            self._ai_pending_settings = {}

        chat = SETTINGS["ai_chats"][chat_index]
        chat["history"].append({"role": "assistant", "content": full_response})
        chat["last_active"] = time.time()
        save_settings(SETTINGS)

        if len(chat["history"]) > 30:
            self._compact_ai_context(chat_index)

        self.ai_cooldown_timer.singleShot(1000, lambda: self.reset_ai_cooldown(chat_index))

    def render_ai_chat_history(self, chat_index):
        if chat_index not in self.ai_chat_ui:
            return
        ui = self.ai_chat_ui[chat_index]
        chat_list = ui["chat_list"]
        for b in list(chat_list.bubbles):
            b.deleteLater()
        chat_list.bubbles.clear()

        history = SETTINGS.get("ai_chats", [{}])[chat_index].get("history", [])
        import markdown
        for i, msg in enumerate(history):
            is_user = msg["role"] == "user"
            content = msg["content"]
            if not is_user:
                content = re.sub(r'\{+(?:SEARCH|search|SET|set|UPDATE_SETTING|update_setting|OPEN_TAB|open_tab|HENTAI_SEARCH|hentai_search|MANGA_SEARCH|manga_search|HENTAI_TRENDING|hentai_trending|DOWNLOAD|download|FAVORITE_ADD|favorite_add|FAVORITE_REMOVE|favorite_remove|FAVORITE_CREATE|favorite_create|FAVORITE_RENAME|favorite_rename|FAVORITE_DELETE|favorite_delete|FAVORITE_MERGE|favorite_merge|CURATE|curate|RANDOM_FAVORITE|random_favorite|HENTAI_RANDOM|hentai_random|SHOW_SIMILAR|show_similar):?\s*[^}]*\}+', '', content, flags=re.DOTALL)
            content = markdown.markdown(content.strip(), extensions=['fenced_code', 'tables'])
            bubble = ChatBubble(content, is_user=is_user, msg_index=i)
            bubble.edit_requested.connect(lambda b, ci=chat_index: self._edit_ai_message(ci, b))
            bubble.retry_requested.connect(lambda b, ci=chat_index: self._retry_ai_message(ci, b))
            chat_list.add_bubble(bubble)
            if "search_results" in msg and not is_user:
                for res in msg["search_results"]:
                    if 'image_data' in res:
                        pix = QPixmap()
                        pix.loadFromData(base64.b64decode(res['image_data']))
                        img_bubble = ChatImageBubble(pix, res)
                        img_bubble.clicked.connect(lambda post=res: self._open_ai_search_result(post))
                        chat_list.add_bubble(img_bubble)
            if "hentai_results" in msg and not is_user:
                for rd_data in msg["hentai_results"]:
                    card = ChatRefCard(rd_data.get("name", "Untitled"), None, rd_data)
                    card.clicked.connect(lambda rd=rd_data: self._on_ai_ref_clicked(rd))
                    chat_list.add_bubble(card)
            if "manga_results" in msg and not is_user:
                for rd_data in msg["manga_results"]:
                    card = ChatRefCard(rd_data.get("title", "Untitled"), None, rd_data)
                    card.clicked.connect(lambda rd=rd_data: self._on_ai_ref_clicked(rd))
                    chat_list.add_bubble(card)

    def _open_ai_search_result(self, post_data):
        post_id = post_data.get('post_id', '')
        post = self.ai_search_results.get(post_id)
        if post:
            self.open_ai_post_viewer(post)

    def _edit_ai_message(self, chat_index, bubble):
        history = SETTINGS["ai_chats"][chat_index]["history"]
        idx = bubble.msg_index
        if idx < 0 or idx >= len(history) or history[idx]["role"] != "user":
            return
        if getattr(bubble, '_editing', False):
            return
        bubble._editing = True

        old_text = history[idx]["content"]
        edit = QTextEdit(bubble)
        edit.setPlainText(old_text)
        edit.setStyleSheet("QTextEdit { background: #1e3a5f; color: #fff; border: 1px solid #3b82f6; border-radius: 8px; padding: 6px; }")
        edit.setMaximumHeight(120)
        bubble.main_layout.insertWidget(0, edit)
        bubble.text_label.hide()
        edit.setFocus()

        def cancel_edit():
            edit.deleteLater()
            bubble.text_label.show()
            bubble._editing = False

        def save_edit():
            new_text = edit.toPlainText().strip()
            edit.deleteLater()
            bubble.text_label.show()
            bubble._editing = False
            if new_text and new_text != old_text:
                history[idx]["content"] = new_text
                del history[idx + 1:]
                save_settings(SETTINGS)
                self.render_ai_chat_history(chat_index)
                self._send_ai_request(chat_index)
            else:
                import markdown
                bubble.set_text(markdown.markdown(old_text, extensions=['fenced_code', 'tables']))

        def edit_keypress(e):
            if e.key() == Qt.Key_Escape:
                cancel_edit()
                return True
            if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
                save_edit()
                return True
            return QTextEdit.keyPressEvent(edit, e)

        edit.keyPressEvent = edit_keypress

    def _send_ai_request(self, chat_index):
        ui = self.ai_chat_ui[chat_index]
        if not self.ai_can_send:
            return
        ui["input_area"].setEnabled(False)
        ui["send_btn"].setEnabled(False)
        ui["stop_btn"].setVisible(True)
        self.ai_can_send = False
        ui["input_area"].clear()

        messages = self._build_ai_messages(chat_index)
        active_preset = SETTINGS["ai_presets"][SETTINGS["ai_active_preset_index"]]
        self._current_ai_worker = AIStreamWorker(messages, temperature=active_preset["creativity"] / 100.0)
        self._current_ai_worker.signals.chunk.connect(lambda chunk: self.on_ai_chunk_received(chunk, chat_index))
        self._current_ai_worker.signals.finished.connect(lambda full_response: self.on_ai_finished(full_response, chat_index))
        self._current_ai_worker.signals.error.connect(self.on_ai_error)
        self.threadpool.start(self._current_ai_worker)

        loading_bubble = ChatBubble(_tr("Thinking..."), is_user=False)
        ui["chat_list"].add_bubble(loading_bubble)
        ui["_streaming_bubble"] = loading_bubble

    def _retry_ai_message(self, chat_index, bubble):
        history = SETTINGS["ai_chats"][chat_index]["history"]
        idx = bubble.msg_index
        if idx < 0 or idx >= len(history) or history[idx]["role"] != "user":
            return
        user_content = history[idx]["content"]
        del history[idx:]
        history.append({"role": "user", "content": user_content})
        save_settings(SETTINGS)
        self._rebuild_chat_display(chat_index)
        self._send_ai_request(chat_index)

    def _rebuild_chat_display(self, chat_index):
        self.render_ai_chat_history(chat_index)

    def process_ai_actions(self, response, chat_index):
        search_match = re.search(r'\{+(?:SEARCH|search):\s*(.*?)\}+', response, re.DOTALL)
        if search_match:
            params_str = search_match.group(1).replace('\n', ' ').strip()
            tags = params_str
            sort = None
            page = 0
            if ',' in params_str:
                parts = [p.strip() for p in params_str.split(',')]
                tags = parts[0]
                for part in parts[1:]:
                    if part.startswith('sort='): sort = part.split('=', 1)[1]
                    elif part.startswith('page='):
                        try: page = int(part.split('=', 1)[1]) - 1
                        except: page = 0
            self.perform_ai_image_search(tags, chat_index, sort=sort, page=page)

        for match in re.finditer(r'\{+(?:SET|UPDATE_SETTING|update_setting|set):\s*([^}]+)\}+', response):
            inner = match.group(1).strip()
            if '=' not in inner:
                continue
            key = inner.split('=', 1)[0].strip()
            raw_val = inner.split('=', 1)[1].strip()

            if key not in SETTINGS:
                continue

            val = self._coerce_setting_value(key, raw_val)
            if val is not None:
                self._ai_pending_settings[key] = val

        if "{RANDOM_FAVORITE}" in response or "{random_favorite}" in response.lower():
            all_favs = []
            for cat in self.favorites.values(): all_favs.extend(cat.values())
            if all_favs:
                post = random.choice(all_favs)
                self.open_post_full(post)

        for match in re.finditer(r'\{+(?:OPEN_TAB|open_tab):\s*([^}]+)\}+', response):
            tab_name = match.group(1).strip().lower()
            tab_map = {"home": 0, "browser": 1, "favorites": 2, "downloads": 3, "hentai": 4, "manga": 5, "minigames": 6, "ai": 7}
            idx = tab_map.get(tab_name)
            if idx is not None:
                self.tabs.setCurrentIndex(idx)

        if "{HENTAI_RANDOM}" in response or "{hentai_random}" in response.lower():
            self.tabs.setCurrentWidget(self.hentai_tab)
            self.random_hentai()

        for match in re.finditer(r'\{+(?:HENTAI_SEARCH|hentai_search):\s*([^}]+)\}+', response):
            query = match.group(1).strip().strip('"\'')
            self._ai_hentai_search(query, chat_index)

        for match in re.finditer(r'\{+(?:MANGA_SEARCH|manga_search):\s*([^}]+)\}+', response):
            query = match.group(1).strip().strip('"\'')
            self._ai_manga_search(query, chat_index)

        for match in re.finditer(r'\{+(?:HENTAI_TRENDING|hentai_trending):\s*(\d*)\}+', response):
            count_str = match.group(1).strip()
            count = int(count_str) if count_str.isdigit() else 8
            self._ai_hentai_trending(count, chat_index)

        for match in re.finditer(r'\{+(?:DOWNLOAD|download):\s*([^}]+)\}+', response):
            inner = match.group(1).strip()
            tags = inner
            count = 5
            if ',' in inner:
                parts = [p.strip() for p in inner.split(',')]
                tags = parts[0]
                for part in parts[1:]:
                    if part.startswith('count='):
                        try: count = int(part.split('=', 1)[1])
                        except: pass
            self._ai_download_posts(tags, count, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_ADD|favorite_add):\s*([^}]+)\}+', response):
            inner = match.group(1).strip()
            category = "Uncategorized"
            count = 5
            tags = inner
            if '|' in inner:
                parts = [p.strip() for p in inner.split('|')]
                tags = parts[0]
                for part in parts[1:]:
                    if part.startswith('count='):
                        try: count = int(part.split('=', 1)[1])
                        except: pass
                    elif part.startswith('cat='):
                        category = part.split('=', 1)[1].strip()
            self._ai_favorite_add(tags, category, count, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_REMOVE|favorite_remove):\s*(\d+)\}+', response):
            post_id = match.group(1).strip()
            self._ai_favorite_remove(post_id, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_CREATE|favorite_create):\s*([^}]+)\}+', response):
            name = match.group(1).strip().strip('"\'')
            self._ai_favorite_create(name, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_RENAME|favorite_rename):\s*([^}]+)\}+', response):
            inner = match.group(1).strip()
            if ',' in inner:
                parts = [p.strip().strip('"\'') for p in inner.split(',', 1)]
                old_name, new_name = parts[0], parts[1]
                self._ai_favorite_rename(old_name, new_name, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_DELETE|favorite_delete):\s*([^}]+)\}+', response):
            name = match.group(1).strip().strip('"\'')
            self._ai_favorite_delete(name, chat_index)

        for match in re.finditer(r'\{+(?:FAVORITE_MERGE|favorite_merge):\s*([^}]+)\}+', response):
            inner = match.group(1).strip()
            if ',' in inner:
                parts = [p.strip().strip('"\'') for p in inner.split(',', 1)]
                source, target = parts[0], parts[1]
                self._ai_favorite_merge(source, target, chat_index)

        for match in re.finditer(r'\{+(?:CURATE|curate):\s*([^}]+)\}+', response):
            tags = match.group(1).strip()
            self._ai_curate_profile(tags, chat_index)

        similar_match = re.search(r'\{+(?:SHOW_SIMILAR|show_similar):\s*([^}]+)\}+', response)
        if similar_match:
            post_id = similar_match.group(1).strip()
            post = self._find_post_by_id_globally(post_id)
            if post:
                tags = post.get("tags", "")
                search_tags = " ".join(tags.split()[:5])
                self.perform_ai_image_search(search_tags, chat_index)

    def _coerce_setting_value(self, key, raw_val):
        raw_val = raw_val.strip().strip('"').strip("'")
        existing = SETTINGS.get(key)

        if existing is None:
            if raw_val.lower() in ("true", "false"):
                return raw_val.lower() == "true"
            try: return int(raw_val)
            except ValueError:
                try: return float(raw_val)
                except ValueError: return raw_val

        if isinstance(existing, bool):
            return raw_val.lower() in ("true", "1", "yes", "on")

        if isinstance(existing, int):
            try: return int(raw_val)
            except ValueError: return None

        if isinstance(existing, float):
            try: return float(raw_val)
            except ValueError: return None

        if isinstance(existing, list):
            if raw_val:
                return [s.strip() for s in raw_val.split(',') if s.strip()]
            return []

        if isinstance(existing, str):
            return raw_val

        return raw_val

    def _get_app_stats_for_ai(self):
        fav_count = sum(len(posts) for posts in self.favorites.values())
        down_count = len(self.downloads_data)
        active_sources = SETTINGS.get("enabled_sources", [])
        recent_searches = self.search_history[:10] if hasattr(self, 'search_history') else []
        last_post_info = None
        if hasattr(self, 'last_selected') and self.last_selected:
            last_post_info = {
                "id": self.last_selected.get("id"),
                "tags": self.last_selected.get("tags", ""),
                "rating": self.last_selected.get("rating", "unknown")
            }
        return {
            "favorites_count": fav_count,
            "downloads_count": down_count,
            "active_sources": active_sources,
            "current_theme": SETTINGS.get("active_theme", "Default"),
            "incognito_mode": SETTINGS.get("incognito_mode", False),
            "explicit_allowed": SETTINGS.get("allow_explicit", False),
            "recent_searches": recent_searches,
            "last_viewed_post": last_post_info
        }

    def _prepare_ai_system_prompt(self, preset):
        base_persona = preset.get("persona", "")
        stats = self._get_app_stats_for_ai()
        pref_tags = SETTINGS.get("preferred_tags", "").replace("\n", ", ")

        settable_keys = [
            "active_theme", "allow_explicit", "allow_loli_shota", "allow_bestiality", "allow_guro",
            "incognito_mode", "show_download_notification", "enable_recommendations",
            "grid_columns", "thumbnail_size", "auto_scale_grid", "potato_mode",
            "convert_gifs_to_webp",
            "window_mode", "window_size_preset", "custom_window_width", "custom_window_height",
            "preferred_tags", "blacklisted_tags",
            "posts_per_page", "cpu_limit", "ram_limit", "temp_cleanup_minutes",
            "language",
        ]
        settings_flat = "\n".join(
            f"  {k} = {SETTINGS.get(k, '???')} (type: {type(SETTINGS.get(k)).__name__})"
            for k in settable_keys
        )

        enabled = SETTINGS.get("enabled_sources", [])
        themes = ["Dark (Default)", "Light (Default)"] + list(self.custom_themes.keys())
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context = f"""
[APP_CONTEXT]
- Current time: {now}
- Favorites: {stats['favorites_count']} items in {len(self.favorites)} categories
- Downloads: {stats['downloads_count']} files
- Active Sources: {", ".join(enabled)}
- Available Themes: {", ".join(themes)}
- Current Theme: {stats['current_theme']}
- Preferred Tags: {pref_tags}
- Incognito: {stats['incognito_mode']}, NSFW: {stats['explicit_allowed']}

[SETTINGS_YOU_CAN_CHANGE]
{settings_flat}
  enabled_sources = {enabled} (type: list, comma-separated)

[COMMANDS - put these AFTER your response, they are hidden]
- Search images: {{SEARCH: tags, sort=random, page=1}}
- Change setting: {{SET: key=value}}
- Open a tab: {{OPEN_TAB: browser|hentai|manga|favorites|downloads|ai|home|minigames}}
- Search hentai: {{HENTAI_SEARCH: keyword}} — searches by title, tags, or any keyword. Use descriptive keywords (tags, genre, character names).
- Trending hentai: {{HENTAI_TRENDING: count}} — fetch currently popular hentai titles (omit count for default 8).
- Random hentai: {{HENTAI_RANDOM}}
- Search manga: {{MANGA_SEARCH: title}} — searches MangaDex by exact or partial title. Use the real manga title, not tags.
- Download posts: {{DOWNLOAD: tags, count=N}} — searches images by tags and downloads N of them.
- Favorite posts: {{FAVORITE_ADD: tags | count=N, cat=CategoryName}} — searches and favorites posts.
- Remove favorite: {{FAVORITE_REMOVE: post_id}}
- Create category: {{FAVORITE_CREATE: name}}
- Rename category: {{FAVORITE_RENAME: old, new}}
- Delete category: {{FAVORITE_DELETE: name}}
- Merge categories: {{FAVORITE_MERGE: source, target}}
- Curate profile: {{CURATE: tags}} — sets preferred tags for autosuggest based on user's taste.
- Random favorite: {{RANDOM_FAVORITE}}
- Show similar: {{SHOW_SIMILAR: post_id}}
- Sort options: random, score, id_desc, id_asc
- For videos/GIFs add "video" or "animated" to search tags
- You are an expert in anime, manga, and booru imageboards
- Search the correct terms. If you don't know what content exists, use {{HENTAI_TRENDING:}} to discover available hentai first.
- NEVER show command syntax in your visible text. Use them only after your message.
"""
        return f"{base_persona}\n\n{context}"

    def _find_post_by_id_globally(self, post_id):
        if hasattr(self, 'posts'):
            for p in self.posts:
                if p.get('id') == post_id: return p
        for cat in self.favorites.values():
            if post_id in cat: return cat[post_id]
        for p in self.downloads_data.values():
            if p.get('id') == post_id: return p
        return None

    def _ai_hentai_search(self, query, chat_index):
        ui = self.ai_chat_ui[chat_index]
        status = ChatBubble(_tr("Searching hentai: {query}...").format(query=query), is_user=False)
        ui["chat_list"].add_bubble(status)

        def on_results(results, err):
            if err:
                ui["chat_list"].add_bubble(ChatBubble(_tr("Hentai search error: {e}").format(e=err), is_user=False))
                return
            refs = []
            for item in (results or []):
                if len(refs) >= 6:
                    break
                post = self._adapt_hhaven_post(item)
                if not post:
                    continue
                name = post["hentai_title"]
                cover = post["preview_url"]
                ref_data = {"type": "hentai", "slug": post["hentai_slug"], "post": post, "source_url": post.get("source_post_url", ""), "name": name, "cover": cover}
                refs.append(ref_data)
                pixmap = QPixmap()
                if cover:
                    try:
                        img_data = requests.get(cover, timeout=10).content
                        pixmap.loadFromData(img_data)
                    except Exception:
                        pass
                card = ChatRefCard(name, pixmap if not pixmap.isNull() else None, ref_data)
                card.clicked.connect(lambda rd=ref_data: self._on_ai_ref_clicked(rd))
                ui["chat_list"].add_bubble(card)
            if refs:
                history = SETTINGS["ai_chats"][chat_index]["history"]
                for msg in reversed(history):
                    if msg["role"] == "assistant":
                        msg["hentai_results"] = refs
                        break
                save_settings(SETTINGS)
            if not refs:
                ui["chat_list"].add_bubble(ChatBubble(_tr("No hentai found."), is_user=False))

        worker = ApiWorker(_do_hhaven_fetch, "search", 0, 6, query)
        worker.signals.finished.connect(on_results)
        self.threadpool.start(worker)

    def _ai_manga_search(self, query, chat_index):
        ui = self.ai_chat_ui[chat_index]
        status = ChatBubble(_tr("Searching manga: {query}...").format(query=query), is_user=False)
        ui["chat_list"].add_bubble(status)

        def do_manga_search(query, limit=6):
            results = []
            try:
                params = {"limit": limit, "offset": 0, "includes[]": ["cover_art"], "title": query, "order[relevance]": "desc"}
                resp = requests.get("https://api.mangadex.org/manga", params=params, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                for item in payload.get("data", []) or []:
                    manga_id = item.get("id")
                    attrs = item.get("attributes") or {}
                    titles = attrs.get("title") or {}
                    title = titles.get("en") or next(iter(titles.values()), manga_id)
                    cover_rel = [r for r in (item.get("relationships") or []) if r.get("type") == "cover_art"]
                    cover_url = None
                    if cover_rel:
                        fn = (cover_rel[0].get("attributes") or {}).get("fileName")
                        if fn:
                            cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{fn}"
                    results.append({"id": manga_id, "title": title, "url": f"https://mangadex.org/title/{manga_id}", "cover": cover_url})
                return results
            except Exception:
                return results

        def on_results(results, err):
            if err:
                ui["chat_list"].add_bubble(ChatBubble(_tr("Manga search error: {e}").format(e=err), is_user=False))
                return
            refs = []
            for item in (results or []):
                if len(refs) >= 6:
                    break
                title = item.get("title", "Untitled")
                cover = item.get("cover")
                ref_data = {"type": "manga", "title": title, "url": item.get("url", ""), "manga_id": item.get("id"), "cover": cover}
                refs.append(ref_data)
                pixmap = QPixmap()
                if cover:
                    try:
                        img_data = requests.get(cover, timeout=10).content
                        pixmap.loadFromData(img_data)
                    except Exception:
                        pass
                card = ChatRefCard(title, pixmap if not pixmap.isNull() else None, ref_data)
                card.clicked.connect(lambda rd=ref_data: self._on_ai_ref_clicked(rd))
                ui["chat_list"].add_bubble(card)
            if refs:
                history = SETTINGS["ai_chats"][chat_index]["history"]
                for msg in reversed(history):
                    if msg["role"] == "assistant":
                        msg["manga_results"] = refs
                        break
                save_settings(SETTINGS)
            if not refs:
                ui["chat_list"].add_bubble(ChatBubble(_tr("No manga found."), is_user=False))

        worker = ApiWorker(do_manga_search, query, 6)
        worker.signals.finished.connect(on_results)
        self.threadpool.start(worker)

    def _ai_hentai_trending(self, count, chat_index):
        ui = self.ai_chat_ui[chat_index]
        status = ChatBubble(_tr("Fetching trending hentai..."), is_user=False)
        ui["chat_list"].add_bubble(status)

        def on_results(results, err):
            if err:
                ui["chat_list"].add_bubble(ChatBubble(_tr("Error: {e}").format(e=err), is_user=False))
                return
            names = []
            for item in (results or []):
                if not isinstance(item, dict):
                    continue
                title = item.get("title")
                if isinstance(title, dict):
                    title = title.get("rendered") or title.get("raw") or ""
                title = re.sub(r"<[^>]+>", "", str(title or "")).strip()
                if title:
                    names.append(title)
                if len(names) >= count:
                    break
            if names:
                msg = _tr("Trending hentai: {list}").format(list=", ".join(names))
            else:
                msg = _tr("No trending hentai found.")
            ui["chat_list"].add_bubble(ChatBubble(msg, is_user=False))

        worker = ApiWorker(_do_hhaven_fetch, "trending", 0, count)
        worker.signals.finished.connect(on_results)
        self.threadpool.start(worker)

    def _ai_download_posts(self, tags, count, chat_index):
        ui = self.ai_chat_ui[chat_index]
        ui["chat_list"].add_bubble(ChatBubble(_tr("Searching for images to download: {tags}...").format(tags=tags), is_user=False))
        from snekbooru.api.booru import fetch_multiple_sources
        from snekbooru.core.downloader import download_media

        def do_search(tags, count):
            detected_sources = None
            from snekbooru.api.booru import detect_source_from_query
            try:
                detected_sources = detect_source_from_query(tags)
            except Exception:
                detected_sources = None
            posts, _ = fetch_multiple_sources(detected_sources, tags, count + 5, 0, self.custom_boorus)
            return posts[:count]

        def on_search(data, err):
            if err:
                ui["chat_list"].add_bubble(ChatBubble(_tr("Download search error: {e}").format(e=err), is_user=False))
                return
            downloaded = 0
            errors = 0
            for post in (data or []):
                try:
                    success, msg = download_media(post, self)
                    if success:
                        downloaded += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1
                if downloaded >= count:
                    break
            if downloaded:
                self.refresh_downloads_grid()
            ui["chat_list"].add_bubble(ChatBubble(
                _tr("Downloaded {ok} posts{err}.").format(ok=downloaded, err=f" ({errors} failed)" if errors else ""),
                is_user=False
            ))

        worker = ApiWorker(do_search, tags, count)
        worker.signals.finished.connect(on_search)
        self.threadpool.start(worker)

    def _ai_favorite_add(self, tags, category, count, chat_index):
        ui = self.ai_chat_ui[chat_index]
        ui["chat_list"].add_bubble(ChatBubble(_tr("Searching to favorite: {tags}...").format(tags=tags), is_user=False))
        from snekbooru.api.booru import fetch_multiple_sources

        if category not in self.favorites:
            self.favorites[category] = {}
            save_favorites(self.favorites)

        def do_search(tags, count):
            from snekbooru.api.booru import detect_source_from_query
            detected = None
            try: detected = detect_source_from_query(tags)
            except: pass
            posts, _ = fetch_multiple_sources(detected, tags, count + 5, 0, self.custom_boorus)
            return posts[:count]

        def on_search(data, err):
            if err:
                ui["chat_list"].add_bubble(ChatBubble(_tr("Favorite search error: {e}").format(e=err), is_user=False))
                return
            added = 0
            for post in (data or []):
                pid = post.get("id")
                if pid and pid not in self.favorites.get(category, {}):
                    self.favorites[category][pid] = self._sanitize_post_for_storage(post)
                    added += 1
            if added:
                save_favorites(self.favorites)
                self.populate_favorite_categories()
            ui["chat_list"].add_bubble(ChatBubble(
                _tr("Favorited {n} posts in '{cat}'.").format(n=added, cat=category), is_user=False
            ))

        worker = ApiWorker(do_search, tags, count)
        worker.signals.finished.connect(on_search)
        self.threadpool.start(worker)

    def _ai_favorite_remove(self, post_id, chat_index):
        ui = self.ai_chat_ui[chat_index]
        removed = False
        for cat in list(self.favorites.keys()):
            if post_id in self.favorites[cat]:
                del self.favorites[cat][post_id]
                removed = True
                break
        if removed:
            save_favorites(self.favorites)
            self.populate_favorite_categories()
            ui["chat_list"].add_bubble(ChatBubble(_tr("Removed post {id} from favorites.").format(id=post_id), is_user=False))
        else:
            ui["chat_list"].add_bubble(ChatBubble(_tr("Post {id} not found in favorites.").format(id=post_id), is_user=False))

    def _ai_favorite_create(self, name, chat_index):
        ui = self.ai_chat_ui[chat_index]
        if name in self.favorites:
            ui["chat_list"].add_bubble(ChatBubble(_tr("Category '{name}' already exists.").format(name=name), is_user=False))
            return
        self.favorites[name] = {}
        save_favorites(self.favorites)
        self.populate_favorite_categories()
        ui["chat_list"].add_bubble(ChatBubble(_tr("Created favorite category '{name}'.").format(name=name), is_user=False))

    def _ai_favorite_rename(self, old_name, new_name, chat_index):
        ui = self.ai_chat_ui[chat_index]
        if old_name not in self.favorites:
            ui["chat_list"].add_bubble(ChatBubble(_tr("Category '{name}' not found.").format(name=old_name), is_user=False))
            return
        if new_name in self.favorites:
            ui["chat_list"].add_bubble(ChatBubble(_tr("Category '{name}' already exists.").format(name=new_name), is_user=False))
            return
        self.favorites[new_name] = self.favorites.pop(old_name)
        save_favorites(self.favorites)
        self.populate_favorite_categories()
        ui["chat_list"].add_bubble(ChatBubble(_tr("Renamed '{old}' to '{new}'.").format(old=old_name, new=new_name), is_user=False))

    def _ai_favorite_delete(self, name, chat_index):
        ui = self.ai_chat_ui[chat_index]
        if name not in self.favorites or name == "Uncategorized":
            ui["chat_list"].add_bubble(ChatBubble(_tr("Cannot delete '{name}'.").format(name=name), is_user=False))
            return
        posts_to_move = self.favorites.pop(name)
        self.favorites["Uncategorized"].update(posts_to_move)
        save_favorites(self.favorites)
        self.populate_favorite_categories()
        ui["chat_list"].add_bubble(ChatBubble(_tr("Deleted '{name}', posts moved to Uncategorized.").format(name=name), is_user=False))

    def _ai_favorite_merge(self, source, target, chat_index):
        ui = self.ai_chat_ui[chat_index]
        if source not in self.favorites or target not in self.favorites:
            ui["chat_list"].add_bubble(ChatBubble(_tr("One or both categories not found."), is_user=False))
            return
        self.favorites[target].update(self.favorites.pop(source))
        save_favorites(self.favorites)
        self.populate_favorite_categories()
        ui["chat_list"].add_bubble(ChatBubble(_tr("Merged '{src}' into '{tgt}'.").format(src=source, tgt=target), is_user=False))

    def _ai_curate_profile(self, tags, chat_index):
        ui = self.ai_chat_ui[chat_index]
        SETTINGS["preferred_tags"] = tags
        save_settings(SETTINGS)
        self.tag_profile["ai_curated"] = tags
        save_tag_profile(self.tag_profile)
        ui["chat_list"].add_bubble(ChatBubble(_tr("Profile curated with: {tags}").format(tags=tags), is_user=False))

    def _on_ai_ref_clicked(self, ref_data):
        rtype = ref_data.get("type", "")
        if rtype == "hentai":
            post = ref_data.get("post")
            if post:
                self.tabs.setCurrentWidget(self.hentai_tab)
                self.hentai_search_input.setText(ref_data.get("name", ""))
                self.search_hentai()
        elif rtype == "manga":
            title = ref_data.get("title", "")
            if title:
                self.tabs.setCurrentWidget(self.manga_tab)
                self.manga_search_input.setText(title)
                self.apply_manga_filter()

    def perform_ai_image_search(self, tags, chat_index, is_fallback=False, original_tags=None, retry_count=0, sort=None, page=0):
        ui = self.ai_chat_ui[chat_index]

        search_tags = tags
        if sort == "random": search_tags += " sort:random"
        elif sort == "score": search_tags += " sort:score"
        elif sort == "id_asc": search_tags += " sort:id:asc"

        if not is_fallback:
            status = ChatBubble(_tr("Searching: {tags}...").format(tags=tags), is_user=False)
            ui["chat_list"].add_bubble(status)
            original_tags = tags

        tags_lower = tags.lower()
        explicit_keywords = [
            'porn', 'hentai', 'xxx', 'nsfw', 'explicit', 'adult',
            'nude', 'naked', 'sex', 'erotic', 'horny', 'tentacle',
            'rape', 'yaoi', 'yuri', 'futanari', 'futa', 'incest',
            'anal', 'cum', 'cock', 'pussy', 'dick', 'dildo', 'vibrator'
        ]

        has_explicit_request = any(keyword in tags_lower for keyword in explicit_keywords)

        search_tags = tags
        if not has_explicit_request and 'rating:' not in tags_lower:
            search_tags = f"{tags} rating:safe" if tags.strip() else "rating:safe"

        detected_sources = detect_source_from_query(tags)

        media_preference = None
        if any(ext in tags_lower for ext in ['gif', 'video', 'webm', 'mp4', 'animated']):
            media_preference = 'video'
        elif any(ext in tags_lower for ext in ['png', 'jpg', 'jpeg', 'image', 'static']):
            media_preference = 'image'

        result_limit = 6
        worker = ApiWorker(fetch_multiple_sources, detected_sources, search_tags, result_limit, page, self.custom_boorus)
        worker.signals.finished.connect(lambda data, err: self.on_ai_search_results(data, err, chat_index, media_preference, original_tags, retry_count))
        self.threadpool.start(worker)

    def reset_ai_cooldown(self, chat_index):
        self.ai_can_send = True
        self._current_ai_worker = None
        if chat_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[chat_index]
            ui["input_area"].setEnabled(True)
            ui["send_btn"].setEnabled(True)
            ui["stop_btn"].setVisible(False)
            ui["input_area"].setFocus()

    def on_ai_error(self, error_message):
        active_index = self.ai_chat_tabs.currentIndex()
        if active_index >= 0 and active_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[active_index]
            error_bubble = ChatBubble(_tr("Error: {error}").format(error=error_message), is_user=False)
            ui["chat_list"].add_bubble(error_bubble)
            ui.pop("_streaming_bubble", None)
            self.reset_ai_cooldown(active_index)

    def on_ai_search_results(self, data, err, chat_index, media_preference=None, original_tags=None, retry_count=0):
        if chat_index not in self.ai_chat_ui:
            return
        ui = self.ai_chat_ui[chat_index]
        if err:
            status_bubble = ChatBubble(_tr("Search Error: {error}").format(error=err), is_user=False)
            ui["chat_list"].add_bubble(status_bubble)
            return

        posts, _ = data
        if not posts:
            if retry_count < 1 and original_tags:
                fallback = original_tags.replace(" different", "").replace(" another", "").replace(" alt ", " ").strip()
                if fallback and fallback != original_tags:
                    self.perform_ai_image_search(fallback, chat_index, is_fallback=True, original_tags=original_tags, retry_count=retry_count+1)
                    return
            status_bubble = ChatBubble(_tr("No images found."), is_user=False)
            ui["chat_list"].add_bubble(status_bubble)
            return

        result_bubble = ChatBubble("", is_user=False)
        for post in posts[:6]:
            self.ai_search_results[post['id']] = post
            preview = post.get('preview_url')
            file_ext = post.get('file_ext', '').lower()
            is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
            if preview:
                worker = ImageWorker(preview, post)
                worker.signals.finished.connect(lambda pix, p=post, b=result_bubble: self._on_ai_search_image(pix, p, b))
                self.threadpool.start(worker)
        ui["chat_list"].add_bubble(result_bubble)

    def _on_ai_search_image(self, pixmap, post, bubble):
        file_ext = post.get('file_ext', '').lower()
        is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
        if pixmap and not pixmap.isNull():
            chat_index = self.ai_chat_tabs.currentIndex()
            if chat_index in self.ai_chat_ui:
                res_data = {'post_id': post['id'], 'image_data': None, 'is_video': is_video}
                img_bubble = ChatImageBubble(pixmap, res_data)
                img_bubble.clicked.connect(lambda pd=res_data: self._open_ai_search_result(pd))
                self.ai_chat_ui[chat_index]["chat_list"].add_bubble(img_bubble)

        history = SETTINGS["ai_chats"][self.ai_chat_tabs.currentIndex()].get("history", [])
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        image_data = base64.b64encode(buffer.data()).decode()
        for msg in reversed(history):
            if msg["role"] == "assistant":
                if "search_results" not in msg:
                    msg["search_results"] = []
                res_data = {'post_id': post['id'], 'image_data': image_data, 'is_video': is_video}
                msg["search_results"].append(res_data)
                break
        save_settings(SETTINGS)

    def on_chat_anchor_clicked(self, url):
        url_str = url.toString()
        if url_str.startswith("post:"):
            post_id = url_str.split(":")[1]
            post = self.ai_search_results.get(post_id)
            if post:
                self.open_ai_post_viewer(post)
            else:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not load post details."))
        else:
            webbrowser.open(url_str)

    def open_ai_post_viewer(self, post):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton
        from snekbooru.ui.dialogs import CustomTitleBar
        
        dialog = QDialog(self)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.FramelessWindowHint)  
        dialog.setGeometry(100, 100, 900, 700)
        dialog.setModal(False)  
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        title_bar = CustomTitleBar(dialog, _tr("Post Viewer"), has_icon=False)
        main_layout.addWidget(title_bar)
        layout = QVBoxLayout()
        main_layout.addLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        media_widget = QWidget()
        media_layout = QVBoxLayout(media_widget)
        
        file_url = post.get('file_url')
        preview_url = post.get('preview_url')
        file_ext = post.get('file_ext', '').lower()
        is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
        
        if is_video and file_url:
            video_info = QLabel(f"<b>Video Preview</b><br>Format: {file_ext.upper()}<br><a href='{file_url}'>Click here to view full video</a>")
            video_info.setOpenExternalLinks(True)
            media_layout.addWidget(video_info)
            
            if preview_url:
                try:
                    response = requests.get(preview_url, headers=get_media_headers(preview_url), timeout=10)
                    response.raise_for_status()
                    pix = QPixmap()
                    pix.loadFromData(response.content)
                    if not pix.isNull():
                        thumb_label = QLabel()
                        thumb_label.setPixmap(pix.scaledToWidth(600, Qt.SmoothTransformation))
                        thumb_label.setAlignment(Qt.AlignCenter)
                        media_layout.addWidget(thumb_label)
                except Exception as e:
                    media_layout.addWidget(QLabel(f"<i>Could not load preview: {str(e)}</i>"))
        else:
            if preview_url or file_url:
                url_to_load = preview_url or file_url
                try:
                    response = requests.get(url_to_load, headers=get_media_headers(url_to_load), timeout=10)
                    pix = QPixmap()
                    pix.loadFromData(response.content)
                    
                    if not pix.isNull():
                        img_label = QLabel()
                        img_label.setPixmap(pix.scaledToWidth(600, Qt.SmoothTransformation))
                        img_label.setAlignment(Qt.AlignCenter)
                        media_layout.addWidget(img_label)
                except Exception as e:
                    media_layout.addWidget(QLabel(f"<i>Could not load image: {str(e)}</i>"))
        
        media_layout.addStretch()
        scroll.setWidget(media_widget)
        layout.addWidget(scroll)
        info_text = f"<b>Post ID:</b> {post.get('id')}<br>"
        info_text += f"<b>Rating:</b> {post.get('rating', 'Unknown')}<br>"
        info_text += f"<b>Score:</b> {post.get('score', 'N/A')}<br>"
        if post.get('tags'):
            info_text += f"<b>Tags:</b> {post.get('tags', '')[:200]}..."
        
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        button_layout = QHBoxLayout()
        
        open_full_btn = QPushButton(qta.icon('fa5s.expand'), _tr(" Open in Full Viewer"))
        open_full_btn.clicked.connect(lambda: (dialog.close(), self.open_post_full(post)))
        
        download_btn = QPushButton(qta.icon('fa5s.download'), _tr(" Download"))
        download_btn.clicked.connect(lambda: (dialog.close(), self.download_post(post)))
        
        fav_btn = QPushButton(qta.icon('fa5s.heart'), _tr(" Favorite"))
        fav_btn.clicked.connect(lambda: (dialog.close(), self.toggle_favorite(post)))
        
        close_btn = QPushButton(qta.icon('fa5s.times'), _tr(" Close"))
        close_btn.clicked.connect(lambda: self._close_dialog_and_refocus(dialog))
        
        button_layout.addWidget(open_full_btn)
        button_layout.addWidget(download_btn)
        button_layout.addWidget(fav_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        dialog.show()  
        
        if not hasattr(self, '_open_dialogs'):
            self._open_dialogs = []
        self._open_dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._open_dialogs.remove(dialog) if dialog in self._open_dialogs else None)

    def _close_dialog_and_refocus(self, dialog):
        dialog.close()
        active_index = self.ai_chat_tabs.currentIndex()
        if active_index >= 0:
            self._rebuild_chat_display(active_index)
            if active_index in self.ai_chat_ui:
                self.ai_chat_ui[active_index]["history_browser"].setFocus()

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self.clear_layout(item.layout())

    def clear_grid(self, grid_layout):
        self.clear_layout(grid_layout)

    def populate_grid(self, grid_layout, posts, widget_map, click_handler, is_local=False, viewport_width=1000):
        if SETTINGS.get("auto_scale_grid", False):
            grid_layout.parentWidget().setFixedWidth(viewport_width)
            target_thumb_size = SETTINGS.get("thumbnail_size", 150)
            spacing = grid_layout.spacing() 

            cols = max(2, int((viewport_width + spacing) / (target_thumb_size + spacing)))

            thumb_size = int((viewport_width - (cols - 1) * spacing) / cols)
        else:
            cols = SETTINGS.get("grid_columns", 5)
            thumb_size = SETTINGS.get("thumbnail_size", 150)

        posts = [p for p in posts if isinstance(p, dict)]

        for i, post in enumerate(posts):
            row, col = divmod(i, cols)
            thumb = ThumbnailWidget(post, thumb_size, self.favorites)
            thumb.clicked.connect(click_handler)
            thumb.doubleClicked.connect(self.open_post_full)
            thumb.selectionToggled.connect(self.toggle_bulk_selection)
            thumb.customContextMenuRequested.connect(lambda pos, p=post: self.show_thumbnail_context_menu(p, pos))
            
            grid_layout.addWidget(thumb, row, col)
            post_id = post.get('id')
            if not post_id:
                post_id = post.get('hash') or f"post_{i}"
                post['id'] = post_id 
                
            widget_map[post_id] = thumb

            thumb_loaded = False
            if is_local:
                local_thumb = post.get("local_thumbnail_path")
                if local_thumb and os.path.exists(local_thumb):
                    pix = QPixmap(local_thumb)
                    thumb.set_pixmap(pix)
                    thumb_loaded = True
                else:
                    local_path = post.get("local_path")
                    file_ext = post.get("file_ext", "").lower()
                    if local_path and os.path.exists(local_path) and file_ext in ["jpg", "jpeg", "png", "webp", "bmp", "gif"]:
                        pix = QPixmap(local_path)
                        thumb.set_pixmap(pix)
                        thumb_loaded = True

            if not thumb_loaded:
                thumb_url = post.get("preview_url")
                if thumb_url:
                    if os.path.exists(thumb_url):
                        pix = QPixmap(thumb_url)
                        thumb.set_pixmap(pix)
                    else:
                        worker = ImageWorker(thumb_url, post)
                        worker.signals.finished.connect(self.on_thumbnail_loaded)
                        self.threadpool.start(worker)

    def on_thumbnail_loaded(self, pixmap, post):
        post_id = post.get('id')
        widget = self.post_to_widget_map.get(post_id) or \
                 self.fav_post_to_widget_map.get(post_id) or \
                 self.reco_post_to_widget_map.get(post_id) or \
                 self.hentai_post_to_widget_map.get(post_id) or \
                 self.downloads_post_to_widget_map.get(post_id)
        
        if widget:
            widget.set_pixmap(pixmap)

    def on_manga_thumb_loaded(self, pixmap, post_data):
        widget = post_data.get("widget")
        url = post_data.get("url")
        if url and not pixmap.isNull():
            self.manga_thumb_cache[url] = pixmap
        if not widget or pixmap.isNull():
            return
        try:
            if hasattr(widget, "set_thumbnail"):
                widget.set_thumbnail(pixmap)
            else:
                widget.thumb_label.setPixmap(pixmap.scaled(widget.thumb_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except RuntimeError:
            return
        except Exception:
            return

    def show_thumbnail_context_menu(self, post, pos):
        menu = QMenu()
        active_tab = self.tabs.currentWidget()
        is_favorited = find_post_in_favorites(post.get('id'), self.favorites) is not None
        fav_text = _tr("Remove from Favorites") if is_favorited else _tr("Add to Favorites")
        fav_action = menu.addAction(qta.icon('fa5s.star', color='yellow' if is_favorited else None), fav_text)

        open_in_browser_action = menu.addAction(qta.icon('fa5s.external-link-alt'), _tr("Open Post in Browser"))
        menu.addSeparator()
        copy_tags_action = menu.addAction(qta.icon('fa5s.tags'), _tr("Copy Tags"))
        copy_image_url_action = menu.addAction(qta.icon('fa5s.link'), _tr("Copy Image URL"))

        if active_tab == self.browser_tab:
            menu.addSeparator()
            download_action = menu.addAction(qta.icon('fa5s.download'), _tr("Download"))
            reverse_search_action = menu.addAction(qta.icon('fa5s.search'), _tr("Reverse Image Search"))

        elif active_tab == self.favorites_tab:
            menu.addSeparator()
            move_to_category_menu = menu.addMenu(_tr("Move to Category..."))
            for category_name in sorted(self.favorites.keys()):
                cat_action = move_to_category_menu.addAction(category_name)
                cat_action.setData(category_name)

        elif active_tab == self.downloads_tab:
            menu.addSeparator()
            open_in_viewer_action = menu.addAction(qta.icon('fa5s.expand'), _tr("Open in Viewer"))
            open_file_action = menu.addAction(qta.icon('fa5s.folder-open'), _tr("Open File Location"))
            copy_path_action = menu.addAction(qta.icon('fa5s.copy'), _tr("Copy File Path"))
            menu.addSeparator()
            delete_from_disk_action = menu.addAction(qta.icon('fa5s.trash-alt', color='red'), _tr("Delete from Disk"))

        chosen_action = menu.exec_(QCursor.pos())
        if chosen_action is None:
            return

        if chosen_action == fav_action:
            self.toggle_favorite(post)
        elif chosen_action == open_in_browser_action:
            if post.get("source_post_url"):
                webbrowser.open(post.get("source_post_url"))
        elif chosen_action == copy_tags_action:
            QApplication.clipboard().setText(post.get("tags", ""))
        elif chosen_action == copy_image_url_action:
            QApplication.clipboard().setText(post.get("file_url", ""))

        elif active_tab == self.browser_tab:
            if chosen_action == download_action:
                from snekbooru.core.downloader import download_media
                self.download_post(post)
            elif chosen_action == reverse_search_action:
                self.last_selected = post
                self.reverse_search_selected()

        elif active_tab == self.favorites_tab:
            if chosen_action and chosen_action.parent() == move_to_category_menu:
                target_category = chosen_action.data()
                current_category = find_post_in_favorites(post.get('id'), self.favorites)
                if current_category and current_category != target_category:
                    post_data = self.favorites[current_category].pop(post.get('id'))
                    self.favorites[target_category][post.get('id')] = post_data
                    save_favorites(self.favorites)
                    self.refresh_favorites_grid()

        elif active_tab == self.downloads_tab:
            if chosen_action == open_in_viewer_action:
                self.open_post_full(post)
            elif chosen_action == open_file_action:
                file_path = post.get("local_path")
                if file_path:
                    from PyQt5.QtGui import QDesktopServices
                    from PyQt5.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))
            elif chosen_action == copy_path_action:
                QApplication.clipboard().setText(post.get("local_path", ""))
            elif chosen_action == delete_from_disk_action:
                reply = QMessageBox.question(self, _tr("Confirm Delete"),
                                             _tr("Are you sure you want to permanently delete this file from your disk?\n\n{path}").format(path=post.get("local_path")),
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    file_hash = get_file_hash(post)
                    if file_hash in self.downloads_data:
                        del self.downloads_data[file_hash]
                        save_downloads_data(self.downloads_data)
                    try:
                        if os.path.exists(post.get("local_path", "")):
                            os.remove(post.get("local_path"))
                        if os.path.exists(post.get("local_thumbnail_path", "")):
                            os.remove(post.get("local_thumbnail_path"))
                    except OSError as e:
                        QMessageBox.warning(self, _tr("Delete Error"), str(e))
                    self.refresh_downloads_grid()

    def format_post_info(self, post):
        if not post: return ""
        tags = post.get('tags', '')
        return (
            f"ID: {post.get('id')}\n"
            f"Rating: {post.get('rating')}\n"
            f"Score: {post.get('score')}\n"
            f"Source: {post.get('source_post_url')}\n\n"
            f"Tags:\n{tags}"
        )

    def _lazy_load_mikubooru_tags(self, post):
        try:
            source_url = post.get("source_post_url", "")
        except AttributeError:
            return
        if "booru.funmaker.moe" not in source_url:
            return
        existing_tags = post.get("tags", "")
        if isinstance(existing_tags, str) and existing_tags.strip():
            return
        if post.get("_tags_loading"):
            return
        post["_tags_loading"] = True

        pid = post.get("id")
        if not pid:
            return

        def _fetch():
            try:
                import requests as _r
                resp = _r.get(
                    f"https://booru.funmaker.moe/api/post/{pid}",
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                resp.raise_for_status()
                detail = resp.json()
                tags_obj = detail.get("tags", {})
                if isinstance(tags_obj, dict):
                    return " ".join(tags_obj.keys()), None
                return "", None
            except Exception as e:
                return None, str(e)

        worker = ApiWorker(_fetch)
        def on_done(data, err):
            post["_tags_loading"] = False
            if data and not err:
                post["tags"] = data
                if self.last_selected is post:
                    self.info.setPlainText(self.format_post_info(post))
        worker.signals.finished.connect(on_done)
        self.threadpool.start(worker)

    def start_new_search(self):
        self.pid = 0
        self.search()

    def search(self):
        tags = self.search_input.text().strip()
        if self.include_pref.isChecked():
            pref_tags = SETTINGS.get("preferred_tags", "").split()
            tags = " ".join(pref_tags) + " " + tags

        if not self.is_incognito_window and SETTINGS.get("enable_recommendations", True) and hasattr(self, 'persona') and self.persona is not None:
            try:
                from snekbooru.common.constants import BORING_TAGS
                from snekbooru.core.persona import top_affinity_tags
                exclude = set(BORING_TAGS)
                exclude.update(SETTINGS.get("blacklisted_tags", "").split())
                persona_tags = top_affinity_tags(self.persona, limit=8, exclude=exclude)
                existing = set(tags.split())
                soft = [f"~{t}" for t in persona_tags if t not in existing and f"~{t}" not in tags]
                if soft:
                    tags = (tags + " " + " ".join(soft)).strip()
            except Exception as e:
                print(f"Error blending persona into search: {e}")

        if not SETTINGS.get("allow_explicit", False) and "rating:" not in tags:
            tags += " rating:safe"

        self.add_to_search_history(self.search_input.text().strip())
        self.fetch_posts(tags.strip())

    def fetch_posts(self, tags):
        self.status.setText(_tr("Loading..."))
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        
        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
        worker = ApiWorker(fetch_multiple_sources, enabled_sources, tags, self.limit.value(), self.pid, self.custom_boorus)
        worker.signals.finished.connect(self.on_posts_loaded)
        self.threadpool.start(worker)

    def on_posts_loaded(self, data, err):
        from snekbooru.api.booru import filter_posts_by_blacklist
        
        self.progress.setVisible(False)
        self.clear_grid(self.grid)
        self.post_to_widget_map.clear()
        self.selected_for_bulk.clear()
        self.update_bulk_status()

        if err:
            self.status.setText(_tr("Error: {error}").format(error=err))
            return

        posts, total_count = data
        blacklisted_tags = SETTINGS.get("blacklisted_tags", "").split()
        if not SETTINGS.get("allow_loli_shota", False):
            blacklisted_tags.extend(["loli", "shota"])
        if not SETTINGS.get("allow_bestiality", False):
            blacklisted_tags.append("bestiality")
        if not SETTINGS.get("allow_guro", False):
            blacklisted_tags.append("guro")
        
        posts = filter_posts_by_blacklist(posts, blacklisted_tags)

        self.posts = posts
        self.id_to_post_map = {p['id']: p for p in posts}
        
        self.populate_grid(self.grid, self.posts, self.post_to_widget_map, self.on_thumbnail_clicked, viewport_width=self.scroll.viewport().width())
        
        self.status.setText(_tr("Loaded {count} posts.").format(count=len(posts)))
        self.page_input.setText(str(self.pid + 1))
        
        if total_count > 0:
            total_pages = (total_count + self.limit.value() - 1) // self.limit.value()
            self.page_count_label.setText(_tr("Page {current} of {total}").format(current=self.pid + 1, total=total_pages))
        else:
            self.page_count_label.setText("")

    def on_thumbnail_clicked(self, post, widget):
        self.info.setPlainText(self.format_post_info(post))
        self.last_selected = post
        self.update_inspector_fav_button(post)
        self._lazy_load_mikubooru_tags(post)
        self._record_browse_open(post)

    def _record_browse_open(self, post):
        if not post or getattr(self, 'is_incognito_window', False):
            return
        if not hasattr(self, 'persona') or self.persona is None:
            return
        try:
            category = find_post_in_favorites(post.get('id'), self.favorites)
            active_tab = self.tabs.currentWidget()
            context = 'browser'
            if active_tab == self.favorites_tab:
                context = 'favorites'
            elif active_tab == self.hentai_tab:
                context = 'hentai'
            elif active_tab == self.manga_tab:
                context = 'manga'
            record_post_open(self.persona, post, context=context, category=category, dwell=0.0)
            self._schedule_persona_save()
        except Exception as e:
            print(f"Error recording browse open: {e}")

    def next_page(self):
        self.pid += 1
        self.search() 

    def prev_page(self):
        if self.pid > 0:
            self.pid -= 1
            self.search() 

    def go_to_page(self):
        try:
            page = int(self.page_input.text())
            if page > 0:
                self.pid = page - 1
                self.search()
        except ValueError:
            pass 

    def random_post(self):
        self.status.setText(_tr("Fetching random post..."))
        tags = self.search_input.text().strip()
        worker = ApiWorker(danbooru_random, tags)
        worker.signals.finished.connect(self.on_random_post_loaded)
        self.threadpool.start(worker)

    def on_random_post_loaded(self, post, err):
        if err:
            self.status.setText(_tr("Error fetching random post."))
            return
        self.clear_grid(self.grid)
        self.post_to_widget_map.clear()
        self.selected_for_bulk.clear()
        self.update_bulk_status()

        self.posts = [post]
        self.id_to_post_map = {p['id']: p for p in self.posts}
        self.populate_grid(self.grid, self.posts, self.post_to_widget_map, self.on_thumbnail_clicked)
        
        self.status.setText(_tr("Loaded 1 random post."))
        self.page_input.setText("1")
        self.page_count_label.setText(_tr("Page 1 of 1"))
        self.on_thumbnail_clicked(post, self.post_to_widget_map.get(post['id']))

    def random_tag(self):
        self.status.setText(_tr("Fetching random tag..."))
        worker = ApiWorker(danbooru_random, "") 
        worker.signals.finished.connect(self.on_random_tag_loaded)
        self.threadpool.start(worker)

    def fetch_suggestions(self):
        search_text = self.search_input.text().strip()
        if not search_text or len(search_text) < 2:
            return
        worker = ApiWorker(suggest_all_tags, search_text, 20)
        worker.signals.finished.connect(self.on_suggestions_loaded)
        self.threadpool.start(worker)

    def on_suggestions_loaded(self, suggestions, err):
        if err or not suggestions:
            return
        if isinstance(suggestions, list):
            self.search_completer_model.setStringList(suggestions)

    def suggest_tags_dialog(self):
        text, ok = QInputDialog.getText(
            self, 
            _tr("Tag Suggestion"), 
            _tr("Enter partial tag name:"),
            QLineEdit.Normal,
            self.search_input.text()
        )
        
        if not ok or not text.strip():
            return
        
        self.status.setText(_tr("Fetching tag suggestions..."))
        worker = ApiWorker(suggest_all_tags, text.strip(), 40)
        worker.signals.finished.connect(self.on_suggest_tags_dialog_result)
        self.threadpool.start(worker)

    def on_suggest_tags_dialog_result(self, suggestions, err):
        if err or not suggestions:
            self.status.setText(_tr("Error fetching tag suggestions."))
            return
        
        if not isinstance(suggestions, list):
            self.status.setText(_tr("No suggestions found."))
            return
        
        if not suggestions:
            self.status.setText(_tr("No tags matching your query."))
            return
        from PyQt5.QtWidgets import QInputDialog
        items = [str(s) for s in suggestions]
        item, ok = QInputDialog.getItem(
            self,
            _tr("Select Tag"),
            _tr("Choose a tag:"),
            items,
            0,
            False
        )
        
        if ok and item:
            self.search_input.setText(item)
            self.start_new_search()

    def open_selected_full(self):
        active_tab = self.tabs.currentWidget()
        if active_tab not in [self.browser_tab, self.favorites_tab, self.downloads_tab]:
            return
            
        if self.last_selected:
            if active_tab == self.browser_tab:
                if not any(p.get("id") == self.last_selected.get("id") for p in getattr(self, "posts", [])):
                    return
            elif active_tab == self.favorites_tab:
                favs = self.favorites.get(self.current_favorites_category, {})
                if self.last_selected.get("id") not in favs:
                    return
            elif active_tab == self.downloads_tab:
                if not any(p.get("id") == self.last_selected.get("id") for p in getattr(self, "downloads_posts", [])):
                    return
                    
            self.open_post_full(self.last_selected)

    def on_random_tag_loaded(self, post, err):
        if err or not post:
            self.status.setText(_tr("Error fetching random tag."))
            return

        tags_string = post.get("tags", "")
        if not tags_string:
            self.status.setText(_tr("Could not find any tags."))
            return

        all_tags = tags_string.split()
        from snekbooru.common.constants import BORING_TAGS
        interesting_tags = [tag for tag in all_tags if tag not in BORING_TAGS and ":" not in tag]

        if not interesting_tags:
            interesting_tags = all_tags 

        if interesting_tags:
            random_tag = random.choice(interesting_tags)
            self.search_input.setText(random_tag)
            self.start_new_search()

    def open_post_full(self, post):
        self._record_browse_open(post)
        active_tab = self.tabs.currentWidget()
        if active_tab == self.browser_tab:
            posts_list = self.posts
        elif active_tab == self.favorites_tab:
            posts_list = list(self.favorites.get(self.current_favorites_category, {}).values())
        elif active_tab == self.hentai_tab:
            pass; return
        elif active_tab == self.downloads_tab:
            local_path = post.get("local_path")
            if not local_path or not os.path.exists(local_path):
                QMessageBox.warning(self, _tr("File Not Found"), _tr("The local file for this download is missing."))
                return
            posts_list = [p for p in self.downloads_posts if p.get("local_path") and os.path.exists(p.get("local_path"))]
        else:
            posts_list = [post]

        try:
            current_index = posts_list.index(post)
        except ValueError:
            posts_list = [post]
            current_index = 0

        from snekbooru.ui.media_viewer import launch_media_viewer_process
        p = Process(target=launch_media_viewer_process, args=(posts_list, current_index, self.favorites, SETTINGS, self.media_viewer_queue, self.custom_themes))
        p.start()
        self.media_viewer_processes.append(p)

    def download_selected(self):
        if self.last_selected: self.download_post(self.last_selected)

    def download_post(self, post):
        from snekbooru.core.downloader import download_media
        success, message = download_media(post, self)
        if success:
            if not getattr(self, 'is_incognito_window', False) and hasattr(self, 'persona') and self.persona is not None:
                try:
                    record_download(self.persona, post, _persona_source(post))
                except Exception:
                    pass
            if SETTINGS.get("show_download_notification", True):
                self._show_download_toast(message)
            else:
                try:
                    self.status.setText(message)
                except Exception:
                    pass
        else:
            QMessageBox.warning(self, _tr("Download Failed"), message)

    def _show_download_toast(self, message):
        toast = QLabel(message, self)
        toast.setStyleSheet("""
            QLabel {
                background-color: #2d2d2d;
                color: #fff;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
        """)
        toast.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        toast.adjustSize()
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = screen_geo.right() - toast.width() - 20
        y = screen_geo.bottom() - toast.height() - 40
        toast.move(x, y)
        toast.show()
        QTimer.singleShot(3000, toast.deleteLater)

    def toggle_inspector_favorite(self):
        if self.last_selected:
            self.toggle_favorite(self.last_selected)

    def _sanitize_post_for_storage(self, post):
        clean_post = post.copy()
        
        keys_to_remove = ["hh_object", "episode_obj", "pixmap", "movie", "hanime_data", "hanime_slug"]
        for key in keys_to_remove:
            if key in clean_post:
                del clean_post[key]
        
        return clean_post

    def toggle_favorite(self, post):
        post_id = post.get('id')
        if not post_id: return

        category = find_post_in_favorites(post_id, self.favorites)
        if category:
            del self.favorites[category][post_id]
        else:
            self.favorites["Uncategorized"][post_id] = self._sanitize_post_for_storage(post)
        
        save_favorites(self.favorites)
        self.update_inspector_fav_button(post)
        
        widget = self.post_to_widget_map.get(post_id) or self.fav_post_to_widget_map.get(post_id)
        if widget:
            widget.update_style()

    def update_inspector_fav_button(self, post):
        post_id = post.get('id')
        is_fav = post_id and find_post_in_favorites(post_id, self.favorites)
        icon, text = ('fa5s.star', _tr(" Unfavorite")) if is_fav else ('fa5s.star', _tr(" Favorite"))
        color = 'yellow' if is_fav else None
        self.inspector_fav_btn.setText(text)
        self.inspector_fav_btn.setIcon(qta.icon(icon, color=color))

    def reverse_search_selected(self):
        if not self.last_selected: return
        
        image_url = self.last_selected.get("file_url")
        if not image_url:
            QMessageBox.warning(self, _tr("Reverse Search"), _tr("No image URL available for this post."))
            return

        self.tabs.setCurrentWidget(self.browser_tab)
        self.browser_content_tabs.setCurrentIndex(2) 
        self.reverse_search_url_input.setText(image_url)
        self._perform_reverse_search()

    def start_bulk_download(self):
        if not self.selected_for_bulk:
            QMessageBox.information(self, _tr("Bulk Download"), _tr("No posts selected."))
            return
        
        from PyQt5.QtCore import QThread
        class DownloadWorker(QThread):
            progress = pyqtSignal(int, int, str)
            finished = pyqtSignal(str)

            def __init__(self, posts_to_download, download_dir, parent_app):
                super().__init__()
                self.posts = list(posts_to_download)
                self.parent_app = parent_app
                self.download_dir = download_dir
                self.is_cancelled = False

            def run(self):
                from snekbooru.core.downloader import download_media
                total = len(self.posts)
                for i, post in enumerate(self.posts):
                    if self.is_cancelled: break
                    self.progress.emit(i + 1, total, _tr("Downloading Post #{id}...").format(id=post.get('id')))
                    try:
                        download_media(post) 
                        self.progress.emit(i + 1, total, _tr("Saved Post #{id}").format(id=post.get('id')))
                    except Exception as e:
                        self.progress.emit(i + 1, total, _tr("Failed Post #{id}: {error}").format(id=post.get('id'), error=e))
                        time.sleep(0.1) 
                self.finished.emit(_tr("Bulk download cancelled.") if self.is_cancelled else _tr("Bulk download complete."))

            def cancel(self): self.is_cancelled = True

        posts_to_download = []
        for post_id in self.selected_for_bulk:
            if post := self.id_to_post_map.get(post_id):
                posts_to_download.append(post)

        worker = DownloadWorker(posts_to_download, SETTINGS.get("download_dir"), self)
        dialog = BulkDownloadDialog(worker, self)
        dialog.exec_()
        self.refresh_downloads_grid()

    def select_all_visible(self):
        for post_id, widget in self.post_to_widget_map.items():
            if widget.isVisible():
                self.selected_for_bulk.add(post_id)
                widget.set_selection(True)
        self.update_bulk_status()

    def deselect_all(self):
        for post_id in list(self.selected_for_bulk):
            if post_id in self.post_to_widget_map:
                self.post_to_widget_map[post_id].set_selection(False)

        self.selected_for_bulk.clear()
        self.update_bulk_status()

    def toggle_bulk_selection(self, post, widget):
        post_id = post.get('id')
        if post_id in self.selected_for_bulk:
            self.selected_for_bulk.remove(post_id)
            widget.set_selection(False)
        else:
            self.selected_for_bulk.add(post_id)
            widget.set_selection(True)
        self.update_bulk_status()

    def update_bulk_status(self):
        self.bulk_status_label.setText(_tr("{count} selected.").format(count=len(self.selected_for_bulk)))

    def add_to_search_history(self, text):
        if text and text not in self.search_history:
            self.search_history.insert(0, text)
            self.search_history = self.search_history[:50] 
            self.search_completer_model.setStringList(self.search_history)
            save_search_history(self.search_history)
        if not getattr(self, 'is_incognito_window', False) and hasattr(self, 'persona') and self.persona is not None:
            try:
                record_search(self.persona, text)
            except Exception:
                pass

    def clear_search_history(self):
        self.search_history.clear()
        self.search_completer_model.setStringList([])
        save_search_history([])
        QMessageBox.information(self, _tr("History Cleared"), _tr("Search history has been cleared."))

    def fetch_recommendations(self):
        self.reco_status_label.setText(_tr("Analyzing your favorites and browsing habits to find recommendations..."))
        
        tag_counts = {}
        for category in self.favorites.values():
            for post in category.values():
                for tag in post.get('tags', '').split():
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        from snekbooru.common.constants import BORING_TAGS
        for tag in BORING_TAGS:
            tag_counts.pop(tag, None)

        if not getattr(self, 'is_incognito_window', False) and hasattr(self, 'persona') and self.persona is not None:
            from snekbooru.core.persona import top_affinity_tags
            blacklist_now = set(SETTINGS.get("blacklisted_tags", "").split())
            blacklist_now.update(BORING_TAGS)
            if not SETTINGS.get("allow_loli_shota", True):
                blacklist_now.update(["loli", "shota"])
            if not SETTINGS.get("allow_bestiality", False):
                blacklist_now.add("bestiality")
            if not SETTINGS.get("allow_guro", False):
                blacklist_now.add("guro")
            persona_tags = top_affinity_tags(self.persona, limit=25, exclude=blacklist_now)
            for tag in persona_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        sorted_tags = sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)
        top_tags = [tag for tag, count in sorted_tags[:20]]

        if not top_tags:
            self.reco_status_label.setText(_tr("Not enough favorites to generate recommendations."))
            return

        self.reco_status_label.setText(_tr("Fetching posts for your favorite tags..."))

        blacklisted_tags = SETTINGS.get("blacklisted_tags", "").split()
        if not SETTINGS.get("allow_loli_shota", True):
            blacklisted_tags.extend(["loli", "shota"])
        if not SETTINGS.get("allow_bestiality", False):
            blacklisted_tags.append("bestiality")
        if not SETTINGS.get("allow_guro", False):
            blacklisted_tags.append("guro")

        worker = RecommendationFetcher(top_tags, blacklisted_tags)
        worker.signals.finished.connect(self.on_recommendations_loaded)
        worker.signals.progress.connect(lambda cur, tot, msg: self.reco_status_label.setText(f"({cur}/{tot}) {msg}"))
        self.threadpool.start(worker)

    def on_recommendations_loaded(self, data, err):
        self.clear_grid(self.reco_grid)
        self.reco_post_to_widget_map.clear()

        if err:
            self.reco_status_label.setText(_tr("Error fetching recommendations: {error}").format(error=err))
            return

        posts, _ = data

        self.reco_posts = posts
        self.populate_grid(self.reco_grid, self.reco_posts, self.reco_post_to_widget_map, self.on_thumbnail_clicked, viewport_width=self.reco_scroll.viewport().width())
        self.reco_status_label.setText(_tr("Found {count} recommended posts.").format(count=len(posts)))

    def open_settings(self):
        self.custom_fonts_path = get_fonts_path()
        dialog = SettingsDialog(self, self.custom_fonts_path)
        old_lang = SETTINGS.get("language")

        if dialog.exec_():
            new_settings = dialog.values()
            SETTINGS.update(new_settings)
            save_settings(SETTINGS)
            self.reapply_settings(old_lang)

    def reapply_settings(self, old_lang):
        if SETTINGS.get("language") != old_lang:
            self.retranslate_ui()

        self.apply_theme()
        self.load_hotkeys()
        self._configure_temp_cleanup_timer()
        self.update_source_label()
        self.apply_window_settings()
        self.apply_potato_mode()

        self.clear_grid(self.grid)
        self.clear_grid(self.fav_grid)

        self.on_posts_loaded((self.posts, 0), None)
        self.refresh_favorites_grid()
        self.refresh_downloads_grid()

    def refresh_visible_grid(self):
        current_tab = self.tabs.currentWidget()
        if current_tab == self.browser_tab:
            self.on_posts_loaded((self.posts, 0), None)
        elif current_tab == self.favorites_tab:
            self.refresh_favorites_grid()

    def retranslate_ui(self):
        self.title_bar.title_label.setText(_tr("Snekbooru (Incognito)") if self.is_incognito_window else _tr("Snekbooru"))
        self.limit.setSuffix(_tr(" posts"))
        self.limit.setToolTip(_tr("Number of posts to load per page."))
        self.source_title_label.setText(_tr("Source:"))
        self.settings_btn.setText(_tr(" Settings"))

        self.tabs.setTabText(self.tabs.indexOf(self.home_tab), _tr("Home"))
        self.tabs.setTabText(self.tabs.indexOf(self.browser_tab), _tr("Browser"))
        self.tabs.setTabText(self.tabs.indexOf(self.favorites_tab), _tr("Favorites"))
        self.tabs.setTabText(self.tabs.indexOf(self.downloads_tab), _tr("Downloads"))
        self.tabs.setTabText(self.tabs.indexOf(self.manga_tab), _tr("Manga"))
        self.tabs.setTabText(self.tabs.indexOf(self.minigames_tab), _tr("Minigames"))
        self.tabs.setTabText(self.tabs.indexOf(self.ai_tab), _tr("AI"))

        self.home_title.setText(_tr("Welcome to Snekbooru"))
        self.home_subtitle.setText(_tr("Total posts available from supported sources:"))
        self.disclaimer_label.setText(_tr("(Note: Gelbooru & Danbooru totals are only accurate with an API key. Other counts are scraped.)"))
        self.home_refresh_btn.setText(_tr(" Refresh Stats"))
        self.credits_group.setTitle(_tr("Credits"))

        self.controls_group.setTitle(_tr("Search Controls"))
        self.search_input.setPlaceholderText(_tr("tags (e.g. rating:safe cat_girl)"))
        self.include_pref.setText(_tr("Include preferred tags"))
        self.suggest_btn.setText(_tr(" Suggest Tags"))
        self.search_btn.setText(_tr(" Search"))
        self.rand_btn.setText(_tr(" Random Post"))
        self.rand_tag_btn.setText(_tr(" Random Tag"))
        self.insp_group.setTitle(_tr("Post Inspector"))
        self.open_full.setText(_tr(" Open Full Media"))
        self.quick_dl.setText(_tr(" Quick Download"))
        self.inspector_fav_btn.setText(_tr(" Favorite")) 
        self.reverse_search_btn.setText(_tr("Reverse Search"))
        self.bulk_group.setTitle(_tr("Bulk Download"))
        self.bulk_dl_btn.setText(_tr(" Download Selected"))
        self.select_all_btn.setText(_tr(" Select All Visible"))
        self.deselect_all_btn.setText(_tr(" Deselect All"))
        self.bulk_status_label.setText(_tr("{count} selected.").format(count=len(self.selected_for_bulk)))
        self.prev_btn.setText(_tr(" Previous"))
        self.next_btn.setText(_tr("Next "))
        self.page_input.setToolTip(_tr("Go to page... (Press Enter)"))
        self.status.setText(_tr("Ready"))

        self.fav_category_group.setTitle(_tr("Categories"))
        self.new_cat_btn.setText(_tr(" New"))
        self.rename_cat_btn.setText(_tr(" Rename"))
        self.delete_cat_btn.setText(_tr(" Delete"))
        self.fav_refresh_btn.setText(_tr(" Refresh Grid"))
        self.fav_search_filter_label.setText(_tr("Filter:"))
        self.fav_search_input.setPlaceholderText(_tr("Filter by tags..."))
        self.fav_insp_group.setTitle(_tr("Post Inspector"))

        self.manga_search_input.setPlaceholderText(_tr("manga or doujinshi title..."))
        self.manga_search_btn.setText(_tr(" Search"))
        self.manga_clear_search_btn.setText(_tr(" Clear"))
        self.manga_refresh_btn.setText(_tr(" Refresh"))
        self.manga_status_label.setText(_tr("Ready"))
        self.manga_results_label.setText(_tr("Ready"))
        self.manga_info.setPlainText(_tr("No manga found."))
        self.manga_open_btn.setText(_tr(" Open"))
        self.manga_open_browser_btn.setText(_tr(" Open on Website"))

    def apply_potato_mode(self):
        is_potato = SETTINGS.get("potato_mode", False)
        
        self.suggest_btn.setVisible(not is_potato)
        self.browser_content_tabs.setTabVisible(1, not is_potato) 

    def apply_theme(self):
        self.custom_themes = load_custom_themes()
        theme_name = SETTINGS.get("active_theme", "Dark (Default)")
        
        if self.is_incognito_window:
            scss_string = INCOGNITO_STYLESHEET
        elif theme_name == "Dark (Default)":
            scss_string = DARK_STYLESHEET
        elif theme_name == "Light (Default)":
            scss_string = LIGHT_STYLESHEET
        else:
            scss_string = self.custom_themes.get(theme_name, DARK_STYLESHEET)

        final_stylesheet = preprocess_stylesheet(scss_string)
        self.setStyleSheet(final_stylesheet)
        for btn in [self.title_bar.minimize_btn, self.title_bar.maximize_btn, self.title_bar.close_btn]:
            btn.style().unpolish(btn); btn.style().polish(btn)
        self.title_bar.update_icons()
        self.repaint()
        QApplication.processEvents()

    def update_source_label(self):
        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
        if len(enabled_sources) > 3:
            display_text = _tr("{count} Sources").format(count=len(enabled_sources))
        else:
            display_text = ", ".join(enabled_sources)
        self.source_lbl.setText(display_text)

    def launch_incognito_window(self):
        incognito_app = GelDanApp(is_incognito=True)
        self.incognito_windows.append(incognito_app)
        incognito_app.show()

    def closeEvent(self, event):
        for p in self.media_viewer_processes:
            if p.is_alive():
                p.terminate()
                try:
                    p.join(timeout=2.0)
                except Exception:
                    pass
        for w in self.incognito_windows:
            w.close()
        
        if not self.is_incognito_window:
            save_settings(SETTINGS)
            save_tag_profile(self.tag_profile)
            save_favorites(self.favorites)
            save_highscores(self.highscores)
            try:
                if getattr(self, 'persona', None) is not None:
                    save_persona(self.persona)
            except Exception:
                pass

        try:
            from snekbooru.core.temp_cache import purge_snekbooru_temp
            purge_snekbooru_temp()
        except Exception:
            pass

        super().closeEvent(event)
    
    def apply_window_settings(self):
        mode = SETTINGS.get("window_mode", "Windowed")

        self.showNormal() 

        if mode == _tr("Fullscreen"):
            self.title_bar.hide()
            self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint) 
            self.showFullScreen()
            return 
        elif mode == _tr("Windowed Borderless"):
            self.title_bar.hide()
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            screen_rect = QApplication.desktop().screenGeometry()
            self.setGeometry(screen_rect) 
        else:
            self.title_bar.show()
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            size_preset = SETTINGS.get("window_size_preset", "1600x900")
            if size_preset == _tr("Custom"):
                width = SETTINGS.get("custom_window_width", 1820)
                height = SETTINGS.get("custom_window_height", 1080)
            else:
                try:
                    width, height = map(int, size_preset.split(' ')[0].split('x'))
                except ValueError:
                    width, height = 1820, 1080 
            self.resize(width, height)
            self.center_on_screen()

        self.show()

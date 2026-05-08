import os
import random
import shutil
import sys
import threading
import time
import re
import inspect

vendor_path = os.path.join(os.path.dirname(__file__), '..', 'vendor')
sys.path.insert(0, vendor_path)

import base64
import cloudscraper
import requests
from multiprocessing import Process, Queue
try:
    from snekbooru_linux.vendor import hhaven
except ImportError:
    hhaven = None
import time
import qtawesome as qta
from enma import Enma, Sources, infra
from PyQt5.QtCore import (QCoreApplication, QEvent, QPoint, QStringListModel,
                          Qt, QThreadPool, QTimer, pyqtSignal, QThread, QUrl, QStandardPaths)
from PyQt5.QtGui import (QCursor, QIcon, QKeySequence, QMovie, QPixmap,
                         QTextCursor, QIntValidator, QDesktopServices)
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter,
                             QFormLayout, QFrame, QGridLayout, QGroupBox,
                             QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton,
                             QScrollArea, QSizePolicy, QSpacerItem, QSpinBox, QStackedWidget, QFileDialog,
                             QSplitter, QTabWidget, QWidget, QVBoxLayout, QToolButton, QDialog, QTextBrowser, QTextEdit,
                             QSlider, QShortcut, QKeySequenceEdit)
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
import webbrowser, traceback
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineProfile, QWebEngineView, QWebEngineScript
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWidgets import QDesktopWidget
from snekbooru_linux.api.nhentai import download_gallery_pages, parse_gallery_id
from snekbooru_linux.api.booru import (gelbooru_posts, danbooru_post_count, danbooru_random,
                                 fetch_multiple_sources,
                                 suggest_all_tags)
from snekbooru_linux.api.utils import scrape_post_count
from snekbooru_linux.common.constants import USER_AGENT
from snekbooru_linux.common.helpers import get_file_hash, get_resource_path
from snekbooru_linux.common.translations import _tr
from snekbooru_linux.core.config import (SETTINGS, find_post_in_favorites,
                                   load_custom_boorus, load_downloads_data,
                                   load_favorites, load_highscores,
                                   load_search_history, load_tag_profile,
                                   save_downloads_data, save_favorites,
                                   save_highscores, save_search_history,
                                   save_settings, save_tag_profile) # noqa: E501
from snekbooru_linux.core.manga_utils import normalize_http_url, resolve_manga_url
from snekbooru_linux.core.book_export import (cleanup_images_folder, export_epub_from_images,
                                        export_mobi_from_images, export_pdf_from_images,
                                        export_png_zip_from_images, list_image_files)
from snekbooru_linux.core.temp_cache import cleanup_snekbooru_temp, snekbooru_temp_dir
from snekbooru_linux.core.workers import (AIStreamWorker, ApiWorker, AsyncApiWorker, ImageWorker,
                                    RecommendationFetcher)
from snekbooru_linux.ui.dialogs import (BaseDialog, BulkDownloadDialog,
                                  BookExportDialog, MangaBookDialog, MangaDownloadExportDialog, HentaiSeriesDialog, HentaiViewerDialog, SettingsDialog)
from snekbooru_linux.ui.styling import (DARK_STYLESHEET, INCOGNITO_STYLESHEET,
                                  LIGHT_STYLESHEET, get_fonts_path,
                                  load_custom_themes, preprocess_stylesheet)
from PyQt5.QtMultimedia import QMediaPlayer
from snekbooru_linux.ui.vlc_player import VLCVideoPlayer
from snekbooru_linux.ui.minigames import (PostShowdownGame, ImageScrambleGame,
                                    TagGuesserGame)
from snekbooru_linux.ui.widgets import (AdBlocker, ImageDropLabel, MangaListItem,
                                  ThumbnailWidget)
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


class MangaWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if isinstance(message, str) and "Unrecognized feature: 'cross-origin-isolated'" in message:
            return
        return super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

def _mangadex_og_image_from_url(url):
    if not isinstance(url, str): return None
    match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]+)", url)
    if not match: return None
    return f"https://og.mangadex.org/og-image/manga/{match.group(1)}"

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
    if manga_obj is None: return None
    if isinstance(manga_obj, dict):
        for k in ("cover", "thumbnail", "image", "images", "cover_url", "thumbnail_url"):
            if k in manga_obj:
                val = manga_obj[k]
                if isinstance(val, str):
                    url = normalize_http_url(val)
                    if url.startswith("http"): return url
                    og = _mangadex_og_image_from_url(url)
                    if og: return og
                if isinstance(val, dict):
                    for sub in ("uri", "url", "src"):
                        if sub in val and isinstance(val[sub], str):
                            url = normalize_http_url(val[sub])
                            if url.startswith("http"): return url
                            og = _mangadex_og_image_from_url(url)
                            if og: return og
                for sub in ("url", "uri", "src"):
                    if hasattr(val, sub):
                        try:
                            url = normalize_http_url(getattr(val, sub))
                            if isinstance(url, str) and url.startswith("http"): return url
                            og = _mangadex_og_image_from_url(url)
                            if og: return og
                        except Exception: pass
    for attr in ("cover", "thumbnail", "image", "images", "cover_url", "thumbnail_url", "thumbnail"):
        if hasattr(manga_obj, attr):
            try:
                val = getattr(manga_obj, attr)
                if isinstance(val, str):
                    url = normalize_http_url(val)
                    if url.startswith("http"): return url
                    og = _mangadex_og_image_from_url(url)
                    if og: return og
                if isinstance(val, dict):
                    for sub in ("uri", "url", "src"):
                        if sub in val and isinstance(val[sub], str):
                            url = normalize_http_url(val[sub])
                            if url.startswith("http"): return url
                            og = _mangadex_og_image_from_url(url)
                            if og: return og
                if hasattr(val, "uri"):
                    u = getattr(val, "uri")
                    url = normalize_http_url(u)
                    if isinstance(url, str) and url.startswith("http"): return url
                    og = _mangadex_og_image_from_url(url)
                    if og: return og
                for sub in ("url", "src"):
                    if hasattr(val, sub):
                        u = getattr(val, sub)
                        url = normalize_http_url(u)
                        if isinstance(url, str) and url.startswith("http"): return url
                        og = _mangadex_og_image_from_url(url)
                        if og: return og
                if isinstance(val, (list, tuple)) and val:
                    first = val[0]
                    if isinstance(first, str):
                        url = normalize_http_url(first)
                        if url.startswith("http"): return url
                        og = _mangadex_og_image_from_url(url)
                        if og: return og
                    if hasattr(first, "uri"):
                        u = getattr(first, "uri")
                        url = normalize_http_url(u)
                        if isinstance(url, str) and url.startswith("http"): return url
                        og = _mangadex_og_image_from_url(url)
                        if og: return og
            except Exception: pass
    return None

def extract_title(manga_obj):
    if manga_obj is None: return "<no title>"
    if isinstance(manga_obj, dict):
        for k in ("title", "name"):
            if k in manga_obj:
                v = manga_obj[k]
                title = _extract_title_from_value(v)
                if title: return title
        for k in ("pretty", "english", "en", "japanese", "jp"):
            if k in manga_obj:
                title = _extract_title_from_value(manga_obj[k])
                if title: return title
    for attr in ("title", "name"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                title = _extract_title_from_value(v)
                if title: return title
            except Exception: pass
    for attr in ("pretty", "english", "en", "japanese", "jp"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                title = _extract_title_from_value(v)
                if title: return title
            except Exception: pass
    for attr in ("url", "uri", "link", "page", "source_url"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            except Exception:
                pass
    for attr in ("id", "identifier", "uuid", "manga_id"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                if isinstance(v, (str, int)) and str(v).strip():
                    return str(v).strip()
            except Exception:
                pass
    try:
        return repr(manga_obj)[:120]
    except Exception:
        return "<no title>"


def number_to_png_display(number):
    """Convert a number to HTML with PNG digit images that scale with window size."""
    try:
        number_str = str(number).replace(',', '')
        html_parts = []
        for digit in number_str:
            if digit.isdigit():
                digit_path = get_resource_path(os.path.join("graphics", f"{digit}.png"))
                if os.path.exists(digit_path):
                    # Load and scale the image
                    pixmap = QPixmap(digit_path)
                    if not pixmap.isNull():
                        # Scale to a responsive height based on viewport
                        # Using ~2.5% of viewport height for scaling
                        screen = QApplication.primaryScreen()
                        viewport_height = screen.geometry().height()
                        responsive_height = max(14, int(viewport_height * 0.15))
                        
                        scaled = pixmap.scaledToHeight(responsive_height, Qt.SmoothTransformation)
                        # Convert to base64 for embedding
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
    """Detect which booru source the user wants to search in from the query."""
    query_lower = query.lower()
    source_keywords = {
        "gelbooru": ["gel", "gelbooru"],
        "danbooru": ["dan", "danbooru", "dan booru"],
        "konachan": ["kona", "konachan"],
        "yandere": ["yan", "yandere"],
        "rule34": ["rule34", "rule 34"],
        "hypnohub": ["hypno", "hypnohub"],
    }
    
    detected_sources = []
    for source, keywords in source_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_sources.append(source.capitalize() if source != "rule34" else "Rule34")
    
    # If no source detected, use enabled sources
    if not detected_sources:
        detected_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
    
    return detected_sources

async def _do_hhaven_search(query: str) -> list:
    """Async helper to search Hentai Haven."""
    import asyncio
    client = hhaven.Client()
    try:
        await client.build()
        results = await client.search(query)
        full_hentai_objects = await asyncio.gather(*[h.full() for h in results])
        return full_hentai_objects
    finally:
        await client.close()

async def _do_hhaven_random(count=12) -> list:
    """Async helper to get multiple random Hentai Haven entries from the homepage."""
    import random
    import asyncio
    client = hhaven.Client()
    try:
        await client.build()
        home_page = await client.home()
        if not home_page.last:
            return []
        
        sample_size = min(count, len(home_page.last))
        random_partials = random.sample(home_page.last, sample_size)
        full_hentai_objects = await asyncio.gather(*[h.full() for h in random_partials])
        return full_hentai_objects
    finally:
        await client.close()

async def _get_hhaven_stream_url(episode: 'hhaven.PartialHentaiEpisode') -> str:
    """Extracts the direct .m3u8 stream URL from a Hentai Haven episode object."""
    client = hhaven.Client()
    try:
        await client.build()
        full_episode = await client.get_episode(episode.id, episode.hentai_id)
        return full_episode.content
    finally:
        await client.close()

async def _scrape_hhaven_series_page(hentai_obj: 'hhaven.Hentai') -> dict:
    """Converts a hhaven.Hentai object to the dict format HentaiSeriesDialog expects."""
    episodes = []
    for episode in hentai_obj.episodes:
        episodes.append({
            'title': episode.name,
            'url': None, # URL is not needed, we pass the object
            'episode_obj': episode
        })

    return {
        "title": hentai_obj.title,
        "description": hentai_obj.description,
        "episodes": episodes
    }

class ChatBrowser(QTextBrowser):
    """Custom QTextBrowser that disables internal navigation to prevent chat reset."""
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

        self.update_icons() # Set initial icons

        for btn in [self.minimize_btn, self.maximize_btn, self.close_btn]:
            btn.setFixedSize(46, 32)
            btn.setObjectName("title_bar_button") # Generic class for all title bar buttons

        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)

        self.start_move_pos = None

    def _get_icon_color(self):
        """Determines if theme is dark or light and returns appropriate icon color."""
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
        # Only pass the parent to the QDialog constructor if it's a QWidget.
        # This allows the dialog to be created in a separate process with a mock parent.
        qt_parent = parent if isinstance(parent, QWidget) else None
        # Initialize BaseDialog with a placeholder title, we'll set it properly later.
        super().__init__("Media Viewer", qt_parent)

        self.parent_app = parent
        self.posts_list = posts_list
        self.current_index = current_index
        self.post = self.posts_list[self.current_index]

        self.setMinimumSize(800, 600)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        self.media_stack = QStackedWidget()
        self.content_layout.addWidget(self.media_stack, 1)

        # Image view
        self.image_scroll_area = QScrollArea()
        self.image_scroll_area.setWidgetResizable(True)
        self.image_label = QLabel(_tr("Loading image..."))
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_scroll_area.setWidget(self.image_label)
        self.media_stack.addWidget(self.image_scroll_area)

        # Video view - QMediaPlayer for local files, VLC for streaming
        self.qmedia_player = QMediaPlayer(self)
        self.qmedia_video_widget = QVideoWidget()
        self.qmedia_video_widget.setStyleSheet("background-color: black;")
        self.qmedia_player.setVideoOutput(self.qmedia_video_widget)
        self.media_stack.addWidget(self.qmedia_video_widget)

        self.vlc_video_player = VLCVideoPlayer()
        self.media_stack.addWidget(self.vlc_video_player)
        
        self.cv_video_player = None  # For compatibility
        self.temp_video_file = None

        # Video controls
        self.video_controls = QWidget()
        video_controls_layout = QHBoxLayout(self.video_controls)
        video_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.play_pause_button = QPushButton(qta.icon('fa5s.play'), "")
        self.rewind_10_button = QPushButton(qta.icon('fa5s.redo'), " -10s")
        self.forward_10_button = QPushButton(qta.icon('fa5s.undo'), "+10s ")
        self.forward_10_button.setLayoutDirection(Qt.RightToLeft)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.duration_label = QLabel("--:-- / --:--")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        self.fullscreen_button = QPushButton(qta.icon('fa5s.expand'), "")
        video_controls_layout.addWidget(self.play_pause_button)
        video_controls_layout.addWidget(self.rewind_10_button)
        video_controls_layout.addWidget(self.forward_10_button)
        video_controls_layout.addWidget(self.seek_slider)
        video_controls_layout.addWidget(self.duration_label)
        video_controls_layout.addWidget(self.volume_slider)
        video_controls_layout.addWidget(self.fullscreen_button)
        self.video_controls.setVisible(False) # Hide by default

        # Controls
        controls_layout = QHBoxLayout()
        self.prev_button = QPushButton(qta.icon('fa5s.arrow-left'), _tr(" Previous"))
        self.next_button = QPushButton(qta.icon('fa5s.arrow-right'), _tr("Next "))
        self.next_button.setLayoutDirection(Qt.RightToLeft)

        # Zoom controls for images
        self.zoom_in_button = QPushButton(qta.icon('fa5s.search-plus'), "")
        self.zoom_out_button = QPushButton(qta.icon('fa5s.search-minus'), "")
        self.zoom_fit_button = QPushButton(qta.icon('fa5s.compress'), "")
        self.zoom_label = QLabel("100%")
        self.zoom_controls = [self.zoom_in_button, self.zoom_out_button, self.zoom_fit_button, self.zoom_label]

        self.fav_button = QPushButton(qta.icon('fa5s.star'), _tr(" Favorite"))
        self.download_button = QPushButton(qta.icon('fa5s.download'), _tr(" Download"))
        self.open_browser_button = QPushButton(qta.icon('fa5s.external-link-alt'), _tr(" Open in Browser"))

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

        # Connections
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

        self.threadpool = QThreadPool()
        self.image_pixmap = None
        self.zoom_factor = 1.0
        self.gif_movie = None
        self.cleanup_thread = None

        self.load_media()

        # Connect signals for both players
        self.qmedia_player.positionChanged.connect(self.update_position)
        self.qmedia_player.durationChanged.connect(self.update_duration)
        self.vlc_video_player.position_changed.connect(self.update_position)
        self.vlc_video_player.duration_changed.connect(self.update_duration)
        self.vlc_video_player.state_changed.connect(self.update_play_pause_button)
        self.vlc_video_player.error.connect(self.on_vlc_error)
        
        self._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._shortcut_prev.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_prev.activated.connect(self._handle_left_key)
        
        self._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._shortcut_next.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_next.activated.connect(self._handle_right_key)

    def _handle_left_key(self):
        current_widget = self.media_stack.currentWidget()
        is_video_playing = current_widget in [self.qmedia_video_widget, self.vlc_video_player]
        modifiers = QApplication.keyboardModifiers()
        
        if is_video_playing and int(modifiers) == 0:
            self.skip_video(-10)
        else:
            self.prev_media()

    def _handle_right_key(self):
        current_widget = self.media_stack.currentWidget()
        is_video_playing = current_widget in [self.qmedia_video_widget, self.vlc_video_player]
        modifiers = QApplication.keyboardModifiers()
        
        if is_video_playing and int(modifiers) == 0:
            self.skip_video(10)
        else:
            self.next_media()

    def wheelEvent(self, event):
        if self.media_stack.currentWidget() == self.image_scroll_area:
            self.zoom_image(1.1 if event.angleDelta().y() > 0 else 1 / 1.1)

    def update_controls(self):
        """Updates the state of the control buttons."""
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.posts_list) - 1)
        
        is_favorited = find_post_in_favorites(self.post.get('id'), self.parent_app.favorites) is not None
        fav_icon_color = 'yellow' if is_favorited else None
        self.fav_button.setIcon(qta.icon('fa5s.star', color=fav_icon_color))

    def load_media(self):
        self.qmedia_player.stop()
        self.vlc_video_player.stop()
        self.image_pixmap = None
        if self.gif_movie: self.gif_movie.stop()
        self.gif_movie = None
        self.zoom_factor = 1.0

        title = f"Snekbooru Media Viewer - Post {self.post.get('id')}"
        self.setWindowTitle(title); self.title_bar.title_label.setText(title)
        self.update_controls()

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

        if not file_url:
            self.image_label.setText(_tr("Error: No file found."))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            return

        if file_ext in ['mp4', 'webm', 'mov', 'avi', 'mkv']:
            if use_local:
                self.video_controls.setVisible(True)
                for w in self.zoom_controls: w.setVisible(False)
                self._load_video_file(file_url)
            else:
                video_playback_method = SETTINGS.get("video_playback_method", _tr("Download First (Reliable)"))
                if video_playback_method == _tr("Stream (Experimental)"):
                    self.video_controls.setVisible(True)
                    for w in self.zoom_controls: w.setVisible(False)
                    self.media_stack.setCurrentWidget(self.vlc_video_player)
                    self._load_video_stream(file_url)
                else:
                    self.video_controls.setVisible(True)
                    for w in self.zoom_controls: w.setVisible(False)
                    self.image_label.setText(_tr("Loading video..."))
                    self.media_stack.setCurrentWidget(self.image_scroll_area)
                    
                    from snekbooru_linux.core.workers import ApiWorker
                    worker = ApiWorker(self._download_video_to_temp, file_url, self.post.get('id', 'temp'))
                    worker.signals.finished.connect(self._on_video_downloaded)
                    self.threadpool.start(worker)

        elif file_ext == 'gif':
            self.video_controls.setVisible(False)
            for w in self.zoom_controls: w.setVisible(False) # No zoom for GIFs for now
            self.image_label.setText(_tr("Loading GIF..."))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            if use_local:
                try:
                    with open(file_url, "rb") as f:
                        gif_content = f.read()
                    self._on_gif_data_loaded((gif_content, None), None)
                except Exception as e:
                    self.image_label.setText(_tr("Error loading GIF: {error}").format(error=str(e)))
            else:
                from snekbooru_linux.core.workers import ApiWorker
                worker = ApiWorker(self._fetch_raw_data, file_url)
                worker.signals.finished.connect(self._on_gif_data_loaded)
                self.threadpool.start(worker)

        else: # Assume image
            self.video_controls.setVisible(False)
            for w in self.zoom_controls: w.setVisible(True)
            self.image_label.setText(_tr("Loading image..."))
            self.media_stack.setCurrentWidget(self.image_scroll_area)
            if use_local:
                pixmap = QPixmap(file_url)
                self.on_image_loaded(pixmap, self.post)
            else:
                worker = ImageWorker(file_url, self.post)
                worker.signals.finished.connect(self.on_image_loaded)
                self.threadpool.start(worker)

    def on_image_loaded(self, pixmap, post):
        self.image_pixmap = pixmap
        if not pixmap.isNull():
            self.fit_image_to_window()
        else:
            self.image_label.setText(_tr("Error: Could not load image."))

    def _fetch_raw_data(self, url):
        """Generic worker function to fetch raw bytes from a URL."""
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
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            return r.content, None
        except Exception as e:
            return None, str(e)

    def _on_gif_data_loaded(self, data, err):
        gif_content, function_error = data

        if err or function_error or not gif_content:
            self.image_label.setText(_tr("Error loading GIF: {error}").format(error=err or "Unknown"))
            return

        # To load a QMovie from memory, we must use a QBuffer
        self.gif_byte_array = QByteArray(gif_content)
        self.gif_buffer = QBuffer(self.gif_byte_array)
        self.gif_buffer.open(QIODevice.ReadOnly)

        self.gif_movie = QMovie()
        self.gif_movie.setDevice(self.gif_buffer)
        self.image_label.setMovie(self.gif_movie)
        self.gif_movie.start()

    def _download_video_to_temp(self, url, post_id):
        """Downloads a video to a temporary file using pure Python (no ffmpeg)."""
        import tempfile
        try:
            file_ext = '.mp4'
            fd, self.temp_video_file = tempfile.mkstemp(dir=snekbooru_temp_dir("media"), suffix=file_ext)
            os.close(fd)
            
            # Pure Python streaming download - no ffmpeg at all
            try:
                if isinstance(url, str):
                    url = normalize_http_url(url).replace("\\", "/")
                headers = {'User-Agent': USER_AGENT}
                if isinstance(url, str) and "gelbooru" in url:
                    headers["Referer"] = "https://gelbooru.com/"
                response = requests.get(
                    url, 
                    timeout=300, 
                    headers=headers, 
                    stream=True
                )
                if response.status_code == 200:
                    # Stream video in chunks to temp file
                    with open(self.temp_video_file, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Verify file was written
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
        
        # Switch to video player widget
        self.media_stack.setCurrentWidget(self.qmedia_video_widget)
        
        # Load and play video
        self._load_video_file(filepath)

    def _load_video_stream(self, url):
        """Load the video stream directly into QMediaPlayer."""
        try:
            if isinstance(url, str):
                url = normalize_http_url(url).replace("\\", "/")
            self.vlc_video_player.load(url)
            self.vlc_video_player.play()
        except Exception as e:
            self.image_label.setText(_tr("Error: Could not play video: {error}").format(error=str(e)))
            self.media_stack.setCurrentWidget(self.image_scroll_area)

    def _load_video_file(self, filepath):
        """Load the video file into QMediaPlayer for local playback."""
        try:
            self.media_stack.setCurrentWidget(self.qmedia_video_widget)
            self.qmedia_player.setMedia(QMediaContent(QUrl.fromLocalFile(filepath)))
            self.qmedia_player.play()

        except Exception as e:
            self.image_label.setText(_tr("Error: Could not play video: {error}").format(error=str(e)))
            self.media_stack.setCurrentWidget(self.image_scroll_area)

    def on_vlc_error(self, error_msg):
        self.image_label.setText(_tr("Video Error: {error}").format(error=error_msg))
        self.media_stack.setCurrentWidget(self.image_scroll_area)
        self.video_controls.setVisible(False)
    
    def _format_time(self, seconds):
        """Format seconds to MM:SS format."""
        if seconds < 0:
            seconds = 0
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def _on_slider_moved(self, slider_value):
        """Handle slider position change (value is in milliseconds)."""
        if self.media_stack.currentWidget() == self.vlc_video_player:
            self.vlc_video_player.seek(slider_value)
        else:
            self.qmedia_player.setPosition(slider_value)

    def update_position(self, position):
        """Updates the seek slider and time label. Position is in milliseconds."""
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        
        duration = self.seek_slider.maximum()
        if duration > 0:
            self.duration_label.setText(
                f"{self._format_time(position / 1000)} / {self._format_time(duration / 1000)}")

    def update_duration(self, duration):
        """Updates the range of the seek slider. Duration is in milliseconds."""
        self.seek_slider.setRange(0, duration)
    
    def _cleanup_temp_video(self, wait_on_close=False):
        """Schedules the temporary video file for deletion with retries."""
        if self.temp_video_file and os.path.exists(self.temp_video_file):
            filepath_to_delete = self.temp_video_file
            self.temp_video_file = None # Unset immediately

            def robust_delete():
                max_attempts = 30 if wait_on_close else 120
                for _ in range(max_attempts):
                    if not os.path.exists(filepath_to_delete):
                        return
                    try:
                        os.remove(filepath_to_delete)
                        return # Success
                    except OSError:
                        time.sleep(0.5) # Wait 500ms before retrying

            # If closing, we need to wait for the thread. Otherwise, let it run in the background.
            is_daemon = not wait_on_close
            thread = threading.Thread(target=robust_delete, daemon=is_daemon)
            thread.start()

            if wait_on_close:
                self.cleanup_thread = thread

    def prev_media(self):
        self.qmedia_player.stop()
        self.vlc_video_player.stop()
        if self.gif_movie: self.gif_movie.stop()
        self._cleanup_temp_video()
        if self.current_index > 0:
            self.current_index -= 1
            self.post = self.posts_list[self.current_index]
            self.load_media()

    def next_media(self):
        self.qmedia_player.stop()
        self.vlc_video_player.stop()
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
        is_vlc = self.media_stack.currentWidget() == self.vlc_video_player
        
        if is_vlc:
            if self.vlc_video_player.is_playing:
                self.vlc_video_player.pause()
            else:
                self.vlc_video_player.play()
        else: # QMediaPlayer
            if self.qmedia_player.state() == QMediaPlayer.PlayingState:
                self.qmedia_player.pause()
            else:
                self.qmedia_player.play()

    def update_play_pause_button(self, state):
        """Updates the play/pause button icon based on player state."""
        is_playing = (state == 'playing') or (state == QMediaPlayer.PlayingState)
        if is_playing:
            self.play_pause_button.setIcon(qta.icon('fa5s.pause'))
        else:
            self.play_pause_button.setIcon(qta.icon('fa5s.play'))

    def skip_video(self, seconds):
        """Skip forward or backward by the given seconds."""
        is_vlc = self.media_stack.currentWidget() == self.vlc_video_player
        
        if is_vlc:
            current_pos_ms = self.vlc_video_player.player_thread.position if self.vlc_video_player.player_thread else 0
            new_pos_ms = max(0, current_pos_ms + (seconds * 1000))
            self.vlc_video_player.seek(new_pos_ms)
        else:
            current_pos = self.qmedia_player.position()
            new_pos = max(0, current_pos + (seconds * 1000))
            self.qmedia_player.setPosition(new_pos)

    def set_video_volume(self, volume):
        """Set volume (0-100)."""
        self.qmedia_player.setVolume(volume)
        self.vlc_video_player.set_volume(volume)

    def toggle_fullscreen(self):
        """Toggles fullscreen mode for the dialog."""
        is_vlc = self.media_stack.currentWidget() == self.vlc_video_player
        if is_vlc:
            self.vlc_video_player.toggle_fullscreen()
        elif self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setIcon(qta.icon('fa5s.expand'))
        else:
            self.showFullScreen()
            self.fullscreen_button.setIcon(qta.icon('fa5s.compress'))

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
        """Handle key presses for navigation and video control."""
        if event.isAutoRepeat():
            return  # Ignore auto-repeat key events
        
        # Check if we're viewing the video widget
        current_widget = self.media_stack.currentWidget()
        is_video_playing = current_widget in [self.qmedia_video_widget, self.vlc_video_player]
        
        # Space bar: pause/play video
        if event.key() == Qt.Key_Space and is_video_playing:
            self.toggle_play_pause()
        # F key: toggle fullscreen
        elif event.key() == Qt.Key_F:
            self.toggle_fullscreen()
        # Escape: close dialog
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.media_stack.currentWidget() == self.image_scroll_area:
            self.fit_image_to_window()

    def closeEvent(self, event):
        self.qmedia_player.stop()
        self.vlc_video_player.stop()
        if self.gif_movie:
            self.gif_movie.stop()
        
        self.threadpool.clear() # Stop any running workers
        self._cleanup_temp_video(wait_on_close=True)
        
        # If a cleanup thread was started for closing, wait for it to finish.
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=6.0) # Wait up to 6 seconds

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
            # Enma is initialized globally, so we just use the instance
            enma = self.parent_app.enma

            enma.source_manager.set_source(self.source_identifier)
            source = enma.source_manager.source
            source_meta = {"name": getattr(source, "name", None) or getattr(self.source_identifier, "name", str(self.source_identifier))}
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
                        res = _call_search_fn(search_fn, self.query.strip(), page)
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

class GelDanApp(QWidget):
    def __init__(self, is_incognito=False):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.is_incognito_window = is_incognito

        self.title_bar = MainWindowTitleBar(self)

        self.setObjectName("main_window")
        self.apply_window_settings()
        self.center_on_screen()

        # State
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
            self.enma = Enma()
            # Replace the default requests session with a cloudscraper session
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
        self.ai_chat_displayed_posts = {}  # Maps chat_index -> list of post IDs to display
        self.ai_chat_message_count = {}  # Tracks message count per chat for proper image positioning
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
            self.tabs.setCurrentIndex(1) # Start on browser tab for incognito
        else:
            self.tabs.setCurrentIndex(0) # Start on home tab
        
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

    def resizeEvent(self, event):
        """Override resize event to refresh grid if auto-scaling is on."""
        super().resizeEvent(event)
        if hasattr(self, 'tabs') and SETTINGS.get("auto_scale_grid", False):
            self.refresh_visible_grid()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.update_maximize_icon()
        super().changeEvent(event)

    def center_on_screen(self):
        """Centers the window on the primary screen."""
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
            # Check for Ctrl+Enter to send AI message
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
                try:
                    self.send_ai_message()
                except Exception as e:
                    QMessageBox.warning(self, _tr("Error"), _tr("Could not send message: {error}").format(error=str(e)))
                return True # Event handled

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
        else: # Fallback icon
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
            except Exception as e:
                print(f"Error processing media viewer queue: {e}")
                break

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
        testers_label = QLabel(_tr("69st and s4d_god (both on Discord)"))
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
            QMessageBox.critical(self, "Enma missing", "Enma package not installed or failed to initialize.")
        else:
            QTimer.singleShot(100, self.populate_manga_sources)

        return widget

    def create_hentai_tab(self):
        """Creates the UI for the Hentai Haven tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if not hhaven:
            label = QLabel(_tr("<h2>Hentai Haven integration requires the 'aiocache' library.</h2>"
                               "<p>Please install it by running: <b>pip install aiocache</b></p>"))
            label.setAlignment(Qt.AlignCenter)
            label.setOpenExternalLinks(True)
            layout.addWidget(label)
            return widget

        # Search controls
        controls_group = QGroupBox(_tr("Search Hentai Haven"))
        controls_layout = QHBoxLayout(controls_group)
        self.hentai_search_input = QLineEdit()
        self.hentai_search_input.setPlaceholderText(_tr("Search for tags, title, etc..."))
        self.hentai_search_input.returnPressed.connect(self.search_hentai)
        self.hentai_search_btn = QPushButton(qta.icon('fa5s.search'), _tr(" Search"))
        self.hentai_search_btn.clicked.connect(self.search_hentai)
        self.hentai_random_btn = QPushButton(qta.icon('fa5s.random'), _tr(" Random"))
        self.hentai_random_btn.clicked.connect(self.random_hentai)

        controls_layout.addWidget(self.hentai_search_input)
        controls_layout.addWidget(self.hentai_search_btn)
        controls_layout.addWidget(self.hentai_random_btn)
        layout.addWidget(controls_group)

        # Results grid
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

        return widget

    def search_hentai(self):
        """Initiates a search on Hentai Haven."""
        query = self.hentai_search_input.text().strip()
        if not query: return
        self.hentai_status_label.setText(_tr("Searching..."))
        worker = AsyncApiWorker(_do_hhaven_search, query)
        worker.signals.finished.connect(self.on_hentai_search_finished)
        self.threadpool.start(worker)

    def random_hentai(self):
        """Fetches a random video from Hentai Haven."""
        self.hentai_status_label.setText(_tr("Fetching random video..."))
        worker = AsyncApiWorker(_do_hhaven_random)
        worker.signals.finished.connect(self.on_hentai_search_finished)
        self.threadpool.start(worker)

    def on_hentai_search_finished(self, results, err):
        """Populates the grid with results from Hentai Haven."""
        self.clear_grid(self.hentai_grid)
        self.hentai_post_to_widget_map.clear()
        if err:
            self.hentai_status_label.setText(_tr("Error: {error}").format(error=err))
            QMessageBox.critical(self, _tr("Hentai Haven Error"), err)
            return
        
        posts = [self._adapt_hhaven_to_post(h) for h in results]
        if not posts:
            self.hentai_status_label.setText(_tr("No results found."))
        else:
            self.hentai_status_label.setText(_tr("Loaded {count} results.").format(count=len(posts)))

        self.populate_grid(self.hentai_grid, posts, self.hentai_post_to_widget_map, self.on_hentai_thumbnail_clicked, viewport_width=self.hentai_scroll.viewport().width())

    def on_hentai_thumbnail_clicked(self, post: dict, widget: ThumbnailWidget):
        """Scrapes the series page and opens a dialog with episode info."""
        hentai_obj = post.get("hh_object")
        if not hentai_obj: return

        widget.set_text(_tr("Loading..."))
        worker = AsyncApiWorker(_scrape_hhaven_series_page, hentai_obj)
        def on_finished(series_data, err):
            widget.set_text("")
            if err:
                QMessageBox.critical(self, "Error", f"Could not load series page:\n{err}")
            else:
                dialog = HentaiSeriesDialog(series_data, self); self.open_dialogs.append(dialog); dialog.show()
        worker.signals.finished.connect(on_finished)
        self.threadpool.start(worker)

    def _adapt_hhaven_to_post(self, hentai_obj):
        """Converts an hhaven.Hentai object to the app's internal post dictionary format."""
        return {
            "id": f"hh_{hentai_obj.id}",
            "preview_url": hentai_obj.thumbnail,
            "file_url": None, # No direct file URL
            "rating": "explicit",
            "score": hentai_obj.rating.votes,
            "tags": ", ".join([tag.name for tag in hentai_obj.tags]),
            "source_post_url": f"https://hentaihaven.xxx/watch/{hentai_obj.name}",
            "hh_object": hentai_obj, # Store the full object for later use
            "file_ext": "mp4" # Assume video
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

        try:
            if fetch_all or "Gelbooru" in enabled_sources:
                _, count = gelbooru_posts('', 0, 0)
                if isinstance(count, int): total += count
        except Exception: has_error = True; print("Failed to get Gelbooru count.")

        try:
            if fetch_all or "Danbooru" in enabled_sources:
                from snekbooru_linux.common.constants import DANBOORU_COUNTS_POSTS
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
            # Use PNG digit images if available, otherwise use text
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

        self.prev_btn.clicked.connect(self.prev_page) # This should call search, not start_new_search
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

        # Left pane for chat list and preset management
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_pane.setMaximumWidth(300)

        # Chat list
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

        # Preset management
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

        # Right pane for chat interface and personalization
        right_tabs = QTabWidget()
        
        # Chat Tab
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)

        # This stack will hold either the chat tabs or the welcome message
        self.ai_chat_area_stack = QStackedWidget()

        # The QTabWidget for the actual chats
        self.ai_chat_tabs = QTabWidget()
        self.ai_chat_tabs.setTabsClosable(False)
        self.ai_chat_tabs.setMovable(True)
        self.ai_chat_area_stack.addWidget(self.ai_chat_tabs)

        # The "Get Started" message widget
        self.ai_no_chats_widget = QWidget()
        no_chats_layout = QVBoxLayout(self.ai_no_chats_widget)
        no_chats_layout.setAlignment(Qt.AlignCenter)
        no_chats_label = QLabel(_tr("<h2>Send a message to begin a conversation!</h2>"))
        no_chats_label.setAlignment(Qt.AlignCenter)
        no_chats_label.setStyleSheet("color: #888;")
        no_chats_layout.addWidget(no_chats_label)
        self.ai_chat_area_stack.addWidget(self.ai_no_chats_widget)

        chat_layout.addWidget(self.ai_chat_area_stack)

        # Shared input area, moved outside the tab widget
        self.ai_shared_input_area = QPlainTextEdit()
        self.ai_shared_input_area.setObjectName("ai_chat_input_area")
        self.ai_shared_input_area.setPlaceholderText(_tr("Type your message here... Press Ctrl+Enter to send."))
        self.ai_shared_input_area.setMaximumHeight(120)
        self.ai_input_areas.append(self.ai_shared_input_area) # Add to list for event filter
        self.ai_shared_input_area.installEventFilter(self)

        self.ai_shared_send_button = QPushButton(qta.icon('fa5s.paper-plane'), _tr("Send"))
        self.ai_shared_send_button.clicked.connect(self.send_ai_message)

        chat_layout.addWidget(self.ai_shared_input_area)
        chat_layout.addWidget(self.ai_shared_send_button)
        # Personalization Tab
        personalization_group = QGroupBox(_tr("Personalization"))
        personalization_layout = QFormLayout(personalization_group)
        self.ai_name_edit = QLineEdit() # This will now be part of the personalization tab
        self.ai_persona_edit = QPlainTextEdit()
        
        # Provider selector
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["OpenRouter", "Google Gemini (Experimental)"])
        self.ai_provider_combo.currentTextChanged.connect(self.on_ai_provider_changed)
        
        self.ai_model_edit = QLineEdit()
        self.ai_gemini_model_combo = QComboBox()
        self.ai_gemini_model_combo.addItems([
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-pro"
        ])
        self.ai_gemini_model_combo.setVisible(False)
        self.ai_allow_spicy_check = QCheckBox(_tr("Allow 'spicy' or suggestive content"))
        
        personalization_layout.addRow(_tr("Name:"), self.ai_name_edit)
        personalization_layout.addRow(_tr("System Prompt / Persona:"), self.ai_persona_edit)
        personalization_layout.addRow(_tr("AI Provider:"), self.ai_provider_combo)
        personalization_layout.addRow(_tr("Model:"), self.ai_model_edit)
        personalization_layout.addRow(_tr("Gemini Model:"), self.ai_gemini_model_combo)
        personalization_layout.addRow(self.ai_allow_spicy_check)

        # Sliders
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

        # Post Showdown (Score Guesser)
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
        elif self.tabs.widget(index) == self.hentai_tab and hasattr(self, 'hentai_grid') and self.hentai_grid.count() == 0:
            self.random_hentai()

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
        if "nhentai.net/g/" in str(url):
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
        supports_download = bool(url) and (("nhentai.net/g/" in str(url)) or ("mangadex.org/title/" in str(url)))
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

        if "nhentai.net/g/" in str(url):
            spec = {"kind": "nhentai", "url": str(url)}
            dialog = MangaDownloadExportDialog(self, title=title, source_label="NHENTAI", download_spec=spec)
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

        if "nhentai.net/g/" in str(url):
            gid = parse_gallery_id(url)
            if not gid:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not parse gallery ID."))
                return

            out_dir = snekbooru_temp_dir("manga", "nhentai", str(gid))
            os.makedirs(out_dir, exist_ok=True)

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
                QDesktopServices.openUrl(QUrl.fromLocalFile(out_dir))
            except Exception:
                pass

        if open_reader:
            title = entry.get("title") or result.get("title") or "Manga"
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
        self.manga_sources = [s for s in Sources if 'manganato' not in str(s).lower()]
        all_item = QListWidgetItem("All")
        all_item.setData(Qt.UserRole, "ALL")
        self.manga_source_list.addItem(all_item)
        for s in self.manga_sources:
            title = getattr(s, "name", str(s))
            w = QListWidgetItem(title)
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
                for e in self.manga_search_cache.get((s, active_q), []):
                    aggregates.append((name, e))
                    if len(aggregates) >= 50:
                        break
                if len(aggregates) >= 50:
                    break
        else:
            for s, entries in self.manga_entries_cache.items():
                name = getattr(s, "name", str(s))
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

    def on_manga_thumb_loaded(self, pixmap, post_data):
        widget = post_data.get("widget")
        url = post_data.get("url")
        if url and not pixmap.isNull():
            self.manga_thumb_cache[url] = pixmap
        if widget and not pixmap.isNull():
            widget.set_thumbnail(pixmap)

    def on_manga_cover_loaded(self, pixmap, post_data):
        widget = post_data.get("widget")
        if widget and not pixmap.isNull(): # This is for manga covers
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
        # Ensure Uncategorized is always first
        if "Uncategorized" in self.favorites:
            self.fav_category_list.addItem("Uncategorized")
        
        for category in sorted(self.favorites.keys()):
            if category != "Uncategorized":
                self.fav_category_list.addItem(category)
        
        # Select the previously selected or default category
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

        # This can be a long operation, should be done in a worker thread in a real app
        # For now, we'll do it synchronously with a message box
        QMessageBox.information(self, _tr("Importing"), _tr("Importing files... The app may freeze."))
        
        imported_count = 0
        for filename in os.listdir(dir_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')):
                file_path = os.path.join(dir_path, filename)
                # Create a mock post object
                mock_post = {
                    "id": f"local_{filename}",
                    "file_url": f"file:///{file_path}",
                    "source_post_url": f"file:///{file_path}",
                    "tags": "local_import",
                    "file_ext": filename.split('.')[-1].lower(),
                    "local_path": file_path,
                    "local_thumbnail_path": None # No thumb for local imports yet
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
        """Toggle between OpenRouter and Gemini model fields."""
        is_gemini = provider == "Google Gemini (Experimental)"
        self.ai_model_edit.setVisible(not is_gemini)
        self.ai_gemini_model_combo.setVisible(is_gemini)

    def load_ai_preset_settings(self, index):
        presets = SETTINGS.get("ai_presets", [])
        if 0 <= index < len(presets):
            preset = presets[index]
            self.ai_name_edit.setText(preset.get("name", ""))
            self.ai_persona_edit.setPlainText(preset.get("persona", ""))
            
            # Set provider
            provider = preset.get("provider", "OpenRouter")
            self.ai_provider_combo.blockSignals(True)
            self.ai_provider_combo.setCurrentText(provider)
            self.ai_provider_combo.blockSignals(False)
            
            # Update model display based on provider
            self.on_ai_provider_changed(provider)
            
            self.ai_model_edit.setText(preset.get("model", ""))
            
            # Set Gemini model if applicable
            if provider == "Google Gemini (Experimental)":
                gemini_model = preset.get("model", "gemini-2.0-flash")
                idx = self.ai_gemini_model_combo.findText(gemini_model)
                if idx >= 0:
                    self.ai_gemini_model_combo.setCurrentIndex(idx)
            
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
            
            # Save the appropriate model based on selected provider
            if self.ai_provider_combo.currentText() == "Google Gemini (Experimental)":
                preset["model"] = self.ai_gemini_model_combo.currentText()
            else:
                preset["model"] = self.ai_model_edit.text()
            
            preset["allow_spicy"] = self.ai_allow_spicy_check.isChecked()
            preset["formal_casual"] = self.ai_formal_casual_slider.value()
            preset["helpful_sassy"] = self.ai_helpful_sassy_slider.value()
            preset["concise_verbose"] = self.ai_concise_verbose_slider.value()
            preset["creativity"] = self.ai_creativity_slider.value()
            
            save_settings(SETTINGS)
            self.populate_ai_presets() # Refresh combo box text
            QMessageBox.information(self, _tr("Preset Saved"), _tr("AI preset '{name}' has been updated.").format(name=preset["name"]))

    def new_ai_preset(self):
        from snekbooru_linux.common.constants import DEFAULT_AI_MODEL
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

        for i, chat in enumerate(SETTINGS.get("ai_chats", [])):
            self.ai_chat_list.addItem(chat["name"])
            self.add_ai_chat_tab(chat["name"], chat["history"])

        active_chat_index = SETTINGS.get("ai_active_chat_index", 0)
        if 0 <= active_chat_index < self.ai_chat_list.count():
            self.ai_chat_list.setCurrentRow(active_chat_index)
            self.ai_chat_tabs.setCurrentIndex(active_chat_index)
        
        if self.ai_chat_list.count() == 0:
            self.ai_chat_area_stack.setCurrentWidget(self.ai_no_chats_widget)
        else:
            self.ai_chat_area_stack.setCurrentWidget(self.ai_chat_tabs)

    def add_ai_chat_tab(self, name, history):
        from PyQt5.QtWidgets import QTextBrowser
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        history_browser = QTextBrowser()
        history_browser.setOpenExternalLinks(False)
        history_browser.anchorClicked.connect(self.on_chat_anchor_clicked)
        history_browser.setObjectName("ai_chat_history_browser")

        layout.addWidget(history_browser)

        self.ai_chat_tabs.addTab(tab, name)
        
        # Store the browser - we'll rebuild display from SETTINGS as source of truth
        tab_index = self.ai_chat_tabs.indexOf(tab)
        self.ai_chat_ui[tab_index] = {
            "history_browser": history_browser
        }
        
        # Populate history from SETTINGS
        self._rebuild_chat_display(tab_index)

    def _rebuild_chat_display(self, chat_index):
        """Rebuild the entire chat display from SETTINGS (source of truth)."""
        if chat_index not in self.ai_chat_ui:
            return
        
        history_browser = self.ai_chat_ui[chat_index]["history_browser"]
        history_browser.clear()  # Start fresh
        
        # Get the chat history from SETTINGS
        chats = SETTINGS.get("ai_chats", [])
        if chat_index < len(chats):
            history = chats[chat_index].get("history", [])
            
            import markdown
            for message in history:
                role = "You" if message['role'] == 'user' else 'AI'
                html_content = markdown.markdown(message['content'], extensions=['fenced_code', 'codehilite'])
                history_browser.append(f"<b>{role}:</b><br>{html_content}<hr>")
        
        # Restore displayed images/posts if they exist for this chat
        if chat_index in self.ai_chat_displayed_posts:
            for image_entry in self.ai_chat_displayed_posts[chat_index]:
                post = image_entry.get('post', {})
                image_data = image_entry.get('image_data', '')
                
                if image_data:
                    file_ext = post.get('file_ext', '').lower()
                    is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
                    
                    # Add a video/gif indicator if applicable
                    video_badge = ""
                    if is_video:
                        video_badge = " <span style='position: relative; top: -145px; left: 125px; background: rgba(0,0,0,0.7); color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;'>▶ Video</span>"
                    
                    html = f"<a href='post:{post['id']}'><img src='data:image/png;base64,{image_data}' height='150' style='margin: 2px; border-radius: 4px; cursor: pointer;' />{video_badge}</a>"
                    history_browser.append(html)
                    # Store post data for anchor click handling
                    self.ai_search_results[post['id']] = post
        
        # Ensure we're at the bottom
        history_browser.moveCursor(QTextCursor.End)
        history_browser.ensureCursorVisible()

    def switch_ai_chat(self, current, previous):
        if current:
            index = self.ai_chat_list.row(current)
            self.ai_chat_tabs.setCurrentIndex(index)
            SETTINGS["ai_active_chat_index"] = index
            # Rebuild display from source of truth
            self._rebuild_chat_display(index)

    def new_ai_chat(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, _tr("New Chat"), _tr("Enter chat name:"))
        if ok and name:
            SETTINGS["ai_chats"].append({"name": name, "history": []})
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
        
        # Also clean up displayed posts for this chat
        if active_index in self.ai_chat_displayed_posts:
            del self.ai_chat_displayed_posts[active_index]
        
        # If we deleted the last chat, set index to -1, otherwise select the first one.
        if not SETTINGS.get("ai_chats"):
            SETTINGS["ai_active_chat_index"] = -1
        else:
            SETTINGS["ai_active_chat_index"] = 0
            
        save_settings(SETTINGS)
        # This will re-render the UI, showing the new chat tab
        self.populate_ai_chats()

    def send_ai_message(self):
        active_index = self.ai_chat_tabs.currentIndex()

        # If no chats exist, create one first
        if active_index < 0 and not SETTINGS.get("ai_chats"):
            SETTINGS["ai_chats"] = [{"name": "Chat 1", "history": []}]
            SETTINGS["ai_active_chat_index"] = 0
            save_settings(SETTINGS)
            self.populate_ai_chats() # This will create and switch to the new tab
            active_index = 0 # The new chat is at index 0

        if active_index < 0: return
        chat_index = active_index

        ui = self.ai_chat_ui[active_index]
        user_message = self.ai_shared_input_area.toPlainText().strip()

        if not self.ai_can_send:
            ui["history_browser"].append(f"<b style='color:orange;'>{_tr('Please wait a moment before sending another message.')}</b><hr>")
            return

        if not user_message: return

        # Disable input and start cooldown
        self.ai_shared_input_area.setEnabled(False)
        self.ai_shared_send_button.setEnabled(False)
        self.ai_can_send = False

        # Update UI immediately
        import markdown
        ui["history_browser"].append(f"<b>You:</b><br>{markdown.markdown(user_message)}<hr>")
        self.ai_shared_input_area.clear()

        # Update data store for the current chat
        chat_history = SETTINGS["ai_chats"][active_index]["history"]
        chat_history.append({"role": "user", "content": user_message})

        # Prepare messages for API
        active_preset = SETTINGS["ai_presets"][SETTINGS["ai_active_preset_index"]]
        
        system_prompt = active_preset["persona"]
        pref_tags = SETTINGS.get("preferred_tags", "").replace("\n", ", ")
        system_prompt += f"\n\n[SYSTEM]\nYou have access to an image database. To search/show an image, output: {{SEARCH: tag1 tag2}}\nUser's preferred tags: {pref_tags}\nUse standard booru tags (space separated)."
        messages = [{"role": "system", "content": system_prompt}] + chat_history # Send the whole history

        # Start worker
        worker = AIStreamWorker(messages, temperature=active_preset["creativity"] / 100.0)
        worker.signals.chunk.connect(lambda chunk: self.on_ai_chunk_received(chunk, active_index))
        worker.signals.finished.connect(lambda full_response: self.on_ai_finished(full_response, active_index))
        worker.signals.error.connect(self.on_ai_error)
        self.threadpool.start(worker)

        # Add a placeholder for AI response
        ui["history_browser"].append("<b>AI:</b><br>")

    def on_ai_chunk_received(self, chunk, chat_index):
        if chat_index == self.ai_chat_tabs.currentIndex():
            ui = self.ai_chat_ui[chat_index]
            # To preserve whitespace from the stream, we must convert it to HTML entities.
            html_chunk = chunk.replace(' ', '&nbsp;').replace('\n', '<br>')
            cursor = ui["history_browser"].textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertHtml(html_chunk)
            ui["history_browser"].moveCursor(QTextCursor.End)

    def on_ai_finished(self, full_response, chat_index):
        # Update data store with the full response
        SETTINGS["ai_chats"][chat_index]["history"].append({"role": "assistant", "content": full_response})
        save_settings(SETTINGS)

        # To properly format the final response, we need to re-render the last two messages
        ui = self.ai_chat_ui[chat_index]
        history = SETTINGS["ai_chats"][chat_index]["history"]
        
        search_match = re.search(r'\{+SEARCH: (.*?)\}+', full_response, re.DOTALL)
        if search_match:
            tags = search_match.group(1).replace('\n', ' ').strip()
            self.perform_ai_image_search(tags, chat_index)

        # This is complex, a simpler way for now is to just append the final formatted message
        # A full re-render would be better
        # For now, we just add the closing hr tag
        ui["history_browser"].append("<hr>")

        # Start cooldown timer before re-enabling
        self.ai_cooldown_timer.singleShot(2000, lambda: self.reset_ai_cooldown(chat_index))

    def perform_ai_image_search(self, tags, chat_index, is_fallback=False, original_tags=None, retry_count=0):
        ui = self.ai_chat_ui[chat_index]
        if not is_fallback:
            ui["history_browser"].append(f"<i>Searching database for: {tags}...</i><br>")
            original_tags = tags
        
        # Detect if user explicitly requests adult content
        tags_lower = tags.lower()
        explicit_keywords = [
            'porn', 'hentai', 'xxx', 'nsfw', 'explicit', 'adult',
            'nude', 'naked', 'sex', 'erotic', 'horny', 'tentacle',
            'rape', 'yaoi', 'yuri', 'futanari', 'futa', 'incest',
            'anal', 'cum', 'cock', 'pussy', 'dick', 'dildo', 'vibrator'
        ]
        
        has_explicit_request = any(keyword in tags_lower for keyword in explicit_keywords)
        
        # Add NSFW filter by default UNLESS user explicitly requests adult content
        search_tags = tags
        if not has_explicit_request and 'rating:' not in tags_lower:
            # Add safe rating filter by default only if no explicit request
            search_tags = f"{tags} rating:safe" if tags.strip() else "rating:safe"
        
        # Detect which source the user wants
        detected_sources = detect_source_from_query(tags)
        
        # Check for media type preference (gif, video, webm, mp4, etc.)
        media_preference = None
        if any(ext in tags_lower for ext in ['gif', 'video', 'webm', 'mp4', 'animated']):
            media_preference = 'video'
        elif any(ext in tags_lower for ext in ['png', 'jpg', 'jpeg', 'image', 'static']):
            media_preference = 'image'
        
        enabled_sources = detected_sources
        worker = ApiWorker(fetch_multiple_sources, enabled_sources, search_tags, 1, 0, self.custom_boorus)
        worker.signals.finished.connect(lambda data, err: self.on_ai_search_results(data, err, chat_index, media_preference, original_tags, retry_count))
        self.threadpool.start(worker)

    def on_ai_search_results(self, data, err, chat_index, media_preference=None, original_tags=None, retry_count=0):
        ui = self.ai_chat_ui[chat_index]
        if err:
            ui["history_browser"].append(f"<b style='color:red;'>Search Error: {err}</b><br>")
            return

        posts, _ = data
        if not posts:
            # Fallback: retry with simplified search terms if we haven't already
            if original_tags is None:
                original_tags = ""  # Will be set by perform_ai_image_search
            
            # Try fallback searches: remove modifiers and retry
            fallback_searches = []
            if retry_count == 0 and original_tags:
                # First fallback: remove " different", " another", etc.
                fallback = original_tags.replace(" different", "").replace(" another", "").replace(" alt ", " ").strip()
                if fallback and fallback != original_tags:
                    fallback_searches.append(fallback)
                
                # Second fallback: take only the first word
                first_word = original_tags.split()[0] if original_tags.split() else ""
                if first_word and first_word != fallback:
                    fallback_searches.append(first_word)
            
            # If we have fallback searches, try them
            if fallback_searches:
                ui["history_browser"].append(f"<i>No results for '{original_tags}', trying: {fallback_searches[0]}...</i><br>")
                self.perform_ai_image_search(fallback_searches[0], chat_index, is_fallback=True, original_tags=original_tags, retry_count=retry_count+1)
                return
            
            # Ultimate fallback: search for popular anime characters
            ui["history_browser"].append(f"<i>No images found, showing popular anime...</i><br>")
            self.perform_ai_image_search("anime girl", chat_index, is_fallback=True, original_tags=original_tags, retry_count=retry_count+1)
            return

        # Track the message index where search results begin
        if chat_index not in self.ai_chat_message_count:
            self.ai_chat_message_count[chat_index] = len(SETTINGS.get("ai_chats", [{}])[chat_index].get("history", []))
        message_index = self.ai_chat_message_count[chat_index]
        
        # Load thumbnails asynchronously and display them
        html = "<div style='margin-top: 5px;' id='ai_search_results'>"
        html += "</div><br>"
        
        ui["history_browser"].append(html)
        ui["history_browser"].moveCursor(QTextCursor.End)
        
        # Load only the first thumbnail asynchronously
        if posts:
            post = posts[0]  # Only use the first result
            self.ai_search_results[post['id']] = post
            preview = post.get('preview_url')
            file_url = post.get('file_url')
            file_ext = post.get('file_ext', '').lower()
            
            # Check if it's a video/GIF based on file extension
            is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
            
            if preview:
                # Use ImageWorker to load the thumbnail
                worker = ImageWorker(preview, post)
                worker.signals.finished.connect(lambda pix, p=post, idx=chat_index, msg_idx=message_index: self.on_ai_thumbnail_loaded(pix, p, idx, msg_idx))
                self.threadpool.start(worker)

    def on_ai_thumbnail_loaded(self, pixmap, post, chat_index, message_index=None):
        """Inserts a loaded thumbnail into the AI chat results at the correct position."""
        if pixmap.isNull() or chat_index not in self.ai_chat_ui:
            return
        
        ui = self.ai_chat_ui[chat_index]
        history_browser = ui["history_browser"]
        
        # Convert pixmap to base64 for embedding in HTML
        from PyQt5.QtCore import QBuffer, QIODevice
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        image_data = base64.b64encode(buffer.data()).decode()
        
        # Track this post for persistence with its message index
        if chat_index not in self.ai_chat_displayed_posts:
            self.ai_chat_displayed_posts[chat_index] = []
        self.ai_chat_displayed_posts[chat_index].append({
            'post_id': post['id'],
            'image_data': image_data,
            'post': post,
            'message_index': message_index  # Track which message this image belongs to
        })
        
        file_ext = post.get('file_ext', '').lower()
        is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
        
        # Add a video/gif indicator if applicable
        video_badge = ""
        if is_video:
            video_badge = " <span style='position: relative; top: -145px; left: 125px; background: rgba(0,0,0,0.7); color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;'>▶ Video</span>"
        
        html = f"<a href='post:{post['id']}'><img src='data:image/png;base64,{image_data}' height='150' style='margin: 2px; border-radius: 4px; cursor: pointer;' />{video_badge}</a>"
        history_browser.append(html)
        
        # Ensure the widget is visible and updated
        history_browser.moveCursor(QTextCursor.End)
        history_browser.ensureCursorVisible()
        history_browser.update()

    def reset_ai_cooldown(self, chat_index):
        self.ai_can_send = True
        if chat_index in self.ai_chat_ui:
            ui = self.ai_chat_ui[chat_index]
            # Re-enable input
        self.ai_shared_input_area.setEnabled(True)
        self.ai_shared_send_button.setEnabled(True)
        self.ai_shared_input_area.setFocus()

    def on_ai_error(self, error_message):
        active_index = self.ai_chat_tabs.currentIndex()
        QMessageBox.critical(self, _tr("AI Error"), error_message)
        # We should also update the UI to show the error
        active_index = self.ai_chat_tabs.currentIndex()
        if active_index >= 0:
            ui = self.ai_chat_ui[active_index]
            ui["history_browser"].append(f"<b style='color:red;'>Error: {error_message}</b><hr>")
            
            # Re-enable input on error
            self.reset_ai_cooldown(active_index)
            self.ai_shared_input_area.setEnabled(True)
            self.ai_shared_send_button.setEnabled(True)
            self.ai_shared_input_area.setFocus()

    def on_chat_anchor_clicked(self, url):
        url_str = url.toString()
        if url_str.startswith("post:"):
            post_id = url_str.split(":")[1]
            post = self.ai_search_results.get(post_id)
            if post:
                # Open a custom AI post viewer dialog
                self.open_ai_post_viewer(post)
            else:
                QMessageBox.warning(self, _tr("Error"), _tr("Could not load post details."))
        else:
            webbrowser.open(url_str)

    def open_ai_post_viewer(self, post):
        """Open a custom dialog to view the AI-found post with options."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QPushButton
        from snekbooru_linux.ui.dialogs import CustomTitleBar
        
        dialog = QDialog(self)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.FramelessWindowHint)  # Remove default title bar
        dialog.setGeometry(100, 100, 900, 700)
        dialog.setModal(False)  # Non-modal to prevent blocking the main window
        
        # Add custom title bar
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(0, 0, 0, 0)  # No margins for title bar
        main_layout.setSpacing(0)
        title_bar = CustomTitleBar(dialog, _tr("Post Viewer"), has_icon=False)
        main_layout.addWidget(title_bar)
        
        # Content layout
        layout = QVBoxLayout()
        main_layout.addLayout(layout)
        
        # Create a scroll area for the media
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        media_widget = QWidget()
        media_layout = QVBoxLayout(media_widget)
        
        file_url = post.get('file_url')
        preview_url = post.get('preview_url')
        file_ext = post.get('file_ext', '').lower()
        
        # Determine media type and display accordingly
        is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi']
        
        if is_video and file_url:
            # For videos, show a play button and info
            video_info = QLabel(f"<b>Video Preview</b><br>Format: {file_ext.upper()}<br><a href='{file_url}'>Click here to view full video</a>")
            video_info.setOpenExternalLinks(True)
            media_layout.addWidget(video_info)
            
            if preview_url:
                try:
                    response = requests.get(preview_url, headers={'User-Agent': USER_AGENT}, timeout=10)
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
            # For images, display the preview
            if preview_url or file_url:
                url_to_load = preview_url or file_url
                try:
                    response = requests.get(url_to_load, headers={'User-Agent': USER_AGENT}, timeout=10)
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
        
        # Post info section
        info_text = f"<b>Post ID:</b> {post.get('id')}<br>"
        info_text += f"<b>Rating:</b> {post.get('rating', 'Unknown')}<br>"
        info_text += f"<b>Score:</b> {post.get('score', 'N/A')}<br>"
        if post.get('tags'):
            info_text += f"<b>Tags:</b> {post.get('tags', '')[:200]}..."
        
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Action buttons
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
        dialog.show()  # Non-blocking show instead of exec_()
        
        # Keep a reference to prevent garbage collection
        if not hasattr(self, '_open_dialogs'):
            self._open_dialogs = []
        self._open_dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._open_dialogs.remove(dialog) if dialog in self._open_dialogs else None)

    def _close_dialog_and_refocus(self, dialog):
        """Close dialog and refocus on the chat history."""
        dialog.close()
        # Rebuild the display from source of truth
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
            # By not adjusting the size of the grid host, the scroll area will correctly manage the width
            # and prevent horizontal scrollbars from appearing.
            grid_layout.parentWidget().setFixedWidth(viewport_width)
            target_thumb_size = SETTINGS.get("thumbnail_size", 150)
            spacing = grid_layout.spacing() # Usually 10

            # Calculate how many columns can fit based on the target size
            cols = max(2, int((viewport_width + spacing) / (target_thumb_size + spacing)))

            # Recalculate the actual thumbnail size to fill the width perfectly
            thumb_size = int((viewport_width - (cols - 1) * spacing) / cols)
        else:
            cols = SETTINGS.get("grid_columns", 5)
            thumb_size = SETTINGS.get("thumbnail_size", 150)

        for i, post in enumerate(posts):
            row, col = divmod(i, cols)
            thumb = ThumbnailWidget(post, thumb_size, self.favorites)
            thumb.clicked.connect(click_handler)
            thumb.doubleClicked.connect(self.open_post_full)
            thumb.selectionToggled.connect(self.toggle_bulk_selection)
            thumb.customContextMenuRequested.connect(lambda pos, p=post: self.show_thumbnail_context_menu(p, pos))
            
            grid_layout.addWidget(thumb, row, col)
            widget_map[post['id']] = thumb

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
        # Check all possible widget maps
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
        """
        Creates and shows a context-aware right-click menu for a thumbnail.
        The menu options change depending on the currently active tab.
        """
        menu = QMenu()
        active_tab = self.tabs.currentWidget()

        # --- Common Actions ---
        is_favorited = find_post_in_favorites(post.get('id'), self.favorites) is not None
        fav_text = _tr("Remove from Favorites") if is_favorited else _tr("Add to Favorites")
        fav_action = menu.addAction(qta.icon('fa5s.star', color='yellow' if is_favorited else None), fav_text)

        open_in_browser_action = menu.addAction(qta.icon('fa5s.external-link-alt'), _tr("Open Post in Browser"))
        menu.addSeparator()
        copy_tags_action = menu.addAction(qta.icon('fa5s.tags'), _tr("Copy Tags"))
        copy_image_url_action = menu.addAction(qta.icon('fa5s.link'), _tr("Copy Image URL"))

        # --- Tab-Specific Actions ---
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

        # Execute the menu and handle the chosen action
        chosen_action = menu.exec_(QCursor.pos())

        # --- Action Handlers ---
        if chosen_action is None:
            return

        # Common actions
        if chosen_action == fav_action:
            self.toggle_favorite(post)
        elif chosen_action == open_in_browser_action:
            if post.get("source_post_url"):
                webbrowser.open(post.get("source_post_url"))
        elif chosen_action == copy_tags_action:
            QApplication.clipboard().setText(post.get("tags", ""))
        elif chosen_action == copy_image_url_action:
            QApplication.clipboard().setText(post.get("file_url", ""))

        # Browser tab actions
        elif active_tab == self.browser_tab:
            if chosen_action == download_action:
                from snekbooru_linux.core.downloader import download_media
                self.download_post(post)
            elif chosen_action == reverse_search_action:
                self.last_selected = post
                self.reverse_search_selected()

        # Favorites tab actions
        elif active_tab == self.favorites_tab:
            if chosen_action and chosen_action.parent() == move_to_category_menu:
                target_category = chosen_action.data()
                current_category = find_post_in_favorites(post.get('id'), self.favorites)
                if current_category and current_category != target_category:
                    post_data = self.favorites[current_category].pop(post.get('id'))
                    self.favorites[target_category][post.get('id')] = post_data
                    save_favorites(self.favorites)
                    self.refresh_favorites_grid()

        # Downloads tab actions
        elif active_tab == self.downloads_tab:
            if chosen_action == open_in_viewer_action:
                self.open_post_full(post)
            elif chosen_action == open_file_action:
                file_path = post.get("local_path")
                if file_path:
                    # QDesktopServices is more cross-platform than os.startfile
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

    def start_new_search(self):
        """Initiates a new search, resetting the page to 0."""
        self.pid = 0
        self.search()

    def search(self):
        """Fetches posts for the current tags and page number (pid)."""
        tags = self.search_input.text().strip()
        if self.include_pref.isChecked():
            pref_tags = SETTINGS.get("preferred_tags", "").split()
            tags = " ".join(pref_tags) + " " + tags

        blacklisted_tags = SETTINGS.get("blacklisted_tags", "").split()
        
        if not SETTINGS.get("allow_loli_shota", False):
            blacklisted_tags.extend(["loli", "shota"])
        if not SETTINGS.get("allow_bestiality", False):
            blacklisted_tags.append("bestiality")
        if not SETTINGS.get("allow_guro", False):
            blacklisted_tags.append("guro")

        for tag in blacklisted_tags:
            if tag:
                tags += f" -{tag}"

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
        from snekbooru_linux.api.booru import filter_posts_by_blacklist
        
        self.progress.setVisible(False)
        self.clear_grid(self.grid)
        self.post_to_widget_map.clear()
        self.selected_for_bulk.clear()
        self.update_bulk_status()

        if err:
            self.status.setText(_tr("Error: {error}").format(error=err))
            return

        posts, total_count = data
        
        # Apply blacklist filtering (especially important for custom boorus that may not support API-level filtering)
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

    def next_page(self):
        self.pid += 1
        self.search() # Use search() to paginate

    def prev_page(self):
        if self.pid > 0:
            self.pid -= 1
            self.search() # Use search() to paginate

    def go_to_page(self):
        try:
            page = int(self.page_input.text())
            if page > 0:
                self.pid = page - 1
                self.search()
        except ValueError:
            pass # Ignore invalid input

    def random_post(self):
        self.status.setText(_tr("Fetching random post..."))
        # Use the current search tags for the random post, if any
        tags = self.search_input.text().strip()
        worker = ApiWorker(danbooru_random, tags)
        worker.signals.finished.connect(self.on_random_post_loaded)
        self.threadpool.start(worker)

    def on_random_post_loaded(self, post, err):
        if err:
            self.status.setText(_tr("Error fetching random post."))
            return
        
        # Instead of opening, display it in the grid
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
        
        # Also select it in the inspector
        self.on_thumbnail_clicked(post, self.post_to_widget_map.get(post['id']))

    def random_tag(self):
        self.status.setText(_tr("Fetching random tag..."))
        worker = ApiWorker(danbooru_random, "") # Fetch a random post to get tags from
        worker.signals.finished.connect(self.on_random_tag_loaded)
        self.threadpool.start(worker)

    def fetch_suggestions(self):
        """Fetch tag suggestions based on current search input."""
        search_text = self.search_input.text().strip()
        if not search_text or len(search_text) < 2:
            return
        
        # Fetch suggestions in background
        worker = ApiWorker(suggest_all_tags, search_text, 20)
        worker.signals.finished.connect(self.on_suggestions_loaded)
        self.threadpool.start(worker)

    def on_suggestions_loaded(self, suggestions, err):
        """Handle loaded tag suggestions."""
        if err or not suggestions:
            return
        
        # Update the completer with suggestions
        if isinstance(suggestions, list):
            self.search_completer_model.setStringList(suggestions)

    def suggest_tags_dialog(self):
        """Open a dialog to suggest tags based on search."""
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
        """Handle suggestion dialog result."""
        if err or not suggestions:
            self.status.setText(_tr("Error fetching tag suggestions."))
            return
        
        if not isinstance(suggestions, list):
            self.status.setText(_tr("No suggestions found."))
            return
        
        if not suggestions:
            self.status.setText(_tr("No tags matching your query."))
            return
        
        # Show selection dialog with suggestions
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
        if self.last_selected:
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
        from snekbooru_linux.common.constants import BORING_TAGS
        interesting_tags = [tag for tag in all_tags if tag not in BORING_TAGS and ":" not in tag]

        if not interesting_tags:
            interesting_tags = all_tags # Fallback if all tags were boring

        if interesting_tags:
            random_tag = random.choice(interesting_tags)
            self.search_input.setText(random_tag)
            self.start_new_search()

    def open_post_full(self, post):
        active_tab = self.tabs.currentWidget()
        if active_tab == self.browser_tab:
            posts_list = self.posts
        elif active_tab == self.favorites_tab:
            posts_list = list(self.favorites.get(self.current_favorites_category, {}).values())
        elif active_tab == self.hentai_tab:
            QMessageBox.information(self, _tr("Info"), _tr("Hentai Haven videos cannot be opened in the media viewer. They will open in the Manga tab instead.")); return
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

        # Use the multiprocessing viewer to avoid blocking the main window
        # and allow multiple viewers to be open at once.
        from snekbooru_linux.ui.media_viewer import launch_media_viewer_process
        p = Process(target=launch_media_viewer_process, args=(posts_list, current_index, self.favorites, SETTINGS, self.media_viewer_queue, self.custom_themes))
        p.start()
        self.media_viewer_processes.append(p)

    def download_selected(self):
        if self.last_selected: self.download_post(self.last_selected)

    def download_post(self, post):
        """Handles downloading a single post, showing a message box on completion."""
        from snekbooru_linux.core.downloader import download_media
        success, message = download_media(post, self)
        if success:
            if SETTINGS.get("show_download_notification", True):
                QMessageBox.information(self, _tr("Download Complete"), message)
            else:
                try:
                    self.status.setText(message)
                except Exception:
                    pass
        else:
            QMessageBox.warning(self, _tr("Download Failed"), message)

    def toggle_inspector_favorite(self):
        if self.last_selected:
            self.toggle_favorite(self.last_selected)

    def toggle_favorite(self, post):
        post_id = post.get('id')
        if not post_id: return

        category = find_post_in_favorites(post_id, self.favorites)
        if category:
            del self.favorites[category][post_id]
        else:
            self.favorites["Uncategorized"][post_id] = post
        
        save_favorites(self.favorites)
        self.update_inspector_fav_button(post)
        
        # Update thumbnail style if visible
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
        self.browser_content_tabs.setCurrentIndex(2) # Switch to reverse search tab
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
                from snekbooru_linux.core.downloader import download_media
                total = len(self.posts)
                for i, post in enumerate(self.posts):
                    if self.is_cancelled: break
                    self.progress.emit(i + 1, total, _tr("Downloading Post #{id}...").format(id=post.get('id')))
                    try:
                        download_media(post) # This function now handles all logic
                        self.progress.emit(i + 1, total, _tr("Saved Post #{id}").format(id=post.get('id')))
                    except Exception as e:
                        self.progress.emit(i + 1, total, _tr("Failed Post #{id}: {error}").format(id=post.get('id'), error=e))
                        time.sleep(0.1) # Avoid spamming UI
                self.finished.emit(_tr("Bulk download cancelled.") if self.is_cancelled else _tr("Bulk download complete."))

            def cancel(self): self.is_cancelled = True

        # Get full post objects from the selected IDs
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
        # Create a copy to iterate over as we are modifying the set
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
            self.search_history = self.search_history[:50] # Limit history size
            self.search_completer_model.setStringList(self.search_history)
            save_search_history(self.search_history)

    def clear_search_history(self):
        self.search_history.clear()
        self.search_completer_model.setStringList([])
        save_search_history([])
        QMessageBox.information(self, _tr("History Cleared"), _tr("Search history has been cleared."))

    def fetch_recommendations(self):
        self.reco_status_label.setText(_tr("Analyzing your favorites to find recommendations..."))
        
        tag_counts = {}
        for category in self.favorites.values():
            for post in category.values():
                for tag in post.get('tags', '').split():
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        from snekbooru_linux.common.constants import BORING_TAGS
        for tag in BORING_TAGS:
            tag_counts.pop(tag, None)

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
        old_lang = SETTINGS.get("language") # Get language before changes

        if dialog.exec_():
            new_settings = dialog.values()
            SETTINGS.update(new_settings)
            save_settings(SETTINGS)
            self.reapply_settings(old_lang) # Pass old language to compare against new one

    def reapply_settings(self, old_lang):
        """Applies all user-configurable settings instantly."""
        # Language change requires re-translating the entire UI
        if SETTINGS.get("language") != old_lang:
            self.retranslate_ui()

        self.apply_theme()
        self.load_hotkeys()
        self._configure_temp_cleanup_timer()
        self.update_source_label()
        self.apply_window_settings()
        self.apply_potato_mode()

        # Clear and repopulate grids to reflect changes
        self.clear_grid(self.grid)
        self.clear_grid(self.fav_grid)

        # Repopulate grids to reflect changes in column count or thumbnail size
        self.on_posts_loaded((self.posts, 0), None) # Repopulate browser grid
        self.refresh_favorites_grid()
        self.refresh_downloads_grid()

    def refresh_visible_grid(self):
        """Refreshes the grid of the currently visible tab."""
        current_tab = self.tabs.currentWidget()
        if current_tab == self.browser_tab:
            self.on_posts_loaded((self.posts, 0), None)
        elif current_tab == self.favorites_tab:
            self.refresh_favorites_grid()

    def retranslate_ui(self):
        """Dynamically re-translates all static text in the UI."""
        # Main Window
        self.title_bar.title_label.setText(_tr("Snekbooru (Incognito)") if self.is_incognito_window else _tr("Snekbooru"))
        self.limit.setSuffix(_tr(" posts"))
        self.limit.setToolTip(_tr("Number of posts to load per page."))
        self.source_title_label.setText(_tr("Source:"))
        self.settings_btn.setText(_tr(" Settings"))

        # Tabs
        self.tabs.setTabText(self.tabs.indexOf(self.home_tab), _tr("Home"))
        self.tabs.setTabText(self.tabs.indexOf(self.browser_tab), _tr("Browser"))
        self.tabs.setTabText(self.tabs.indexOf(self.favorites_tab), _tr("Favorites"))
        self.tabs.setTabText(self.tabs.indexOf(self.downloads_tab), _tr("Downloads"))
        self.tabs.setTabText(self.tabs.indexOf(self.manga_tab), _tr("Manga"))
        self.tabs.setTabText(self.tabs.indexOf(self.minigames_tab), _tr("Minigames"))
        self.tabs.setTabText(self.tabs.indexOf(self.ai_tab), _tr("AI"))

        # Home Tab
        self.home_title.setText(_tr("Welcome to Snekbooru"))
        self.home_subtitle.setText(_tr("Total posts available from supported sources:"))
        self.disclaimer_label.setText(_tr("(Note: Gelbooru & Danbooru totals are only accurate with an API key. Other counts are scraped.)"))
        self.home_refresh_btn.setText(_tr(" Refresh Stats"))
        self.credits_group.setTitle(_tr("Credits"))

        # Browser Tab
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
        self.inspector_fav_btn.setText(_tr(" Favorite")) # Will be updated by logic
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

        # Favorites Tab
        self.fav_category_group.setTitle(_tr("Categories"))
        self.new_cat_btn.setText(_tr(" New"))
        self.rename_cat_btn.setText(_tr(" Rename"))
        self.delete_cat_btn.setText(_tr(" Delete"))
        self.fav_refresh_btn.setText(_tr(" Refresh Grid"))
        self.fav_search_filter_label.setText(_tr("Filter:"))
        self.fav_search_input.setPlaceholderText(_tr("Filter by tags..."))
        self.fav_insp_group.setTitle(_tr("Post Inspector"))

        # Manga Tab
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
        """Disables or enables features based on Potato Mode setting."""
        is_potato = SETTINGS.get("potato_mode", False)
        
        # Disable expensive features
        self.suggest_btn.setVisible(not is_potato)
        self.browser_content_tabs.setTabVisible(1, not is_potato) # Hide Recommendations tab

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
        
        # Re-apply style to custom title bar buttons after theme change
        for btn in [self.title_bar.minimize_btn, self.title_bar.maximize_btn, self.title_bar.close_btn]:
            btn.style().unpolish(btn); btn.style().polish(btn)
        self.title_bar.update_icons()

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

        super().closeEvent(event)
    
    def apply_window_settings(self):
        """Applies window size and mode from settings."""
        mode = SETTINGS.get("window_mode", "Windowed")

        self.showNormal() # Exit fullscreen if active

        if mode == _tr("Fullscreen"):
            self.title_bar.hide()
            self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint) # Use native fullscreen
            self.showFullScreen()
            return # Fullscreen handles its own size
        elif mode == _tr("Windowed Borderless"):
            self.title_bar.hide()
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            screen_rect = QApplication.desktop().screenGeometry()
            self.setGeometry(screen_rect) # Set to max resolution
        else: # "Windowed"
            self.title_bar.show()
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
            # Set window size from presets
            size_preset = SETTINGS.get("window_size_preset", "1600x900")
            if size_preset == _tr("Custom"):
                width = SETTINGS.get("custom_window_width", 1820)
                height = SETTINGS.get("custom_window_height", 1080)
            else:
                try:
                    width, height = map(int, size_preset.split(' ')[0].split('x'))
                except ValueError:
                    width, height = 1820, 1080 # Fallback
            self.resize(width, height)
            self.center_on_screen()

        self.show() # Show the window after all settings are applied

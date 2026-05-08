import re
from typing import Optional
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineSettings
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QVBoxLayout,
                             QWidget)

from snekbooru.core.config import SETTINGS, find_post_in_favorites


class HentaiWebPage(QWebEnginePage):
    """
    Custom WebEnginePage that enables JavaScript and disables Content Security Policy
    to allow video players on sites like Hentai Haven to function correctly.
    """
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.CspEnabled, False)

class ImageDropLabel(QLabel):
    """A QLabel that accepts image drops."""
    image_changed = pyqtSignal(QPixmap) # Signal that emits the new pixmap

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #888;
                border-radius: 5px;
                padding: 10px;
                color: #888;
            }
            QLabel:hover {
                border-color: #5b5bff;
                color: #eaeaea;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        pixmap = None
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            pixmap = QPixmap(event.mimeData().urls()[0].toLocalFile())
        elif event.mimeData().hasImage():
            pixmap = QPixmap(event.mimeData().imageData())
        
        if pixmap and not pixmap.isNull():
            self.image_changed.emit(pixmap)

class MangaListItem(QWidget):
    def __init__(self, title: str, source_name: str, thumb_pixmap: Optional[QPixmap], url: Optional[str]):
        super().__init__()
        self.url = url
        self.source_name = source_name
        layout = QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(90, 120)
        self.thumb_label.setStyleSheet("background: #111; border: 1px solid #333;")
        if thumb_pixmap:
            pm = thumb_pixmap.scaled(90, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_label.setPixmap(pm)
        else:
            self.thumb_label.setText("No\nImage")
            self.thumb_label.setAlignment(Qt.AlignCenter)
        v = QVBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: bold;")
        self.source_label = QLabel(f"[{source_name}]")
        self.source_label.setStyleSheet("color: #888; font-size: 11px;")
        v.addWidget(self.title_label)
        v.addWidget(self.source_label)
        layout.addWidget(self.thumb_label)
        layout.addLayout(v)
        self.setLayout(layout)

    def set_thumbnail(self, pixmap: QPixmap):
        pm = pixmap.scaled(90, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.thumb_label.setPixmap(pm)

    def set_title(self, title: str):
        self.title_label.setText(title)

class AdBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.blocked_domains = {
            'doubleclick.net', 'googlesyndication.com', 'google-analytics.com',
            'adnxs.com', 'advertising.com', 'adtechus.com', 'quantserve.com',
            'scorecardresearch.com', 'zedo.com', 'adbrite.com', 'adbureau.net',
            'targetspot.com', 'nexac.com', 'yieldmanager.com', 'addthis.com',
            'clicksor.com', 'chitika.com', 'buysellads.com', 'bidvertiser.com',
            'mathtag.com', 'adroll.com', 'taboola.com', 'outbrain.com', 
            'revcontent.com', 'viglink.com', 'sharethrough.com', 'livejasmin.com',
            'exoclick.com', 'juicyads.com', 'popads.net', 'adf.ly'
        }
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in [
            r'/ads?/', r'/adserv(er)?/', r'/banner\d*/', r'/pop(up|under)/',
            r'/pixel/', r'/track(ing)?/', r'/analytics/', r'/stats?/',
            r'/sponsor/', r'/promo/', r'google.*/(ads|analytics)',
            r'/(click|view)track', r'/count(er)?/', r'/beacon/',
            r'/metric', r'/impression\.', r'[\-.]ad[xs]?[\-.]',
            r'[\-.]telemetry[\-.]', r'/affiliate/', r'/social\-plugins?/',
            r'/tagging/', r'/logging/', r'/tracker/'
        ]]

    def interceptRequest(self, info):
        url = info.requestUrl().toString().lower()
        domain = info.requestUrl().host().lower()
        
        should_block = (
            any(ad_domain in domain for ad_domain in self.blocked_domains) or
            any(pattern.search(url) for pattern in self.compiled_patterns)
        )
        
        if should_block:
            info.block(True)

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(object, QWidget) # post, self
    doubleClicked = pyqtSignal(object) # post
    selectionToggled = pyqtSignal(object, QWidget) # post, self

    def __init__(self, post, size, favorites_dict, parent=None):
        super().__init__(parent)
        self.post = post
        self.is_selected = False
        self.setFixedSize(size, size)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.favorites = favorites_dict
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        
        self.label = QLabel("Loading…")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedSize(size, size)
        layout.addWidget(self.label)
        
        self.loading_label = QLabel(self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("background-color: rgba(0,0,0,0.7); color: white; font-weight: bold;")
        self.loading_label.hide()

        self.update_style()

    def _is_video(self):
        video_exts = ['mp4', 'webm', 'avi', 'mov', 'wmv', 'flv', 'mkv']
        return self.post.get("file_ext", "") in video_exts

    def _is_gif(self):
        return self.post.get("file_ext", "").lower() == "gif"

    def mousePressEvent(self, event):
        modifiers = QApplication.keyboardModifiers()
        is_ctrl_click = (event.button() == Qt.LeftButton and (modifiers & Qt.ControlModifier))
        is_shift_click = (event.button() == Qt.LeftButton and (modifiers & Qt.ShiftModifier))
        is_middle_click = event.button() in [Qt.MiddleButton, Qt.XButton1, Qt.XButton2]

        if is_ctrl_click or is_middle_click or is_shift_click:
            self.selectionToggled.emit(self.post, self)
        elif event.button() == Qt.LeftButton:
            self.clicked.emit(self.post, self)
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.post)
        event.accept()

    def set_pixmap(self, pixmap):
        if pixmap.isNull():
            self.label.setText("Failed")
            self.setStyleSheet("border: 1px solid #f55; background: #311; color: #f88;" if SETTINGS.get("dark_mode", True) else "border: 1px solid #f55; background: #fee; color: #f55;")
        else:
            transform_mode = Qt.FastTransformation if SETTINGS.get("potato_mode", False) else Qt.SmoothTransformation
            self.label.setPixmap(pixmap.scaled(self.width(), self.height(), Qt.KeepAspectRatio, transform_mode))

    def set_text(self, text):
        if text:
            self.loading_label.setText(text)
            self.loading_label.show()
            self.loading_label.raise_()
        else:
            self.loading_label.hide()

    def set_favorites_dict(self, favorites_dict):
        self.favorites = favorites_dict

    def set_selection(self, selected):
        self.is_selected = selected
        self.update_style()

    def resizeEvent(self, event):
        self.loading_label.setGeometry(self.rect())
        super().resizeEvent(event)

    def update_style(self):
        dark = SETTINGS.get("dark_mode", True)
        is_fav = hasattr(self, 'favorites') and self.favorites and self.post.get('id') and self.post.get('id') in self.favorites
        if self.is_selected:
            if dark:
                self.setStyleSheet("border: 1px solid #555; background: #3a3a3a;")
            else:
                self.setStyleSheet("border: 1px solid #ccc; background: #dcdcdc;")
        elif self._is_gif():
            border_color = "#ffc107" if is_fav else "#ffc107" # Yellow for GIFs
            self.setStyleSheet(f"border: 2px solid {border_color}; background: #1a1a1a;" if dark else f"border: 2px solid {border_color}; background: #f0f0f0;")
        elif self._is_video():
            border_color = "#ffc107" if is_fav else "#5b5bff" # Yellow for fav, blue for video
            self.setStyleSheet(f"border: 2px solid {border_color}; background: #1a1a1a;" if dark else f"border: 2px solid {border_color}; background: #f0f0f0;")
        elif is_fav:
            self.setStyleSheet("border: 2px solid #ffc107; background: #1a1a1a;" if dark else "border: 2px solid #ffc107; background: #f0f0f0;")
        else:
            self.setStyleSheet("border: 1px solid #555; background: #1a1a1a;" if dark else "border: 1px solid #ddd; background: #f0f0f0;")

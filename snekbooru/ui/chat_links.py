from collections import OrderedDict
from math import ceil
import re
import threading
from urllib.parse import urlsplit, urlunsplit

from PyQt5.QtCore import (QBuffer, QByteArray, QIODevice, QMimeData, QObject, QRectF, QSize, QSizeF,
                          Qt, QThreadPool, pyqtSignal)
from PyQt5.QtGui import (QColor, QFontMetricsF, QImageReader, QPainter, QPixmap,
                         QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextObjectInterface)
from PyQt5.QtWidgets import QApplication, QFrame, QSizePolicy, QTextBrowser, QToolTip

from snekbooru.core.ai_tools import fetch_public_favicon, sanitize_ai_html
from snekbooru.core.config import SETTINGS
from snekbooru.core.workers import ApiWorker

LINK_OBJECT = QTextFormat.UserObject + 7
LINK_URL = QTextFormat.UserProperty + 1
LINK_TITLE = QTextFormat.UserProperty + 2


def dark_chat_theme(widget):
    theme = SETTINGS.get("active_theme", "Dark (Default)")
    window = widget.window()
    if getattr(window, "is_incognito_window", False):
        return True
    if theme == "Dark (Default)":
        return True
    if theme == "Light (Default)":
        return False
    color = window.palette().color(window.backgroundRole())
    for match in re.finditer(r"([^{}]+)\{([^{}]+)\}", window.styleSheet()):
        selectors = [selector.strip() for selector in match.group(1).split(",")]
        if any(selector in ("QWidget", "QWidget#main_window", "#main_window") for selector in selectors):
            value = re.search(r"background(?:-color)?\s*:\s*([^;]+)\s*;", match.group(2))
            if value:
                raw_color = value.group(1).strip()
                rgb = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)", raw_color)
                candidate = QColor(*map(int, rgb.groups())) if rgb and all(0 <= int(channel) <= 255 for channel in rgb.groups()) else QColor(raw_color)
                if candidate.isValid():
                    color = candidate
    return (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) < 128


def link_origin(url):
    parsed = urlsplit(url)
    if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password:
        return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
    return ""


class FaviconLoader(QObject):
    ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cache = OrderedDict()
        self.pending = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.stop_event = threading.Event()
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self.stop)

    def stop(self):
        self.stop_event.set()
        self.pool.clear()
        self.pending.clear()

    def request(self, url):
        origin = link_origin(url)
        if self.stop_event.is_set() or not origin or origin in self.cache or origin in self.pending or len(self.pending) >= 24:
            return
        self.pending.add(origin)
        worker = ApiWorker(fetch_public_favicon, origin, self.stop_event)
        worker.signals.finished.connect(lambda data, error: self._received(origin, data, error))
        self.pool.start(worker)

    def _received(self, origin, data, error):
        self.pending.discard(origin)
        pixmap = None
        if data and not error:
            buffer = QBuffer()
            buffer.setData(QByteArray(data))
            buffer.open(QIODevice.ReadOnly)
            reader = QImageReader(buffer)
            size = reader.size()
            if size.isValid() and 0 < size.width() <= 512 and 0 < size.height() <= 512:
                reader.setScaledSize(QSize(16, 16))
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cache[origin] = pixmap
        self.cache.move_to_end(origin)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        self.ready.emit(origin)

    def icon(self, url):
        return self.cache.get(link_origin(url))


_favicon_loader = None


def favicon_loader():
    global _favicon_loader
    if _favicon_loader is None:
        _favicon_loader = FaviconLoader(QApplication.instance())
    return _favicon_loader


class LinkPillRenderer(QObject, QTextObjectInterface):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def label(self, char_format):
        url = char_format.property(LINK_URL)
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")) or url

    def metrics(self, char_format):
        metrics = QFontMetricsF(self.view.font())
        maximum = max(40, min(340, self.view.viewport().width() - 12))
        text = metrics.elidedText(self.label(char_format), Qt.ElideMiddle, int(maximum - 38))
        width = min(maximum, metrics.horizontalAdvance(text) + 38)
        return text, width, max(22, metrics.height() + 4)

    def intrinsicSize(self, document, position, char_format):
        text, width, height = self.metrics(char_format)
        return QSizeF(width, height)

    def drawObject(self, painter, rect, document, position, char_format):
        text, width, height = self.metrics(char_format)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#334155" if self.view.is_dark else "#e2e8f0"))
        painter.drawRoundedRect(rect.adjusted(0.5, 1, -0.5, -1), 4, 4)
        icon_rect = QRectF(rect.left() + 6, rect.center().y() - 8, 16, 16)
        pixmap = self.view.loader.icon(char_format.property(LINK_URL))
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(icon_rect.toRect(), pixmap)
        else:
            host = urlsplit(char_format.property(LINK_URL)).hostname or "Link"
            initial = host.removeprefix("www.")[:1].upper()
            painter.setPen(QColor(self.view.link_color))
            painter.setFont(self.view.font())
            painter.drawText(icon_rect, Qt.AlignCenter, initial)
        painter.setFont(self.view.font())
        painter.setPen(QColor(self.view.link_color))
        text_rect = rect.adjusted(28, 0, -6, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class ChatTextView(QTextBrowser):
    linkActivated = pyqtSignal(str)

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._source_text = ""
        self._text_format = Qt.RichText
        self.is_dark = True
        self.link_color = "#ffffff"
        self.loader = favicon_loader()
        self.origins = set()
        self.renderer = LinkPillRenderer(self)
        self.document().documentLayout().registerHandler(LINK_OBJECT, self.renderer)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.setMouseTracking(True)
        self.anchorClicked.connect(lambda url: self.linkActivated.emit(url.toString()))
        self.loader.ready.connect(self._favicon_ready)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.setText(text)

    def setWordWrap(self, enabled):
        self.setLineWrapMode(QTextBrowser.WidgetWidth if enabled else QTextBrowser.NoWrap)

    def setTextFormat(self, text_format):
        self._text_format = text_format

    def textFormat(self):
        return self._text_format

    def text(self):
        return self._source_text

    def setText(self, text):
        self._source_text = text
        self.origins.clear()
        if self._text_format == Qt.PlainText:
            self.setPlainText(text)
        else:
            self.setHtml(sanitize_ai_html(text))
            document = self.document()
            ranges = []
            block = document.begin()
            while block.isValid():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    char_format = fragment.charFormat()
                    if char_format.isAnchor() and char_format.anchorHref():
                        url = char_format.anchorHref()
                        if ranges and ranges[-1][2] == url and ranges[-1][1] == fragment.position():
                            start, end, href, title = ranges[-1]
                            ranges[-1] = (start, fragment.position() + fragment.length(), href, title + fragment.text())
                        else:
                            ranges.append((fragment.position(), fragment.position() + fragment.length(), url, fragment.text()))
                    iterator += 1
                block = block.next()
            for start, end, url, title in reversed(ranges):
                cursor = QTextCursor(document)
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                char_format = QTextCharFormat()
                char_format.setObjectType(LINK_OBJECT)
                char_format.setProperty(LINK_URL, url)
                char_format.setProperty(LINK_TITLE, title)
                char_format.setAnchor(True)
                char_format.setAnchorHref(url)
                cursor.insertText("\ufffc", char_format)
                origin = link_origin(url)
                if origin and len(self.origins) < 8:
                    self.origins.add(origin)
            for origin in self.origins:
                self.loader.request(origin)
        self.document().setTextWidth(max(1, self.viewport().width()))
        self._fit_height()

    def set_link_theme(self, is_dark, text_color):
        self.is_dark = is_dark
        self.link_color = "#ffffff" if is_dark else "#153e75"
        self.setStyleSheet(f"QTextBrowser {{ background: transparent; color: {text_color}; border: none; padding: 0; }}")
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def _fit_height(self, *args):
        height = max(20, ceil(self.document().documentLayout().documentSize().height()) + 2)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(1, self.viewport().width()))
        self.document().markContentsDirty(0, self.document().characterCount())
        self._fit_height()

    def _favicon_ready(self, origin):
        if origin in self.origins:
            self.document().markContentsDirty(0, self.document().characterCount())
            self.viewport().update()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        url = self.anchorAt(event.pos())
        self.viewport().setCursor(Qt.PointingHandCursor if url else Qt.IBeamCursor)
        if url:
            QToolTip.showText(event.globalPos(), url, self)

    @staticmethod
    def _plain_document(document):
        lines = []
        block = document.begin()
        while block.isValid():
            parts = []
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                char_format = fragment.charFormat()
                parts.append(char_format.property(LINK_URL) if char_format.objectType() == LINK_OBJECT else fragment.text())
                iterator += 1
            lines.append("".join(parts))
            block = block.next()
        return "\n".join(lines).replace("\u2028", "\n").replace("\u2029", "\n")

    def toPlainText(self):
        return self._plain_document(self.document())

    def copy(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            QApplication.clipboard().setMimeData(self.createMimeDataFromSelection())

    def createMimeDataFromSelection(self):
        document = QTextDocument()
        QTextCursor(document).insertFragment(self.textCursor().selection())
        data = QMimeData()
        data.setText(self._plain_document(document))
        return data

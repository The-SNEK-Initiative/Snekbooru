import os
import re
import shutil
import time
import webbrowser
import markdown
import requests
import tempfile

import qtawesome as qta
from PyQt5.QtCore import QStandardPaths, Qt, QSize, QPoint, QUrl, QThreadPool
from PyQt5.QtGui import QFont, QIntValidator, QKeySequence, QPalette, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                             QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QKeySequenceEdit,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSpinBox, QStackedWidget, QCompleter,
                             QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget, QScrollArea, QShortcut)

from snekbooru.ui.styling import PYGMENTS_CSS
from snekbooru.api.booru import (fetch_custom_booru_posts,
                                 suggest_custom_booru_tags)
from snekbooru.common.constants import DEFAULT_HOTKEYS, USER_AGENT
from snekbooru.common.translations import SUPPORTED_LANGUAGES, _tr
from snekbooru.core.config import (SETTINGS,
                                   save_custom_boorus,
                                   save_settings)
from snekbooru.ui.styling import (EXAMPLE_STYLESHEET, get_fonts_path,
                                  get_themes_path, load_custom_themes,
                                  sCSSHighlighter, CodeEditor, 
                                  SCSS_KEYWORDS, SCSS_PROPERTIES, SCSS_PSEUDO)
from snekbooru.ui.widgets import AdBlocker
from snekbooru.core.workers import ApiWorker
from snekbooru.core.workers import AsyncApiWorker
from snekbooru.ui.apollo_player import ApolloVideoPlayer
from snekbooru.core.book_export import (export_epub_from_images,
                                        cleanup_images_folder,
                                        export_kindle_epub_from_images,
                                        export_mobi_from_images,
                                        export_pdf_from_images,
                                        export_png_zip_from_images,
                                        list_image_files)
from snekbooru.core.temp_cache import snekbooru_temp_dir, snekbooru_temp_root
from snekbooru.api.ehentai_utils import download_gallery_pages


class CustomTitleBar(QWidget):
    """A custom title bar widget for dialogs."""
    def __init__(self, parent, title="Dialog", has_icon=False):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("custom_title_bar")
        self.setFixedHeight(32)
        self.setObjectName("dialog_title_bar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 0, 0)
        layout.setSpacing(10)

        if has_icon:
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(24, 24)
            self.icon_label.setScaledContents(True)
            layout.addWidget(self.icon_label)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("custom_title_bar_label")
        layout.addWidget(self.title_label)

        layout.addStretch()

        self.close_btn = QToolButton(); self.close_btn.clicked.connect(self.parent.close)
        self.close_btn.setObjectName("close_button")
        self.close_btn.setFixedSize(46, 32) # Keep fixed size for consistent layout
        self.close_btn.setObjectName("title_bar_button")
        layout.addWidget(self.close_btn)

        self.update_icons()
        self.start_move_pos = None

    def _get_icon_color(self):
        """Determines if theme is dark or light and returns appropriate icon color."""
        palette = self.palette()
        bg_color = palette.color(self.backgroundRole())
        r, g, b = bg_color.red(), bg_color.green(), bg_color.blue()
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        return '#ffffff' if luminance < 0.5 else '#000000'

    def update_icons(self):
        """Updates icons based on the current theme color."""
        icon_color = self._get_icon_color()
        if hasattr(self, 'close_btn'):
            self.close_btn.setIcon(qta.icon('fa5s.times', color=icon_color))

    def showEvent(self, event):
        super().showEvent(event)
        self.update_icons()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_move_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.start_move_pos:
            delta = event.globalPos() - self.start_move_pos
            self.parent.move(self.parent.pos() + delta)
            self.start_move_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.start_move_pos = None


class BaseDialog(QDialog):
    """
    Base dialog with a custom title bar and standardized layout.
    Provides a consistent 'look and feel' across the application.
    """
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowTitle(title)
        
        # Main layout with 1px border
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(1, 1, 1, 1)
        self.root_layout.setSpacing(0)
        self.setStyleSheet("QDialog { border: 1px solid #333; }")

        # Custom Title Bar
        self.title_bar = CustomTitleBar(self, title)
        self.root_layout.addWidget(self.title_bar)

        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 15, 15, 15)
        self.content_layout.setSpacing(10)
        self.root_layout.addWidget(self.content_widget)
        
        # Standard Button Box (optional)
        self.button_layout = None

    def add_buttons(self, buttons_config):
        """
        Standardized way to add buttons to the bottom of the dialog.
        buttons_config: list of (text, icon, callback, is_default)
        """
        if not self.button_layout:
            self.button_layout = QHBoxLayout()
            self.button_layout.addStretch()
            self.content_layout.addLayout(self.button_layout)
            
        for text, icon_name, callback, is_default in buttons_config:
            btn = QPushButton(text)
            if icon_name:
                btn.setIcon(qta.icon(icon_name))
            if callback:
                btn.clicked.connect(callback)
            if is_default:
                btn.setDefault(True)
            self.button_layout.addWidget(btn)
        return self.button_layout

    def set_content(self, widget):
        """Replaces the entire content with a single widget."""
        # Clear existing
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.content_layout.addWidget(widget)

    def apply_theme(self):
        """Update title bar icons when theme changes."""
        self.title_bar.update_icons()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()


class BookExportDialog(BaseDialog):
    def __init__(self, parent=None, initial_folder=None, allow_cleanup=False, cleanup_allowed_root=None):
        super().__init__(_tr("Export Book"), parent)
        self.setMinimumSize(620, 320)
        self.threadpool = QThreadPool()
        self.allow_cleanup = bool(allow_cleanup)
        self.cleanup_allowed_root = cleanup_allowed_root

        self.folder_path = QLineEdit()
        if initial_folder:
            self.folder_path.setText(initial_folder)
        browse_btn = QPushButton(qta.icon("fa5s.folder-open"), _tr(" Browse"))
        browse_btn.clicked.connect(self.browse_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_path, 1)
        folder_row.addWidget(browse_btn)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText(_tr("Title (optional)"))

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "EPUB", "MOBI", "Kindle (EPUB)", "PNG ZIP"])

        self.output_path = QLineEdit()
        out_btn = QPushButton(qta.icon("fa5s.save"), _tr(" Save As"))
        out_btn.clicked.connect(self.choose_output_path)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_path, 1)
        out_row.addWidget(out_btn)

        form = QFormLayout()
        form.addRow(_tr("Images Folder:"), folder_row)
        form.addRow(_tr("Book Title:"), self.title_input)
        form.addRow(_tr("Format:"), self.format_combo)
        form.addRow(_tr("Output File:"), out_row)
        self.content_layout.addLayout(form)

        self.delete_images_checkbox = QCheckBox(_tr("Delete downloaded pages after export"))
        self.delete_images_checkbox.setChecked(self.allow_cleanup)
        self.delete_images_checkbox.setVisible(self.allow_cleanup)
        self.content_layout.addWidget(self.delete_images_checkbox)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.content_layout.addWidget(self.progress)

        btn_row = QHBoxLayout()
        self.export_btn = QPushButton(qta.icon("fa5s.file-export"), _tr(" Export"))
        self.export_btn.clicked.connect(self.start_export)
        cancel_btn = QPushButton(qta.icon("fa5s.times"), _tr(" Close"))
        cancel_btn.clicked.connect(self.close)
        btn_row.addStretch(1)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(cancel_btn)
        self.content_layout.addLayout(btn_row)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, _tr("Select Images Folder"))
        if folder:
            self.folder_path.setText(folder)
            if not self.output_path.text().strip():
                self._suggest_output_path()

    def choose_output_path(self):
        self._suggest_output_path(force_picker=True)

    def _suggest_output_path(self, force_picker=False):
        folder = self.folder_path.text().strip()
        fmt = self.format_combo.currentText()
        title = self.title_input.text().strip() or "book"
        safe_title = re.sub(r"[\\\\/:*?\"<>|]+", "_", title).strip() or "book"

        default_ext = {"PDF": ".pdf", "EPUB": ".epub", "MOBI": ".mobi", "Kindle (EPUB)": ".epub", "PNG ZIP": ".zip"}[fmt]
        default_name = f"{safe_title}{default_ext}"
        default_dir = folder if folder and os.path.isdir(folder) else QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        default_path = os.path.join(default_dir, default_name)

        if not force_picker:
            self.output_path.setText(default_path)
            return

        filter_map = {
            "PDF": "PDF (*.pdf)",
            "EPUB": "EPUB (*.epub)",
            "MOBI": "MOBI (*.mobi)",
            "Kindle (EPUB)": "EPUB (*.epub)",
            "PNG ZIP": "ZIP (*.zip)",
        }
        path, _ = QFileDialog.getSaveFileName(self, _tr("Save As"), default_path, filter_map[fmt])
        if path:
            self.output_path.setText(path)

    def start_export(self):
        folder = self.folder_path.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, _tr("Error"), _tr("Please choose a valid images folder."))
            return

        image_paths = list_image_files(folder)
        if not image_paths:
            QMessageBox.warning(self, _tr("Error"), _tr("No images found in the selected folder."))
            return

        fmt = self.format_combo.currentText()
        out_path = self.output_path.text().strip()
        if not out_path:
            self._suggest_output_path()
            out_path = self.output_path.text().strip()
        if not out_path:
            QMessageBox.warning(self, _tr("Error"), _tr("Please choose an output file."))
            return

        title = self.title_input.text().strip() or "Manga"

        self.export_btn.setEnabled(False)
        self.progress.show()

        worker = ApiWorker(self._run_export, fmt, image_paths, out_path, title, folder, self._should_cleanup())
        worker.signals.finished.connect(self._on_export_finished)
        self.threadpool.start(worker)

    def _should_cleanup(self):
        return self.allow_cleanup and self.delete_images_checkbox.isChecked()

    def _run_export(self, fmt, image_paths, out_path, title, source_folder, cleanup):
        fmt = fmt.upper()
        if fmt == "PDF":
            final = export_pdf_from_images(image_paths, out_path)
            self._cleanup_source_images(source_folder, cleanup)
            return final, None
        if fmt == "EPUB":
            final = export_epub_from_images(image_paths, out_path, title=title)
            self._cleanup_source_images(source_folder, cleanup)
            return final, None
        if fmt == "PNG ZIP":
            final = export_png_zip_from_images(image_paths, out_path)
            self._cleanup_source_images(source_folder, cleanup)
            return final, None
        if fmt == "MOBI":
            final = export_mobi_from_images(image_paths, out_path, title=title)
            self._cleanup_source_images(source_folder, cleanup)
            return final, None
        if fmt == "KINDLE (EPUB)":
            final = export_kindle_epub_from_images(image_paths, out_path, title=title)
            self._cleanup_source_images(source_folder, cleanup)
            return final, None
        raise ValueError("Unsupported format")

    def _cleanup_source_images(self, folder, cleanup):
        if not cleanup:
            return
        if not folder or not os.path.isdir(folder):
            return
        allowed_root = self.cleanup_allowed_root or SETTINGS.get("download_dir")
        cleanup_images_folder(folder, allowed_root)

    def _on_export_finished(self, data, err):
        self.export_btn.setEnabled(True)
        self.progress.hide()
        if err:
            QMessageBox.critical(self, _tr("Export Failed"), str(err))
            return
        out_path, function_error = data
        if function_error:
            QMessageBox.critical(self, _tr("Export Failed"), str(function_error))
            return
        QMessageBox.information(self, _tr("Export Complete"), _tr("Saved to: {path}").format(path=out_path))


class MangaDownloadExportDialog(BaseDialog):
    def __init__(self, parent=None, *, title="Manga", source_label="", download_spec=None):
        super().__init__(_tr("Download & Export"), parent)
        self.setMinimumSize(640, 320)
        self.threadpool = QThreadPool()
        self.download_spec = download_spec or {}
        self.temp_folder = None

        self.title_input = QLineEdit()
        self.title_input.setText(title or "Manga")

        self.source_info = QLabel(source_label or "")
        self.source_info.setStyleSheet("color: #888;")

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "EPUB", "MOBI", "Kindle (EPUB)", "PNG ZIP"])

        self.output_path = QLineEdit()
        out_btn = QPushButton(qta.icon("fa5s.save"), _tr(" Save As"))
        out_btn.clicked.connect(self.choose_output_path)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_path, 1)
        out_row.addWidget(out_btn)

        form = QFormLayout()
        form.addRow(_tr("Book Title:"), self.title_input)
        if source_label:
            form.addRow(_tr("Source:"), self.source_info)
        form.addRow(_tr("Format:"), self.format_combo)
        form.addRow(_tr("Output:"), out_row)
        self.content_layout.addLayout(form)

        self.status_label = QLabel(_tr("Ready"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.content_layout.addWidget(self.status_label)
        self.content_layout.addWidget(self.progress)

        row = QHBoxLayout()
        self.start_btn = QPushButton(qta.icon("fa5s.play"), _tr(" Start"))
        self.cancel_btn = QPushButton(qta.icon("fa5s.times"), _tr(" Cancel"))
        row.addStretch()
        row.addWidget(self.start_btn)
        row.addWidget(self.cancel_btn)
        self.content_layout.addLayout(row)

        self.start_btn.clicked.connect(self.start)
        self.cancel_btn.clicked.connect(self.reject)

        self._suggest_output_path()

    def _suggest_output_path(self):
        fmt = (self.format_combo.currentText() or "").upper()
        default_ext = {"PDF": ".pdf", "EPUB": ".epub", "MOBI": ".mobi", "KINDLE (EPUB)": ".epub", "PNG ZIP": ".zip"}.get(fmt, ".pdf")
        safe_title = re.sub(r"[\\\\/:*?\"<>|]+", "_", (self.title_input.text() or "manga")).strip() or "manga"
        default_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        self.output_path.setText(os.path.join(default_dir, f"{safe_title}{default_ext}"))

    def choose_output_path(self):
        fmt = (self.format_combo.currentText() or "").upper()
        default_ext = {"PDF": ".pdf", "EPUB": ".epub", "MOBI": ".mobi", "KINDLE (EPUB)": ".epub", "PNG ZIP": ".zip"}.get(fmt, ".pdf")
        filter_map = {
            "PDF": "PDF (*.pdf)",
            "EPUB": "EPUB (*.epub)",
            "MOBI": "MOBI (*.mobi)",
            "KINDLE (EPUB)": "EPUB (*.epub)",
            "PNG ZIP": "ZIP (*.zip)",
        }
        safe_title = re.sub(r"[\\\\/:*?\"<>|]+", "_", (self.title_input.text() or "manga")).strip() or "manga"
        default_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        default_path = os.path.join(default_dir, f"{safe_title}{default_ext}")
        out_path, _ = QFileDialog.getSaveFileName(self, _tr("Save As"), default_path, filter_map.get(fmt, "All Files (*)"))
        if out_path:
            self.output_path.setText(out_path)

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(not running)
        self.title_input.setEnabled(not running)
        self.format_combo.setEnabled(not running)
        self.output_path.setEnabled(not running)

    def start(self):
        out_path = self.output_path.text().strip()
        if not out_path:
            QMessageBox.warning(self, _tr("Export"), _tr("Please choose an output path."))
            return
        fmt = (self.format_combo.currentText() or "").upper()
        title = (self.title_input.text() or "Manga").strip()
        if not title:
            title = "Manga"

        reply = QMessageBox.question(
            self,
            _tr("Confirm"),
            _tr("Download pages to temp and export now?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_running(True)
        self.progress.setRange(0, 0)
        self.status_label.setText(_tr("Downloading pages..."))

        def work():
            temp_folder = snekbooru_temp_dir("manga", "exports", str(int(time.time())))
            kind = (self.download_spec.get("kind") or "").lower()
            if kind == "ehentai":
                url = self.download_spec.get("url")
                if not url:
                    raise RuntimeError(f"Missing {kind} url")
                download_gallery_pages(url, temp_folder)
            elif kind == "mangadex":
                page_urls = self.download_spec.get("page_urls") or []
                if not page_urls:
                    raise RuntimeError("Missing MangaDex pages")
                for i, uri in enumerate(page_urls, start=1):
                    ext = os.path.splitext(str(uri))[1].split("?")[0].lower()
                    if not ext or len(ext) > 6:
                        ext = ".jpg"
                    file_path = os.path.join(temp_folder, f"page_{i:04d}{ext}")
                    r = requests.get(str(uri), headers={"User-Agent": USER_AGENT, "Referer": "https://mangadex.org/"}, timeout=60)
                    r.raise_for_status()
                    with open(file_path, "wb") as f:
                        f.write(r.content)
            else:
                raise RuntimeError("Unsupported source")

            image_paths = list_image_files(temp_folder)
            if not image_paths:
                raise RuntimeError("No images downloaded.")

            if fmt == "PDF":
                final = export_pdf_from_images(image_paths, out_path)
            elif fmt == "EPUB":
                final = export_epub_from_images(image_paths, out_path, title=title)
            elif fmt == "MOBI":
                final = export_mobi_from_images(image_paths, out_path, title=title)
            elif fmt == "KINDLE (EPUB)":
                final = export_kindle_epub_from_images(image_paths, out_path, title=title)
            elif fmt == "PNG ZIP":
                final = export_png_zip_from_images(image_paths, out_path)
            else:
                raise RuntimeError("Unsupported format")

            try:
                shutil.rmtree(temp_folder, ignore_errors=True)
            except Exception:
                pass

            return final, None

        worker = ApiWorker(work)
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)

    def _on_finished(self, data, err):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_running(False)
        if err or not data:
            self.status_label.setText(_tr("Failed."))
            QMessageBox.critical(self, _tr("Export Failed"), str(err or "Unknown error"))
            return
        out_path, function_error = data
        if function_error:
            self.status_label.setText(_tr("Failed."))
            QMessageBox.critical(self, _tr("Export Failed"), str(function_error))
            return
        self.status_label.setText(_tr("Done"))
        self.accept()


class MangaBookDialog(BaseDialog):
    def __init__(self, parent=None, images_folder=None, title=None):
        super().__init__(title or _tr("Manga Reader"), parent)
        self.setMinimumSize(800, 700)
        self.images_folder = images_folder
        self.image_paths = list_image_files(images_folder) if images_folder else []
        self.index = 0
        self.current_pixmap = None

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)
        self.content_layout.addWidget(self.scroll, 1)

        controls = QHBoxLayout()
        self.prev_btn = QPushButton(qta.icon("fa5s.chevron-left"), _tr(" Prev"))
        self.prev_btn.setFocusPolicy(Qt.NoFocus)
        self.next_btn = QPushButton(qta.icon("fa5s.chevron-right"), _tr(" Next"))
        self.next_btn.setFocusPolicy(Qt.NoFocus)
        self.page_label = QLabel("")
        self.fit_combo = QComboBox()
        self.fit_combo.setFocusPolicy(Qt.NoFocus)
        self.fit_combo.addItems([_tr("Fit Page"), _tr("Fit Width"), _tr("Actual Size")])
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setFocusPolicy(Qt.NoFocus)
        self.zoom_slider.setRange(25, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(180)
        self.export_btn = QPushButton(qta.icon("fa5s.file-export"), _tr(" Export"))
        self.export_btn.setFocusPolicy(Qt.NoFocus)
        self.open_folder_btn = QPushButton(qta.icon("fa5s.folder-open"), _tr(" Folder"))
        self.open_folder_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn = QPushButton(qta.icon("fa5s.times"), _tr(" Close"))
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.page_label, 1, Qt.AlignCenter)
        controls.addWidget(self.fit_combo)
        controls.addWidget(self.zoom_slider)
        controls.addWidget(self.export_btn)
        controls.addWidget(self.open_folder_btn)
        controls.addWidget(self.close_btn)
        self.content_layout.addLayout(controls)

        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.export_btn.clicked.connect(self.open_export)
        self.close_btn.clicked.connect(self.close)
        self.fit_combo.currentIndexChanged.connect(self._apply_scaled_pixmap)
        self.zoom_slider.valueChanged.connect(self._apply_scaled_pixmap)

        self._shortcut_prev = QShortcut(QKeySequence(Qt.Key_Left), self)
        self._shortcut_prev.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_prev.activated.connect(self.prev_page)
        self._shortcut_next = QShortcut(QKeySequence(Qt.Key_Right), self)
        self._shortcut_next.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_next.activated.connect(self.next_page)
        self._shortcut_prev2 = QShortcut(QKeySequence(Qt.Key_PageUp), self)
        self._shortcut_prev2.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_prev2.activated.connect(self.prev_page)
        self._shortcut_next2 = QShortcut(QKeySequence(Qt.Key_PageDown), self)
        self._shortcut_next2.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_next2.activated.connect(self.next_page)
        self._shortcut_next3 = QShortcut(QKeySequence(Qt.Key_Space), self)
        self._shortcut_next3.setContext(Qt.WidgetWithChildrenShortcut)
        self._shortcut_next3.activated.connect(self.next_page)

        self._update_buttons()
        self.show_page(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scaled_pixmap()

    def open_folder(self):
        try:
            if self.images_folder and os.path.isdir(self.images_folder):
                os.startfile(self.images_folder)
        except Exception:
            pass

    def _apply_scaled_pixmap(self):
        if not self.current_pixmap or self.current_pixmap.isNull():
            return
        viewport_w = max(1, self.scroll.viewport().width() - 20)
        viewport_h = max(1, self.scroll.viewport().height() - 20)
        zoom = max(1, int(self.zoom_slider.value()))
        mode = self.fit_combo.currentText()
        pix = self.current_pixmap

        if mode == _tr("Actual Size"):
            w = max(1, int(pix.width() * zoom / 100.0))
            h = max(1, int(pix.height() * zoom / 100.0))
            scaled = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
            return

        if mode == _tr("Fit Width"):
            target_w = max(1, int(viewport_w * zoom / 100.0))
            self.image_label.setPixmap(pix.scaledToWidth(target_w, Qt.SmoothTransformation))
            return

        scale_w = viewport_w / max(1, pix.width())
        scale_h = viewport_h / max(1, pix.height())
        scale = min(scale_w, scale_h) * (zoom / 100.0)
        w = max(1, int(pix.width() * scale))
        h = max(1, int(pix.height() * scale))
        self.image_label.setPixmap(pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _update_buttons(self):
        total = len(self.image_paths)
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < max(0, total - 1))
        if total:
            self.page_label.setText(_tr("Page {cur}/{total}").format(cur=self.index + 1, total=total))
        else:
            self.page_label.setText(_tr("No pages"))

    def show_page(self, index):
        if not self.image_paths:
            self.image_label.setText(_tr("No pages found."))
            self.current_pixmap = None
            self._update_buttons()
            return
        self.index = max(0, min(index, len(self.image_paths) - 1))
        pix = QPixmap(self.image_paths[self.index])
        self.current_pixmap = pix
        if pix.isNull():
            self.image_label.setText(_tr("Failed to load page."))
        else:
            self._apply_scaled_pixmap()
        self._update_buttons()

    def next_page(self):
        self.show_page(self.index + 1)

    def prev_page(self):
        self.show_page(self.index - 1)

    def open_export(self):
        if not self.images_folder or not os.path.isdir(self.images_folder):
            QMessageBox.information(self, _tr("Export"), _tr("No pages folder available to export."))
            return
        cleanup_root = None
        try:
            temp_root = os.path.abspath(snekbooru_temp_root())
            folder_abs = os.path.abspath(self.images_folder)
            if os.path.commonpath([temp_root, folder_abs]) == temp_root:
                cleanup_root = temp_root
        except Exception:
            cleanup_root = None

        dialog = BookExportDialog(self, initial_folder=self.images_folder, allow_cleanup=True, cleanup_allowed_root=cleanup_root)
        try:
            dialog.title_input.setText(self.windowTitle() or _tr("Manga"))
            dialog._suggest_output_path()
        except Exception:
            pass
        dialog.show()

    def showEvent(self, event):
        """Update title bar icons when dialog is shown."""
        super().showEvent(event)
        self.apply_theme()

    def closeEvent(self, event):
        """Clean up temporary manga files if they are in the temp directory."""
        if self.images_folder:
            try:
                temp_root = os.path.abspath(snekbooru_temp_root())
                folder_abs = os.path.abspath(self.images_folder)
                # Only delete if it's inside our temp directory
                if os.path.commonpath([temp_root, folder_abs]) == temp_root:
                    import shutil
                    # Run in background to avoid UI freeze
                    def _bg_cleanup():
                        try:
                            shutil.rmtree(folder_abs, ignore_errors=True)
                            print(f"[MangaBook] Cleaned up temp folder: {folder_abs}")
                        except Exception:
                            pass
                    import threading
                    threading.Thread(target=_bg_cleanup, daemon=True).start()
            except Exception:
                pass
        super().closeEvent(event)


class ThemeEditorDialog(BaseDialog):
    def __init__(self, theme_path, theme_content, parent=None):
        super().__init__(f"sCSS Editor - {os.path.basename(theme_path)}", parent)
        self.theme_path = theme_path
        self.setMinimumSize(800, 700)

        self.editor = CodeEditor(); self.editor.setPlainText(theme_content)
        self.highlighter = sCSSHighlighter(self.editor.document())
        
        # Setup Completer
        completer = QCompleter(SCSS_KEYWORDS + SCSS_PROPERTIES + SCSS_PSEUDO)
        self.editor.setCompleter(completer)
        
        self.content_layout.addWidget(self.editor)

        button_row = QHBoxLayout()
        save_btn = QPushButton(qta.icon('fa5s.save'), " Save & Close"); save_btn.clicked.connect(self.save_and_accept)
        cancel_btn = QPushButton(qta.icon('fa5s.times'), " Cancel"); cancel_btn.clicked.connect(self.reject)
        button_row.addStretch(); button_row.addWidget(save_btn); button_row.addWidget(cancel_btn)
        self.content_layout.addLayout(button_row)

    def save_and_accept(self):
        try:
            with open(self.theme_path, 'w', encoding='utf-8') as f: f.write(self.editor.toPlainText())
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save the theme file.\n\nError: {e}")


class HentaiSeriesDialog(BaseDialog):
    """
    A dialog to display scraped information about a Hentai Haven series,
    including a description and a list of episodes.
    """
    def __init__(self, series_data: dict, parent=None):
        super().__init__(series_data.get("title", "Hentai Series"), parent)
        self.series_data = series_data
        self.parent_app = parent
        self.setMinimumSize(800, 600)

        # Description
        description_group = QGroupBox(_tr("Description"))
        description_layout = QVBoxLayout(description_group)
        description_browser = QTextBrowser()
        description_browser.setPlainText(series_data.get("description", "No description available."))
        description_browser.setReadOnly(True)
        description_browser.setMaximumHeight(150)
        description_layout.addWidget(description_browser)
        self.content_layout.addWidget(description_group)

        # Episodes
        episodes_group = QGroupBox(_tr("Episodes"))
        episodes_layout = QVBoxLayout(episodes_group)
        self.episode_list = QListWidget()
        self.episode_list.itemDoubleClicked.connect(self.on_episode_selected)
        episodes_layout.addWidget(self.episode_list)
        self.content_layout.addWidget(episodes_group)

        self.populate_episodes()

    def populate_episodes(self):
        episodes = self.series_data.get("episodes", [])
        if not episodes:
            self.episode_list.addItem(_tr("No episodes found."))
            return

        for episode in episodes:
            item = QListWidgetItem(episode.get("title", "Unknown Episode"))
            item.setData(Qt.UserRole, episode)
            self.episode_list.addItem(item)

    def on_episode_selected(self, item: QListWidgetItem):
        episode_data = item.data(Qt.UserRole)
        episode_obj = episode_data.get("episode_obj")
        episode_title = episode_data.get("title")

        if not episode_obj:
            QMessageBox.warning(self, "Error", "This episode has no data object.")
            return

        from snekbooru.ui.main_window import _get_hhaven_stream_url # Import the new async helper
        worker = AsyncApiWorker(_get_hhaven_stream_url, episode_obj)
        def on_finished(stream_url, err):
            if err:
                QMessageBox.critical(self, "Error", f"Could not load video stream:\n{err}")
            else:
            
                dialog = HentaiViewerDialog(stream_url, episode_title, self); self.parent_app.open_dialogs.append(dialog); dialog.show()
        worker.signals.finished.connect(on_finished)
        self.parent_app.threadpool.start(worker)

class HentaiViewerDialog(BaseDialog):
    """A dialog to display hentai videos using VLC-based player for proper HLS support."""
    def __init__(self, stream_url, title, parent=None):
        super().__init__(f"Hentai Viewer - {title}", parent)
        self.setMinimumSize(1280, 720)
        self.parent_app = parent.parent_app if hasattr(parent, 'parent_app') else parent
        self.stream_url = stream_url

        # Media Stack (to show loading label)
        self.media_stack = QStackedWidget()
        self.content_layout.addWidget(self.media_stack, 1)

        # Loading Label & Progress
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        self.loading_label = QLabel(_tr("Loading video..."))
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setValue(0)
        self.download_progress_bar.setTextVisible(True)
        self.download_progress_bar.setMaximumWidth(600)
        
        self.download_status_label = QLabel(_tr("Parsing playlist..."))
        self.download_status_label.setAlignment(Qt.AlignCenter)
        
        loading_layout.addStretch()
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.download_progress_bar, 0, Qt.AlignCenter)
        loading_layout.addWidget(self.download_status_label)
        loading_layout.addStretch()
        
        self.media_stack.addWidget(self.loading_widget)

        # Video Widget (using Apollo player for proper HLS support)
        self.apollo_video_player = ApolloVideoPlayer()
        self.media_stack.addWidget(self.apollo_video_player)

        # Controls
        self.video_controls = QWidget()
        controls_layout = QHBoxLayout(self.video_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        self.play_pause_btn = QPushButton(qta.icon('fa5s.play'), "")
        self.play_pause_btn.setFocusPolicy(Qt.NoFocus)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.time_label = QLabel("00:00 / 00:00")
        self.mute_btn = QPushButton(qta.icon('fa5s.volume-up'), "")
        self.mute_btn.setFocusPolicy(Qt.NoFocus)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumWidth(150)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        
        self.loop_btn = QPushButton(qta.icon('fa5s.redo'), "")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setToolTip(_tr("Loop Video"))
        self.loop_btn.setFocusPolicy(Qt.NoFocus)
        
        self.fullscreen_btn = QPushButton(qta.icon('fa5s.expand'), "")
        self.fullscreen_btn.setFocusPolicy(Qt.NoFocus)

        controls_layout.addWidget(self.play_pause_btn)
        controls_layout.addWidget(self.seek_slider)
        controls_layout.addWidget(self.time_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.mute_btn)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addSpacing(10)
        controls_layout.addWidget(self.loop_btn)
        controls_layout.addWidget(self.fullscreen_btn)
        self.content_layout.addWidget(self.video_controls)

        # Connections
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        self.seek_slider.sliderMoved.connect(self.seek_video)
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.apollo_video_player.position_changed.connect(self.update_position)
        self.apollo_video_player.duration_changed.connect(self.update_duration)
        self.apollo_video_player.state_changed.connect(self.update_play_pause_button)
        self.apollo_video_player.download_progress.connect(self.update_download_progress)
        self.apollo_video_player.error.connect(self.on_player_error)

        # Make sure this dialog receives keyboard focus for keyPressEvent
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # Load media
        self.media_stack.setCurrentWidget(self.loading_widget)
        # Use a worker to parse the M3U8 and get the final stream URL
        self.threadpool = QThreadPool()
        worker = ApiWorker(self._get_final_stream_url, stream_url)
        worker.signals.finished.connect(self._on_stream_url_resolved)
        self.threadpool.start(worker)

    def _get_final_stream_url(self, url):
        """
        Parses an M3U8 playlist to find the highest quality stream URL.
        If the URL is not a playlist, it returns the original URL.
        """
        import re
        try:
            headers = {'User-Agent': USER_AGENT, 'Referer': 'https://hentaihaven.xxx/'}
            
            # If it's an M3U8 playlist, we need to parse it first
            if '.m3u8' in url:
                r = requests.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                playlist_content = r.text
                
                lines = playlist_content.strip().split('\n')
                streams = []
                for i, line in enumerate(lines):
                    if line.startswith('#EXT-X-STREAM-INF'):
                        resolution_match = re.search(r'RESOLUTION=(\d+x\d+)', line)
                        if resolution_match and i + 1 < len(lines):
                            stream_url = lines[i+1]
                            if not stream_url.startswith('http'):
                                base_url = url.rsplit('/', 1)[0]
                                stream_url = f"{base_url}/{stream_url}"
                            streams.append({'res': resolution_match.group(1), 'url': stream_url})
                
                if streams:
                    streams.sort(key=lambda s: int(s['res'].split('x')[1]), reverse=True)
                    # Return the M3U8 playlist URL instead of individual stream
                    # Apollo will handle the HLS playlist properly
                    return url, None

            return url, None # Return original URL if not a playlist or no streams found
        except Exception as e:
            return None, str(e)

    def _on_stream_url_resolved(self, data, err):
        if err or not data:
            self.loading_label.setText(_tr("Error loading video: {error}").format(error=err or "Unknown"))
            self.download_progress_bar.hide()
            self.download_status_label.hide()
            self.media_stack.setCurrentWidget(self.loading_widget)
            return

        final_url, _ = data
        self.media_stack.setCurrentWidget(self.apollo_video_player)
        self.apollo_video_player.load(final_url)
        self.apollo_video_player.play()
        self.play_pause_btn.setIcon(qta.icon('fa5s.pause'))
        self.download_status_label.setText(_tr("Starting playback..."))

    def update_download_progress(self, progress):
        """Update the download progress bar and status text."""
        self.download_progress_bar.setValue(int(progress))
        if progress < 33:
            self.download_status_label.setText(_tr("Prefetching video segments..."))
        elif progress < 66:
            self.download_status_label.setText(_tr("Prefetching audio segments..."))
        elif progress < 100:
            self.download_status_label.setText(_tr("Merging components..."))
        else:
            self.download_status_label.setText(_tr("Ready!"))



    def toggle_play_pause(self):
        if self.apollo_video_player.is_playing:
            self.apollo_video_player.pause()
            self.play_pause_btn.setIcon(qta.icon('fa5s.play'))
        else:
            self.apollo_video_player.play()
            self.play_pause_btn.setIcon(qta.icon('fa5s.pause'))

    def seek_video(self, position_ms):
        """Seek to a position in the video."""
        self.apollo_video_player.seek(position_ms)

    def on_volume_changed(self, volume):
        """Update volume when slider changes."""
        self.apollo_video_player.set_volume(volume)
        # Update mute button icon based on volume
        if volume == 0:
            self.mute_btn.setIcon(qta.icon('fa5s.volume-mute'))
        elif volume < 50:
            self.mute_btn.setIcon(qta.icon('fa5s.volume-down'))
        else:
            self.mute_btn.setIcon(qta.icon('fa5s.volume-up'))

    def toggle_mute(self):
        """Toggle mute state."""
        self.apollo_video_player.toggle_mute()
        if self.apollo_video_player.is_muted():
            self.mute_btn.setIcon(qta.icon('fa5s.volume-mute'))
            self.volume_slider.setValue(0)
        else:
            self.mute_btn.setIcon(qta.icon('fa5s.volume-up'))
            self.volume_slider.setValue(100)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        self.apollo_video_player.toggle_fullscreen()
        if self.apollo_video_player.is_fullscreen:
            self.fullscreen_btn.setIcon(qta.icon('fa5s.compress'))
        else:
            self.fullscreen_btn.setIcon(qta.icon('fa5s.expand'))

    def update_position(self, position_ms):
        """Update seek slider when position changes."""
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position_ms)
        self.update_time_label(position_ms, self.seek_slider.maximum())

    def update_duration(self, duration_ms):
        """Update seek slider range when duration is known."""
        self.seek_slider.setRange(0, duration_ms)
        self.update_time_label(self.seek_slider.value(), duration_ms)

    def update_play_pause_button(self, state):
        """Update play/pause button based on playback state."""
        if state == 'playing':
            self.play_pause_btn.setIcon(qta.icon('fa5s.pause'))
        else:
            self.play_pause_btn.setIcon(qta.icon('fa5s.play'))
            if state == 'stopped' and self.loop_btn.isChecked():
                self.apollo_video_player.play()

    def update_time_label(self, position_ms, duration_ms):
        """Update the time display label."""
        if duration_ms == 0:
            return
        pos_min, pos_sec = divmod(position_ms // 1000, 60)
        dur_min, dur_sec = divmod(duration_ms // 1000, 60)
        self.time_label.setText(f"{pos_min:02}:{pos_sec:02} / {dur_min:02}:{dur_sec:02}")

    def on_player_error(self, error_msg):
        """Handle player errors."""
        self.loading_label.setText(_tr("Playback error: {error}").format(error=error_msg))
        self.download_progress_bar.hide()
        self.download_status_label.hide()
        self.media_stack.setCurrentWidget(self.loading_widget)

    def keyPressEvent(self, event):
        """Handle key presses for video control."""
        key = event.key()
        
        # Space: toggle play/pause
        if key == Qt.Key_Space:
            self.toggle_play_pause()
            event.accept()
        # F: toggle fullscreen
        elif key == Qt.Key_F:
            self.toggle_fullscreen()
            event.accept()
        # M: toggle mute
        elif key == Qt.Key_M:
            self.toggle_mute()
            event.accept()
        # Left arrow: seek back 10s
        elif key == Qt.Key_Left:
            if self.apollo_video_player.player:
                current_pos = self.apollo_video_player.player.get_position_ms()
                self.apollo_video_player.seek(max(0, current_pos - 10000))
            event.accept()
        # Right arrow: seek forward 10s
        elif key == Qt.Key_Right:
            if self.apollo_video_player.player:
                current_pos = self.apollo_video_player.player.get_position_ms()
                self.apollo_video_player.seek(current_pos + 10000)
            event.accept()
        # Up arrow: volume up
        elif key == Qt.Key_Up:
            new_vol = min(100, self.volume_slider.value() + 10)
            self.volume_slider.setValue(new_vol)
            event.accept()
        # Down arrow: volume down
        elif key == Qt.Key_Down:
            new_vol = max(0, self.volume_slider.value() - 10)
            self.volume_slider.setValue(new_vol)
            event.accept()
        # Escape: close dialog
        elif key == Qt.Key_Escape:
            self.close()
            event.accept()
        # L: toggle loop
        elif key == Qt.Key_L:
            self.loop_btn.setChecked(not self.loop_btn.isChecked())
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Stop the player in the main thread to avoid QObject::killTimer issues
        try:
            self.apollo_video_player.exit()
        except Exception:
            pass
        if hasattr(self, 'threadpool'): self.threadpool.clear()
        super().closeEvent(event)

class BooruEditorDialog(BaseDialog):
    """A dialog for adding or editing a custom booru configuration."""
    def __init__(self, booru_config=None, parent=None):
        title = _tr("Booru Editor") if booru_config else _tr("Add New Booru")
        super().__init__(title, parent)
        self.booru_config = booru_config or {}
        self.setMinimumWidth(600)

        self.tabs = QTabWidget()
        
        # --- Simple Tab ---
        simple_tab = QWidget()
        simple_form = QFormLayout(simple_tab)
        self.simple_name = QLineEdit(self.booru_config.get("name", ""))
        self.simple_base_url = QLineEdit(self.booru_config.get("base_url", "https://"))
        self.simple_base_url.setPlaceholderText("e.g., https://safebooru.org")
        self.simple_booru_type = QComboBox()
        self.simple_booru_type.addItems(["Gelbooru-like (JSON)", "Danbooru-like (JSON)", "Rule34-like (XML)"])
        self.simple_auth_type = QComboBox(); self.simple_auth_type.addItems(["None", "User ID & API Key", "Login & API Key"])
        
        # Simple tab credential fields
        self.simple_username_label = QLabel(_tr("Username/ID:"))
        self.simple_username = QLineEdit(self.booru_config.get("username", ""))
        self.simple_api_key_label = QLabel(_tr("API Key:"))
        self.simple_api_key = QLineEdit(self.booru_config.get("api_key", ""))
        self.simple_api_key.setEchoMode(QLineEdit.Password)

        simple_form.addRow(_tr("Name:"), self.simple_name)
        simple_form.addRow(_tr("Homepage URL:"), self.simple_base_url)
        simple_form.addRow(_tr("Booru Software Type:"), self.simple_booru_type)
        simple_form.addRow(_tr("Authentication:"), self.simple_auth_type)
        simple_form.addRow(self.simple_username_label, self.simple_username)
        simple_form.addRow(self.simple_api_key_label, self.simple_api_key)


        # --- Advanced Tab ---
        advanced_tab = QWidget()
        adv_form = QFormLayout(advanced_tab)
        self.adv_name = QLineEdit(self.booru_config.get("name", ""))
        self.adv_posts_url = QLineEdit(self.booru_config.get("posts_url", ""))
        self.adv_posts_url.setPlaceholderText("Use {tags}, {limit}, {pid}, {page}")
        self.adv_tags_url = QLineEdit(self.booru_config.get("tags_url", ""))
        self.adv_tags_url.setPlaceholderText("Use {pattern}, {limit}")
        self.adv_response_format = QComboBox(); self.adv_response_format.addItems(["Gelbooru JSON", "Danbooru JSON", "Rule34 XML"])
        self.adv_auth_type = QComboBox(); self.adv_auth_type.addItems(["None", "User ID & API Key", "Login & API Key"])
        
        # Advanced tab credential fields
        self.adv_username_label = QLabel(_tr("Username/ID:"))
        self.adv_username = QLineEdit(self.booru_config.get("username", ""))
        self.adv_api_key_label = QLabel(_tr("API Key:"))
        self.adv_api_key = QLineEdit(self.booru_config.get("api_key", ""))
        self.adv_api_key.setEchoMode(QLineEdit.Password)

        adv_form.addRow(_tr("Name:"), self.adv_name)
        adv_form.addRow(_tr("Posts API URL:"), self.adv_posts_url)
        adv_form.addRow(_tr("Tags API URL:"), self.adv_tags_url)
        adv_form.addRow(_tr("Response Format:"), self.adv_response_format)
        adv_form.addRow(_tr("Authentication:"), self.adv_auth_type)
        adv_form.addRow(self.adv_username_label, self.adv_username)
        adv_form.addRow(self.adv_api_key_label, self.adv_api_key)


        self.tabs.addTab(simple_tab, _tr("Simple"))
        self.tabs.addTab(advanced_tab, _tr("Advanced"))
        self.content_layout.addWidget(self.tabs)

        # Buttons
        button_row = QHBoxLayout()
        test_btn = QPushButton(qta.icon('fa5s.vial'), _tr(" Test Configuration"))
        save_btn = QPushButton(qta.icon('fa5s.save'), _tr(" Save"))
        cancel_btn = QPushButton(qta.icon('fa5s.times'), _tr(" Cancel"))
        button_row.addStretch(); button_row.addWidget(test_btn); button_row.addWidget(save_btn); button_row.addWidget(cancel_btn)
        self.content_layout.addLayout(button_row)

        test_btn.clicked.connect(self.test_configuration)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        # Connect auth_type changes to show/hide credential fields
        self.simple_auth_type.currentIndexChanged.connect(self._update_simple_auth_fields)
        self.adv_auth_type.currentIndexChanged.connect(self._update_adv_auth_fields)
        
        # Initial visibility update
        self._update_simple_auth_fields()
        self._update_adv_auth_fields()
    
    def _update_simple_auth_fields(self):
        """Show/hide credential fields based on simple tab auth type selection."""
        auth_type = self.simple_auth_type.currentText()
        is_none = auth_type == "None"
        self.simple_username_label.setVisible(not is_none)
        self.simple_username.setVisible(not is_none)
        self.simple_api_key_label.setVisible(not is_none)
        self.simple_api_key.setVisible(not is_none)
    
    def _update_adv_auth_fields(self):
        """Show/hide credential fields based on advanced tab auth type selection."""
        auth_type = self.adv_auth_type.currentText()
        is_none = auth_type == "None"
        self.adv_username_label.setVisible(not is_none)
        self.adv_username.setVisible(not is_none)
        self.adv_api_key_label.setVisible(not is_none)
        self.adv_api_key.setVisible(not is_none)


    def get_config(self):
        """Constructs the booru config dictionary from the form fields."""
        is_simple = self.tabs.currentIndex() == 0
        if is_simple:
            name = self.simple_name.text().strip()
            base_url = self.simple_base_url.text().strip().rstrip('/')
            booru_type = self.simple_booru_type.currentText()
            auth = self.simple_auth_type.currentText()

            if not name or not base_url: return None

            config = {"name": name, "base_url": base_url, "auth_type": auth, "mode": "simple", "software": booru_type}
            if auth != "None":
                config["username"] = self.simple_username.text().strip()
                config["api_key"] = self.simple_api_key.text().strip()
            
            # Build URLs with auth placeholders if authentication is required
            auth_suffix = ""
            if auth == "User ID & API Key":
                auth_suffix = "&login={login}&api_key={api_key}"
            elif auth == "Login & API Key":
                auth_suffix = "&login={login}&api_key={api_key}"
            
            if "Gelbooru" in booru_type:
                config["posts_url"] = f"{base_url}/index.php?page=dapi&s=post&q=index&json=1&tags={{tags}}&limit={{limit}}&pid={{pid}}{auth_suffix}"
                config["tags_url"] = f"{base_url}/index.php?page=dapi&s=tag&q=index&json=1&name_pattern={{pattern}}&limit={{limit}}{auth_suffix}"
                config["response_format"] = "Gelbooru JSON"
            elif "Danbooru" in booru_type:
                config["posts_url"] = f"{base_url}/posts.json?tags={{tags}}&limit={{limit}}&page={{page}}{auth_suffix}"
                config["tags_url"] = f"{base_url}/tags.json?search[name_matches]={{pattern}}*&limit={{limit}}{auth_suffix}"
                config["response_format"] = "Danbooru JSON"
            elif "Rule34" in booru_type:
                config["posts_url"] = f"{base_url}/index.php?page=dapi&s=post&q=index&tags={{tags}}&limit={{limit}}&pid={{pid}}{auth_suffix}"
                config["tags_url"] = f"{base_url}/autocomplete.php?q={{pattern}}{auth_suffix}"
                config["response_format"] = "Rule34 XML"
            return config
        else: # Advanced
            name = self.adv_name.text().strip()
            posts_url = self.adv_posts_url.text().strip()
            if not name or not posts_url: return None
            config = {
                "name": name,
                "posts_url": posts_url,
                "tags_url": self.adv_tags_url.text().strip(),
                "response_format": self.adv_response_format.currentText(),
                "auth_type": self.adv_auth_type.currentText(),
                "mode": "advanced"
            }
            auth = self.adv_auth_type.currentText()
            if auth != "None":
                config["username"] = self.adv_username.text().strip()
                config["api_key"] = self.adv_api_key.text().strip()
            return config

    def test_configuration(self):
        config = self.get_config()
        if not config:
            QMessageBox.warning(self, _tr("Invalid Configuration"), _tr("Please fill in all required fields."))
            return

        QMessageBox.information(self, _tr("Testing"), _tr("Attempting to fetch one post with the tag '1girl'..."))
        try:
            posts, total = fetch_custom_booru_posts(config, "1girl", 1, 0)
            if posts:
                QMessageBox.information(self, _tr("Success!"), _tr("Successfully fetched a post!\nID: {id}\nURL: {url}").format(id=posts[0].get('id'), url=posts[0].get('file_url')))
            else:
                QMessageBox.warning(self, _tr("Test Failed"), _tr("The request succeeded, but no posts were returned. The API might be down or the configuration is incorrect."))
        except Exception as e:
            QMessageBox.critical(self, _tr("Test Failed"), _tr("An error occurred while testing the configuration:\n\n{e}").format(e=e))

class SettingsDialog(BaseDialog):
    def __init__(self, parent=None, custom_fonts_path=""):
        super().__init__(_tr("Settings"), parent)
        self.setMinimumWidth(600)
        self.custom_fonts_path = custom_fonts_path
        self.parent_app = parent # Store a reference to the main app

        self.tabs = QTabWidget()
        self.content_layout.addWidget(self.tabs)

        self._create_general_tab()
        self._create_appearance_tab()
        self._create_graphics_tab()
        self._create_api_tab()
        self._create_sources_tab()
        self._create_tags_tab()
        self._create_hotkeys_tab()

        # Buttons
        row = QHBoxLayout()
        self.save_btn = QPushButton(qta.icon('fa5s.save'), _tr(" Save")); self.save_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton(qta.icon('fa5s.times'), _tr(" Cancel")); self.cancel_btn.clicked.connect(self.reject)
        row.addStretch(); row.addWidget(self.save_btn); row.addWidget(self.cancel_btn); 
        self.content_layout.addLayout(row)

        # Connections for buttons
        self.clear_history_btn.clicked.connect(parent.clear_search_history)
        self.new_btn.clicked.connect(self.new_theme); self.edit_btn.clicked.connect(self.edit_selected_theme)
        self.delete_btn.clicked.connect(self.delete_selected_theme); self.import_btn.clicked.connect(self.import_theme)
        self.export_btn.clicked.connect(self.export_theme)
        self.help_btn.clicked.connect(self.show_styling_help)
        self.new_booru_btn.clicked.connect(self.add_booru)
        self.edit_booru_btn.clicked.connect(self.edit_booru)
        self.delete_booru_btn.clicked.connect(self.delete_booru)
        self.reset_app_btn.clicked.connect(self.clear_all_data)

    def _on_allow_explicit_changed(self, state):
        """Enable/disable sub-options when the main explicit setting changes."""
        # This method is now a placeholder. The toggles are independent.
        pass

    def _on_allow_loli_shota_changed(self, state):
        pass

    def _on_allow_bestiality_changed(self, state):
        pass

    def _create_general_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.language_selector = QComboBox()
        # Sort languages alphabetically for consistent ordering, keeping English at the top.
        sorted_languages = sorted(
            (item for item in SUPPORTED_LANGUAGES.items() if item[0] != 'en'),
            key=lambda item: item[1]
        )
        self.language_selector.addItem(SUPPORTED_LANGUAGES.get('en', 'English'), 'en')
        for code, name in sorted_languages:
            self.language_selector.addItem(name, code)

        current_lang_code = SETTINGS.get("language", "en")
        current_lang_index = self.language_selector.findData(current_lang_code)
        if current_lang_index != -1:
            self.language_selector.setCurrentIndex(current_lang_index)

        self.clear_history_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Clear Search History"))
        self.clear_history_btn.setToolTip(_tr("Clears the dropdown history for the search bar."))

        self.allow_explicit = QCheckBox(_tr("Allow Explicit/NSFW Content"))
        self.allow_explicit.setIcon(qta.icon('fa5s.exclamation-triangle', color='#ff6666'))
        self.allow_explicit.setChecked(SETTINGS.get("allow_explicit", False))
        self.allow_explicit.setToolTip(_tr("By enabling this, YOU assume full responsibility. This app is NOT liable.\nNSFW content is prohibited under age 18\nYou must comply with your local laws\nDeactivating this blacklist is YOUR choice and liability"))
        self.allow_explicit.stateChanged.connect(self._on_allow_explicit_changed)

        self.allow_loli_shota = QCheckBox(_tr("Allow 'loli' and 'shota' content"))
        self.allow_loli_shota.setIcon(qta.icon('fa5s.exclamation-triangle', color='#ff6666'))
        self.allow_loli_shota.setChecked(SETTINGS.get("allow_loli_shota", False))
        self.allow_loli_shota.setToolTip(_tr("Shotacon/Lolicon content is ILLEGAL in many countries.\nBy enabling this, YOU are solely responsible for compliance with local laws\nThis app and its developer CANNOT be held liable for any legal consequences\nDrawn child exploitation material violates laws in most jurisdictions\nYOU must verify the legality in your country before enabling"))
        self.allow_loli_shota.stateChanged.connect(self._on_allow_loli_shota_changed)

        self.allow_bestiality = QCheckBox(_tr("Allow 'bestiality' content"))
        self.allow_bestiality.setIcon(qta.icon('fa5s.exclamation-triangle', color='#ff6666'))
        self.allow_bestiality.setChecked(SETTINGS.get("allow_bestiality", False))
        self.allow_bestiality.setToolTip(_tr("Zoophilia/Bestiality content is ILLEGAL in many countries.\nBy enabling this, YOU are solely responsible for legal compliance\nThis app and its developer CANNOT be held liable\nDeactivating this blacklist is YOUR choice - assume full liability\nCheck your local laws before enabling"))
        self.allow_bestiality.stateChanged.connect(self._on_allow_bestiality_changed)

        self.allow_guro = QCheckBox(_tr("Allow 'guro' content"))
        self.allow_guro.setIcon(qta.icon('fa5s.exclamation-triangle', color='#ff6666'))
        self.allow_guro.setChecked(SETTINGS.get("allow_guro", False))
        self.allow_guro.setToolTip(_tr("Extreme violence/gore content.\nBy enabling this, YOU assume full responsibility\nThis app is NOT liable for exposure to graphic content\nDeactivating this blacklist is YOUR conscious choice"))

        self.show_download_notification = QCheckBox(_tr("Show notification on single download"))
        self.show_download_notification.setChecked(SETTINGS.get("show_download_notification", True))
        self.show_download_notification.setToolTip(_tr("If unchecked, no popup will be shown after downloading a single file."))

        self.enable_recommendations = QCheckBox(_tr("Enable Personalized Recommendations"))
        self.enable_recommendations.setChecked(SETTINGS.get("enable_recommendations", True))
        self.enable_recommendations.setToolTip("Automatically adds tags you seem to like to your searches to improve results.\n(e.g., searching 'cat_girl' might become 'cat_girl ~blue_eyes ~long_hair')")
        
        self.fetch_all_site_stats = QCheckBox(_tr("Fetch total post counts from all sites on startup"))
        self.fetch_all_site_stats.setChecked(SETTINGS.get("fetch_all_site_stats", True))
        self.fetch_all_site_stats.setToolTip(_tr("If disabled, the Home tab will not make requests to unselected APIs to get total post counts."))

        self.download_dir = QLineEdit(SETTINGS.get("download_dir", os.path.abspath("downloads")))
        self.pick_dir_btn = QPushButton(qta.icon('fa5s.folder-open'), _tr(" Choose…"))
        self.pick_dir_btn.clicked.connect(self.pick_dir)
        dd = QHBoxLayout(); dd.addWidget(self.download_dir); dd.addWidget(self.pick_dir_btn)

        self.temp_cleanup_minutes = QSpinBox()
        self.temp_cleanup_minutes.setRange(1, 240)
        self.temp_cleanup_minutes.setValue(int(SETTINGS.get("temp_cleanup_minutes", 5)))
        self.temp_cleanup_minutes.setSuffix(_tr(" min"))

        form.addRow(_tr("Language:"), self.language_selector)
        
        
        content_layout = QVBoxLayout(); content_layout.setSpacing(5); content_layout.setContentsMargins(0,0,0,0)
        content_layout.addWidget(self.allow_explicit)
        content_layout.addWidget(self.allow_loli_shota)
        content_layout.addWidget(self.allow_bestiality)
        content_layout.addWidget(self.allow_guro)
        form.addRow(_tr("Content:"), content_layout)
        form.addRow(_tr("Downloads:"), self.show_download_notification)
        form.addRow(_tr("Personalization:"), self.enable_recommendations)
        form.addRow(_tr("Network:"), self.fetch_all_site_stats)

        form.addRow(_tr("Download folder:"), QWidget()) # Use a dummy widget for layout
        form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget().setLayout(dd)
        form.addRow(_tr("Temp cleanup:"), self.temp_cleanup_minutes)
        form.addRow(_tr("Search History:"), self.clear_history_btn)

        # Danger Zone
        self.danger_group = QGroupBox(_tr("Danger Zone"))
        self.danger_group.setObjectName("danger_zone")
        danger_layout = QVBoxLayout()
        self.danger_group.setLayout(danger_layout)

        self.launch_incognito_btn = QPushButton(qta.icon('fa5s.user-secret'), " Launch Incognito Window")
        self.launch_incognito_btn.setToolTip("Opens a new, separate window for private browsing.\nHistory, favorites, and settings are not saved.")
        self.launch_incognito_btn.clicked.connect(self.parent_app.launch_incognito_window)
        danger_layout.addWidget(self.launch_incognito_btn)

        self.reset_app_btn = QPushButton(qta.icon('fa5s.exclamation-triangle'), " Clear All App Data & Reset")
        self.reset_app_btn.setObjectName("reset_button")
        self.reset_app_btn.setToolTip("Deletes all settings, history, and favorites and closes the app.\nThis does NOT delete your downloaded images.\nThis action cannot be undone.")
        danger_layout.addWidget(self.reset_app_btn)
        
        self._on_allow_explicit_changed(self.allow_explicit.checkState()) # Set initial state

        form.addRow(self.danger_group)
        self.tabs.addTab(tab, qta.icon('fa5s.cogs'), _tr("General"))

    def _create_tags_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.pref_tags = QPlainTextEdit(SETTINGS.get("preferred_tags", "rating:safe"))
        self.pref_tags.setMaximumHeight(80)
        self.black_tags = QPlainTextEdit(SETTINGS.get("blacklisted_tags", ""))
        self.black_tags.setMaximumHeight(80)
        form.addRow(_tr("Preferred Tags (one per line):"), self.pref_tags)
        form.addRow(_tr("Blacklisted tags:"), self.black_tags)
        self.tabs.addTab(tab, qta.icon('fa5s.tags'), _tr("Tags"))

    def _create_appearance_tab(self):
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout()
        appearance_tab.setLayout(appearance_layout)
        theme_form = QFormLayout()
        self.theme_selector = QComboBox()
        theme_form.addRow(_tr("Active Theme:"), self.theme_selector)
        appearance_layout.addLayout(theme_form)
        self.theme_group = QGroupBox(_tr("Manage Custom Themes"))
        theme_group_layout = QVBoxLayout()
        self.theme_group.setLayout(theme_group_layout)
        self.themes_list = QListWidget()
        self.themes_list.setToolTip(_tr("List of your custom themes. Double-click to edit."))
        self.themes_list.itemDoubleClicked.connect(self.edit_selected_theme)
        theme_group_layout.addWidget(self.themes_list)
        theme_buttons = QHBoxLayout()
        self.new_btn = QPushButton(qta.icon('fa5s.plus-circle'), _tr(" New"))
        self.edit_btn = QPushButton(qta.icon('fa5s.edit'), _tr(" Edit"))
        self.delete_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Delete"))
        self.import_btn = QPushButton(qta.icon('fa5s.file-import'), _tr(" Import"))
        self.export_btn = QPushButton(qta.icon('fa5s.file-export'), _tr(" Export"))
        self.help_btn = QPushButton(qta.icon('fa5s.question-circle'), _tr(" Styling Help"))
        theme_buttons.addWidget(self.new_btn); theme_buttons.addWidget(self.edit_btn); theme_buttons.addWidget(self.delete_btn)
        theme_buttons.addStretch()
        theme_buttons.addWidget(self.import_btn); theme_buttons.addWidget(self.export_btn); theme_buttons.addWidget(self.help_btn)
        theme_group_layout.addLayout(theme_buttons)
        appearance_layout.addWidget(self.theme_group)
        self.populate_themes()
        self.tabs.addTab(appearance_tab, qta.icon('fa5s.palette'), _tr("Appearance"))

    def _create_sources_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        sources_group = QGroupBox(_tr("Enabled API Sources"))
        sources_group_layout = QVBoxLayout()
        sources_group.setLayout(sources_group_layout)
        self.source_checkboxes = {}
        all_sources = [
            "Gelbooru", "Danbooru", "Konachan", "Yandere", "Rule34", "Hypnohub", "Zerochan", "Waifu.pics"
        ]
        custom_booru_names = [b['name'] for b in self.parent_app.custom_boorus]
        all_sources.extend(custom_booru_names)

        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
        for source_name in all_sources:
            checkbox = QCheckBox(source_name)
            checkbox.setChecked(source_name in enabled_sources)
            sources_group_layout.addWidget(checkbox)
            self.source_checkboxes[source_name] = checkbox
        sources_group_layout.addStretch()
        layout.addWidget(sources_group, 0, Qt.AlignTop)

        # Custom Sources Tab
        custom_sources_tab = QWidget()
        custom_sources_layout = QVBoxLayout()
        custom_sources_tab.setLayout(custom_sources_layout)
        
        # Add disclaimer warning
        disclaimer = QLabel(_tr("⚠️ Custom sources may have parsing errors or bugs if the app is not fully compatible with their API structure. Please report any issues. Right-click to select sources and left-click to enable/disable. Save settings after making changes and then reopen them to ensure sources appear and are usable."))
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #FFA500; font-style: italic;")
        custom_sources_layout.addWidget(disclaimer)
        
        self.boorus_list_widget = QListWidget()
        self.boorus_list_widget.itemDoubleClicked.connect(self.edit_booru)
        custom_sources_layout.addWidget(self.boorus_list_widget)
        self.boorus_list_widget.itemClicked.connect(self._toggle_booru_enabled)  # Toggle enable/disable on click
        booru_button_row = QHBoxLayout()
        self.new_booru_btn = QPushButton(qta.icon('fa5s.plus'), _tr(" New"))
        self.edit_booru_btn = QPushButton(qta.icon('fa5s.edit'), _tr(" Edit"))
        self.delete_booru_btn = QPushButton(qta.icon('fa5s.trash-alt'), _tr(" Delete"))
        booru_button_row.addWidget(self.new_booru_btn); booru_button_row.addWidget(self.edit_booru_btn); booru_button_row.addWidget(self.delete_booru_btn)
        booru_button_row.addStretch()
        custom_sources_layout.addLayout(booru_button_row)
        self.populate_boorus_list()
        layout.addWidget(custom_sources_tab)
        self.tabs.addTab(tab, qta.icon('fa5s.server'), _tr("Sources"))

    def _create_hotkeys_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.hotkey_edits = {}
        current_hotkeys = SETTINGS.get("hotkeys", DEFAULT_HOTKEYS)

        for action, seq_str in sorted(DEFAULT_HOTKEYS.items()):
            label_text = _tr(action.replace("_", " ").title())
            current_seq_str = current_hotkeys.get(action, seq_str)
            key_edit = QKeySequenceEdit(QKeySequence(current_seq_str))
            self.hotkey_edits[action] = key_edit
            form.addRow(label_text, key_edit)

        layout.addLayout(form)
        layout.addStretch()

        reset_hotkeys_btn = QPushButton(qta.icon('fa5s.undo'), _tr(" Reset Hotkeys to Default"))
        reset_hotkeys_btn.clicked.connect(self.reset_hotkeys)
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_row.addWidget(reset_hotkeys_btn)
        layout.addLayout(reset_row)
        self.tabs.addTab(tab, qta.icon('fa5s.keyboard'), _tr("Hotkeys"))

    def _create_api_tab(self):
        gel_group = QGroupBox(_tr("Gelbooru API"))
        gel_form = QFormLayout()
        gel_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.gel_user = QLineEdit(SETTINGS.get("gelbooru", {}).get("user_id", ""))
        self.gel_key  = QLineEdit(SETTINGS.get("gelbooru", {}).get("api_key", "")); self.gel_key.setEchoMode(QLineEdit.Password)
        gel_form.addRow(_tr("Gelbooru User ID:"), self.gel_user)
        gel_form.addRow(_tr("Gelbooru API Key:"), self.gel_key)
        gel_group.setLayout(gel_form)

        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)
        api_layout.setAlignment(Qt.AlignTop)
        api_layout.addWidget(gel_group)
        # Danbooru Group
        dan_group = QGroupBox(_tr("Danbooru API"))
        dan_form = QFormLayout()
        dan_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.db_login = QLineEdit(SETTINGS.get("danbooru", {}).get("login", ""))
        self.db_key   = QLineEdit(SETTINGS.get("danbooru", {}).get("api_key", "")); self.db_key.setEchoMode(QLineEdit.Password)
        dan_form.addRow(_tr("Danbooru Login:"), self.db_login)
        dan_form.addRow(_tr("Danbooru API Key:"), self.db_key)
        dan_group.setLayout(dan_form)
        api_layout.addWidget(dan_group)

        # Rule34 Group
        r34_group = QGroupBox(_tr("Rule34 API"))
        r34_form = QFormLayout()
        r34_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.r34_user = QLineEdit(SETTINGS.get("rule34", {}).get("user_id", ""))
        self.r34_key  = QLineEdit(SETTINGS.get("rule34", {}).get("api_key", "")); self.r34_key.setEchoMode(QLineEdit.Password)
        r34_form.addRow(_tr("Rule34 User ID:"), self.r34_user)
        r34_form.addRow(_tr("Rule34 API Key:"), self.r34_key)
        r34_group.setLayout(r34_form)
        api_layout.addWidget(r34_group)

        # AI API Group
        ai_api_group = QGroupBox(_tr("AI API"))
        ai_api_form = QFormLayout()
        ai_api_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        # API Provider Selection
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(["OpenRouter", "Google Gemini (Experimental)"])
        self.ai_provider_combo.setCurrentText(SETTINGS.get("ai_provider", "OpenRouter"))
        ai_api_form.addRow(_tr("AI Provider:"), self.ai_provider_combo)
        
        # OpenRouter Key
        self.ai_api_key = QLineEdit(SETTINGS.get("ai_api_key", "")); self.ai_api_key.setEchoMode(QLineEdit.Password)
        self.ai_endpoint = QLineEdit(SETTINGS.get("ai_endpoint", "https://openrouter.ai/api/v1/chat/completions"))
        ai_api_form.addRow(_tr("OpenRouter API Key:"), self.ai_api_key)
        ai_api_form.addRow(_tr("OpenRouter Endpoint:"), self.ai_endpoint)
        
        # Gemini Key
        self.gemini_api_key = QLineEdit(SETTINGS.get("gemini_api_key", "")); self.gemini_api_key.setEchoMode(QLineEdit.Password)
        self.gemini_api_key.setToolTip(_tr("Get your API key from https://ai.google.dev/"))
        ai_api_form.addRow(_tr("Gemini API Key:"), self.gemini_api_key)
        
        ai_api_group.setLayout(ai_api_form)
        api_layout.addWidget(ai_api_group)
        self.tabs.addTab(api_tab, qta.icon('fa5s.key'), _tr("APIs"))

    def _create_graphics_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.window_mode_combo = QComboBox()
        self.window_mode_combo.addItems([_tr("Windowed"), _tr("Windowed Borderless"), _tr("Fullscreen")])
        self.window_mode_combo.setCurrentText(SETTINGS.get("window_mode", _tr("Windowed")))
        form.addRow(_tr("Window Mode:"), self.window_mode_combo)

        self.window_size_combo = QComboBox()
        
        # Get screen resolution to populate available sizes
        try:
            from PyQt5.QtWidgets import QApplication
            screen_size = QApplication.primaryScreen().size()
            screen_w, screen_h = screen_size.width(), screen_size.height()
        except Exception:
            screen_w, screen_h = 1920, 1080 # Fallback

        all_resolutions = {
            "1280x720 (HD)", "1600x900 (HD+)", "1920x1080 (Full HD)", 
            "2560x1440 (QHD)", "3840x2160 (4K UHD)", "7680x4320 (8K UHD)"
        }
        
        available_resolutions = []
        for res_str in all_resolutions:
            w, h = map(int, res_str.split(' ')[0].split('x'))
            if w <= screen_w and h <= screen_h:
                available_resolutions.append(res_str)

        self.window_size_combo.addItems(available_resolutions + [_tr("Custom")])
        self.window_size_combo.setCurrentText(SETTINGS.get("window_size_preset", "1920x1080 (Full HD)"))
        form.addRow(_tr("Window Size:"), self.window_size_combo)

        self.custom_width_spin = QSpinBox()
        self.custom_width_spin.setRange(800, 7680); self.custom_width_spin.setSuffix(" px")
        self.custom_width_spin.setValue(SETTINGS.get("custom_window_width", 1820))
        self.custom_height_spin = QSpinBox()
        self.custom_height_spin.setRange(600, 4320); self.custom_height_spin.setSuffix(" px")
        self.custom_height_spin.setValue(SETTINGS.get("custom_window_height", 1080))

        custom_size_layout = QHBoxLayout()
        custom_size_layout.addWidget(self.custom_width_spin); custom_size_layout.addWidget(QLabel("x")); custom_size_layout.addWidget(self.custom_height_spin)
        self.custom_size_widget = QWidget(); self.custom_size_widget.setLayout(custom_size_layout)
        form.addRow(_tr("Custom Size:"), self.custom_size_widget)

        def on_window_size_changed(text): self.custom_size_widget.setVisible(text == _tr("Custom"))
        self.window_size_combo.currentTextChanged.connect(on_window_size_changed)
        on_window_size_changed(self.window_size_combo.currentText())

        self.auto_scale_grid_check = QCheckBox(_tr("Auto-scale grid to fit window width"))
        self.auto_scale_grid_check.setChecked(SETTINGS.get("auto_scale_grid", False))
        self.auto_scale_grid_check.setToolTip(_tr("When enabled, automatically adjusts column count and thumbnail size to best fit the window. Manual settings below will be ignored."))
        form.addRow(self.auto_scale_grid_check)

        def on_auto_scale_toggled(checked):
            self.grid_columns.setDisabled(checked)
            self.thumbnail_size.setToolTip(_tr("The ideal size for thumbnails when auto-scaling is enabled.") if checked else "")

        self.grid_columns = QSpinBox()
        self.grid_columns.setRange(2, 10)
        self.grid_columns.setValue(SETTINGS.get("grid_columns", 5))
        self.grid_columns.setToolTip(_tr("Number of columns in the thumbnail grid. Ignored when auto-scaling is enabled."))
        form.addRow(_tr("Grid Columns:"), self.grid_columns)
        
        self.thumbnail_size = QSpinBox()
        self.thumbnail_size.setRange(80, 300)
        self.thumbnail_size.setValue(SETTINGS.get("thumbnail_size", 150))
        self.thumbnail_size.setSuffix(" px")
        self.thumbnail_size.setToolTip(_tr("The size of the square thumbnails in the grid."))
        form.addRow(_tr("Thumbnail Size:"), self.thumbnail_size)

        self.auto_scale_grid_check.toggled.connect(on_auto_scale_toggled)
        on_auto_scale_toggled(self.auto_scale_grid_check.isChecked()) # Set initial state

        self.video_playback_method_combo = QComboBox()
        self.video_playback_method_combo.addItems([_tr("Download First (Reliable)"), _tr("Stream (Experimental)")])
        self.video_playback_method_combo.setToolTip(_tr("How videos in the media viewer are handled.\n'Download First' is more stable and has better seeking.\n'Stream' loads faster but may have issues with some video formats or seeking."))
        self.video_playback_method_combo.setCurrentText(SETTINGS.get("video_playback_method", _tr("Download First (Reliable)")))
        form.addRow(_tr("Video Playback:"), self.video_playback_method_combo)

        # self.potato_mode_check = QCheckBox(_tr("Enable low-resource 'Potato Mode'"))
        # self.potato_mode_check.setChecked(SETTINGS.get("potato_mode", False))
        # self.potato_mode_check.setToolTip(_tr("Reduces animations, disables some features, and lowers thumbnail quality to save resources."))
        # form.addRow(self.potato_mode_check)

        # self.cpu_limit_spin = QSpinBox()
        # self.cpu_limit_spin.setRange(1, 100); self.cpu_limit_spin.setSuffix(" %"); self.cpu_limit_spin.setSpecialValueText(_tr("Disabled"))
        # self.cpu_limit_spin.setValue(SETTINGS.get("cpu_limit", 1)) # 1 is disabled
        # form.addRow(_tr("Max CPU Usage:"), self.cpu_limit_spin)

        # self.ram_limit_spin = QSpinBox()
        # self.ram_limit_spin.setRange(1, 16000); self.ram_limit_spin.setSuffix(" MB"); self.ram_limit_spin.setSpecialValueText(_tr("Disabled"))
        # self.ram_limit_spin.setValue(SETTINGS.get("ram_limit", 1)) # 1 is disabled
        # form.addRow(_tr("Max RAM Usage:"), self.ram_limit_spin)
        self.tabs.addTab(tab, qta.icon('fa5s.desktop'), _tr("Graphics"))

    def reset_hotkeys(self):
        """Resets the hotkey editor fields to their default values."""
        reply = QMessageBox.question(self, _tr("Reset Hotkeys"), _tr("Are you sure you want to reset all hotkeys to their default values?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            for action, seq_str in DEFAULT_HOTKEYS.items():
                if action in self.hotkey_edits:
                    self.hotkey_edits[action].setKeySequence(QKeySequence(seq_str))
            QMessageBox.information(self, _tr("Hotkeys Reset"), _tr("All hotkeys have been reset to their default values. Click Save to apply."))

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose download folder", self.download_dir.text())
        if d:
            self.download_dir.setText(d)

    def import_theme(self):
        import shutil
        filepath, _ = QFileDialog.getOpenFileName(self, _tr("Import Snekbooru Theme"), "", _tr("Snekbooru Stylesheets (*.snek.css);;All Files (*)"))
        if filepath:
            try:
                themes_path = get_themes_path()
                dest_path = os.path.join(themes_path, os.path.basename(filepath))
                if os.path.exists(dest_path):
                    reply = QMessageBox.question(self, "Overwrite Theme", f"A theme named '{os.path.basename(filepath)}' already exists. Overwrite it?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply == QMessageBox.No: return
                shutil.copy(filepath, dest_path)
                self.populate_themes()
                QMessageBox.information(self, _tr("Theme Imported"), _tr("Theme '{filename}' imported successfully.").format(filename=os.path.basename(filepath)))
            except Exception as e:
                QMessageBox.critical(self, _tr("Import Error"), _tr("Could not import the theme file.\n\nError: {error}").format(error=e))

    def export_theme(self):
        import shutil
        current_item = self.themes_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, _tr("Export Error"), _tr("Please select a custom theme from the list to export."))
            return
        theme_name = current_item.text()
        save_path, _ = QFileDialog.getSaveFileName(self, _tr("Export Snekbooru Theme"), theme_name, _tr("Snekbooru Stylesheets (*.snek.css)"))
        if save_path:
            try:
                theme_path = os.path.join(get_themes_path(), theme_name)
                shutil.copy(theme_path, save_path)
                QMessageBox.information(self, _tr("Theme Exported"), _tr("Theme successfully exported to:\n{path}").format(path=save_path))
            except Exception as e:
                QMessageBox.critical(self, _tr("Export Error"), _tr("Could not export the theme file.\n\nError: {error}").format(error=e))

    def populate_themes(self):
        self.theme_selector.clear()
        self.themes_list.clear()
        self.theme_selector.addItems(["Dark (Default)", "Light (Default)"])
        custom_themes = sorted(load_custom_themes().keys())
        self.theme_selector.addItems(custom_themes)
        self.themes_list.addItems(custom_themes)
        current_theme = SETTINGS.get("active_theme", "Dark (Default)")
        self.theme_selector.setCurrentText(current_theme)

    def new_theme(self):
        theme_name, ok = QInputDialog.getText(self, _tr("New Theme"), _tr("Enter a name for the new theme (e.g., my_theme.snek.css):"))
        if ok and theme_name:
            if not theme_name.endswith(".snek.css"):
                theme_name += ".snek.css"
            theme_path = os.path.join(get_themes_path(), theme_name)
            if os.path.exists(theme_path):
                QMessageBox.warning(self, _tr("Error"), _tr("A theme with that name already exists."))
                return
            editor = ThemeEditorDialog(theme_path, EXAMPLE_STYLESHEET, self)
            if editor.exec_() == QDialog.Accepted:
                self.populate_themes()
                self.themes_list.setCurrentRow(self.themes_list.count() - 1)

    def edit_selected_theme(self):
        current_item = self.themes_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, _tr("Edit Error"), _tr("Please select a custom theme from the list to edit."))
            return
        theme_name = current_item.text()
        theme_path = os.path.join(get_themes_path(), theme_name)
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                content = f.read()
            editor = ThemeEditorDialog(theme_path, content, self)
            editor.exec_() # The editor handles saving, no need to check result
        except Exception as e:
            QMessageBox.critical(self, _tr("Edit Error"), _tr("Could not open theme for editing.\n\nError: {error}").format(error=e))

    def delete_selected_theme(self):
        current_item = self.themes_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, _tr("Delete Error"), _tr("Please select a custom theme from the list to delete."))
            return
        theme_name = current_item.text()
        reply = QMessageBox.question(self, _tr("Confirm Delete"), _tr("Are you sure you want to permanently delete the theme '{theme_name}'?").format(theme_name=theme_name), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            os.remove(os.path.join(get_themes_path(), theme_name))
            self.populate_themes()

    def populate_boorus_list(self):
        self.boorus_list_widget.clear()
        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
        for booru in self.parent_app.custom_boorus:
            # Show + if not enabled, - if enabled
            status_indicator = "✓" if booru['name'] in enabled_sources else "○"
            display_name = f"{booru['name']}  {status_indicator}"
            self.boorus_list_widget.addItem(display_name)

    def _toggle_booru_enabled(self, item):
        """Toggle enable/disable of custom booru by clicking on it."""
        display_name = item.text()
        # Extract the booru name (everything before the status indicator)
        booru_name = display_name.rsplit('  ', 1)[0]
        
        enabled_sources = SETTINGS.get("enabled_sources", ["Gelbooru"])
        if booru_name in enabled_sources:
            enabled_sources.remove(booru_name)
        else:
            enabled_sources.append(booru_name)
        
        SETTINGS["enabled_sources"] = enabled_sources
        from snekbooru.core.config import save_settings
        save_settings(SETTINGS)
        self.populate_boorus_list()

    def add_booru(self):
        editor = BooruEditorDialog(parent=self)
        if editor.exec_() == QDialog.Accepted:
            config = editor.get_config()
            if config:
                if any(b['name'].lower() == config['name'].lower() for b in self.parent_app.custom_boorus):
                    QMessageBox.warning(self, _tr("Duplicate Name"), _tr("A custom source with this name already exists."))
                    return
                self.parent_app.custom_boorus.append(config)
                save_custom_boorus(self.parent_app.custom_boorus)
                self.populate_boorus_list()

    def edit_booru(self):
        current_item = self.boorus_list_widget.currentItem()
        if not current_item: return
        # Extract booru name from display format 'name  indicator'
        display_name = current_item.text()
        selected_name = display_name.rsplit('  ', 1)[0] if '  ' in display_name else display_name
        booru_to_edit = next((b for b in self.parent_app.custom_boorus if b['name'] == selected_name), None)
        if not booru_to_edit: return
        editor = BooruEditorDialog(booru_config=booru_to_edit, parent=self)
        if editor.exec_() == QDialog.Accepted:
            new_config = editor.get_config()
            if new_config:
                if new_config['name'].lower() != selected_name.lower() and any(b['name'].lower() == new_config['name'].lower() for b in self.parent_app.custom_boorus):
                    QMessageBox.warning(self, _tr("Duplicate Name"), _tr("A custom source with this name already exists."))
                    return
                for i, b in enumerate(self.parent_app.custom_boorus):
                    if b['name'] == selected_name: self.parent_app.custom_boorus[i] = new_config; break
                save_custom_boorus(self.parent_app.custom_boorus)
                self.populate_boorus_list()

    def delete_booru(self):
        current_item = self.boorus_list_widget.currentItem()
        if not current_item: return
        # Extract booru name from display format 'name  indicator'
        display_name = current_item.text()
        booru_name = display_name.rsplit('  ', 1)[0] if '  ' in display_name else display_name
        reply = QMessageBox.question(self, _tr("Confirm Delete"), _tr("Are you sure you want to delete the custom source '{name}'?").format(name=booru_name), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.parent_app.custom_boorus = [b for b in self.parent_app.custom_boorus if b['name'] != booru_name]
            save_custom_boorus(self.parent_app.custom_boorus)
            self.populate_boorus_list()

    def clear_all_data(self):
        """Clear all app data and reset to default settings."""
        reply = QMessageBox.warning(self, _tr("Clear All Data"), 
            _tr("This will delete all settings, history, favorites, and custom sources.\nYour downloaded images will NOT be deleted.\nThis action cannot be undone.\n\nAre you sure?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Clear all data in parent app
            self.parent_app.clear_all_data()
            # Close the dialog
            self.reject()

    def show_styling_help(self):
        """Displays a dialog with help on how to style the application."""
        md_text = f"""
# The sCSS Styling System

Snekbooru's appearance is controlled by **sCSS**, a powerful styling language that gives you deep control over the look and feel of the application. This guide will walk you through how to create your own themes.

### Custom Fonts

You can add your own fonts to use in custom themes. Place your font files (`.ttf` or `.otf`) into the following directory and restart the application:

```
{self.custom_fonts_path}
```

After restarting, you can use the font's family name in your stylesheet:

```css
* {{{{
    font-family: 'My Cool Font';
}}}}
```

### Global Styles & Basic Properties

The `*` selector applies styles to all elements. `sWidget` targets the base style for all widgets unless overridden.

```css
* {{ 
    font-family: 'Segoe UI', Arial, sans-serif; /* Specify preferred fonts */
    font-size: 14px; /* Default font size */
}}

sWidget {{ 
    background-color: #1e1e1e; /* Background for most widgets */
    color: #eaeaea; /* Default text color */
    border: none; /* Remove default borders */
    padding: 5px; /* Default padding */
}}
```

Common properties include: `background-color`, `color`, `border`, `border-radius`, `padding`, `margin`, `font-size`, `font-family`, `font-weight`, `min-width`, `max-width`, `min-height`, `max-height`, `text-align`.

### sWidget Type Selectors

To style a specific type of widget, use its **s-prefixed** class name. This is the foundation of sCSS.

*   **sCheckBox:** Checkboxes.
*   **sComboBox:** Dropdown menus.
*   **sDialog:** Dialog windows (like Settings or this one).
*   **sFrame:** A basic container, often used for video.
*   **sGroupBox:** Grouping containers with a title and border.
*   **sHeaderView:** The headers for tables.
*   **sLabel:** Text labels and image displays.
*   **sLineEdit:** Single-line text input fields.
*   **sListWidget:** The search history and downloads lists.
*   **sMenu:** Context (right-click) menus.
*   **sPlainTextEdit:** Multi-line text areas.
*   **sProgressBar:** Progress bars.
*   **sPushButton:** All buttons.
*   **sScrollBar:** The scrollbars themselves.
*   **sScrollArea:** The scrollable viewports for grids and text.
*   **sSlider:** Sliders (e.g., for volume).
*   **sSpinBox:** Numeric input fields with up/down arrows.
*   **sSplitter:** The draggable handles between panes.
*   **sTabBar:** The bar that holds the clickable tabs.
*   **sTabWidget:** The main tab container.
*   **sTableView:** The favorites and downloads tables.
*   **sTextBrowser:** Rich text display areas (like this help dialog).
*   **sWidget:** The base of all other widgets.

```css
/* Example for input fields */
sLineEdit, sPlainTextEdit, sComboBox, sSpinBox {{
    background: #2a2a2a;
    color: #eaeaea;
    border: 1px solid #444;
    border-radius: 4px;
}}

sPushButton {{
    background: #3a3a3a;
    padding: 8px;
}}
```

### Pseudo-States

Apply styles based on a widget's state (e.g., when hovered over, pressed, or disabled):

*   `:hover`: Mouse cursor is over the widget.
*   `:pressed`: Widget is being clicked.
*   `:disabled`: Widget is inactive.
*   `:checked`: For checkable widgets (e.g., `sCheckBox`).
*   `:selected`: For items in lists/tables (e.g., `sListWidget::item:selected`).

```css
sPushButton:hover {{
    background: #4a4a4a;
    border-color: #666;
}}

sPushButton:pressed {{
    background: #5a5a5a;
}}

sPushButton:disabled {{
    background: #1a1a1a;
    color: #666;
}}
```

### Sub-Controls & Parts

Many complex widgets are composed of sub-controls that can be styled individually using `::` (double colon):

*   `sTabWidget::pane`: The content area of a tab widget.
*   `sTabBar::tab`: An individual tab in a tab bar.
*   `sGroupBox::title`: The title text of a group box.
*   `sProgressBar::chunk`: The filled portion of a progress bar.
*   `sComboBox::drop-down`: The dropdown arrow button.
*   `sScrollBar::handle`: The draggable part of a scrollbar.

```css
sTabWidget::pane {{ /* The container for tab content */
    border: 1px solid #444;
}}

sTabBar::tab {{ /* An individual, unselected tab */
    background: #2a2a2a;
    color: #aaa;
    padding: 8px 16px;
}}

sTabBar::tab:selected {{ /* The currently active tab */
    background: #3a3a3a;
    color: #fff;
}}
```

### Styling by ID (`objectName`)

Some elements have a unique ID (called an `objectName` in Qt) for highly specific styling. This is the most powerful way to target a single, specific widget. These are prefixed with ``, just like in web CSS.

*   `sWidget#main_window`: The main application window. **Use this to set a global background image.**
*   `sTabWidget#main_tabs`: The main tab widget for Home, Browser, Favorites, etc.
*   `sWidget#home_tab`: The content area of the Home tab.
*   `sWidget#browser_tab`: The content area of the Browser tab.
*   `sWidget#favorites_tab`: The content area of the Favorites tab.
*   `sWidget#downloads_tab`: The content area of the Downloads tab.
*   `sWidget#minigames_tab`: The content area of the Minigames tab.
*   `sWidget#ai_tab`: The content area of the AI tab.
*   `sFrame#video_frame`: The black frame that contains the video in the full media viewer.
*   `sLabel#title`: The main "Welcome to Snekbooru" title on the Home tab.
*   `sLabel#app_logo_mini`: The small logo in the top-left corner.
*   `sLabel#total_posts_label`: The large number displaying total posts.
*   `sPlainTextEdit#post_inspector_info`: The text area in the main browser's Post Inspector.
*   `sPlainTextEdit#favorites_inspector_info`: The text area in the Favorites tab's Post Inspector.
*   `sTextBrowser#ai_chat_history_browser`: The AI chat history display.
*   `sPlainTextEdit#ai_chat_input_area`: The text input box for the AI chat.
*   `sGroupBox#danger_zone`: The "Danger Zone" group box in settings.
*   `sPushButton#reset_button`: The "Clear All App Data" button.

### Styling Title Bars

The main window and all dialogs use custom title bars that can be styled using their `objectName`.

*   `sWidget#main_window_title_bar`: The title bar for the main application window.
*   `sWidget#dialog_title_bar`: The title bar for all dialog windows (like Settings, Hentai Viewer, etc.).
*   `sLabel#custom_title_bar_label`: The text label within any custom title bar.
*   `sToolButton#title_bar_button`: Any button on a title bar (minimize, maximize, close).
*   `sToolButton#close_button`: Specifically targets the close button on any title bar.

```css
sWidget#main_window_title_bar {{ background-color: #333; }}
sWidget#dialog_title_bar {{ background-color: #2a2a2a; }}
sToolButton#close_button:hover {{ background-color: #c33; }}
```

```css
sLabel#title {{
    font-size: 48px;
    font-weight: bold;
    color: #5b5bff;
}}

sGroupBox#danger_zone {{
    border-color: #c33; /* Red border for danger zone */
}}

sPushButton#reset_button {{
    background-color: #400; /* Dark red background */
    color: #fcc; /* Light red text */
}}
```

### Styling with Classes

For more flexible styling, you can assign 'classes' to widgets and style them with a dot (`.`), just like in web CSS. This is perfect for styling groups of widgets differently without affecting all widgets of that type.

To use a class, you must first set the `class` property on a widget in the application's Python code (e.g., `my_widget.setProperty("class", "card")`). This is an advanced technique for users who wish to customize the application's source. Then, you can style it in your theme:

```css
/* Style any widget with the 'card' class */
.card {{
    background-color: #2a2a2a;
    border-radius: 8px;
    border: 1px solid #444;
}}
```

You can combine type, ID, and class selectors for very specific targeting: `sGroupBox#my-group.card`.

### Advanced Properties

*   **Gradients:** Use `qlineargradient` or `qradialgradient` for backgrounds.
    ```css
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2DE2E6, stop:1 #F706CF);
    ```
*   **Images:** Use `url("path/to/image.png")` for background images or icons. Paths can be absolute or relative to the stylesheet.
    ```css
    background-image: url("path/to/your/image.png");
    border-image: url("path/to/border.png") 3 3 3 3 stretch stretch; /* For complex borders */
    ```

### Final Notes

*   The sCSS system is powerful, but not all web CSS properties are available.
*   Layout is primarily handled by the application's structure, not stylesheets.
*   Experimentation is encouraged!
"""
        dlg = BaseDialog(_tr("Snekbooru Styling Help"), self)
        dlg.setMinimumSize(600, 500)

        text_browser = QTextBrowser()
        # Convert Markdown to HTML for display in QTextBrowser
        html_text = markdown.markdown(md_text, extensions=['fenced_code', 'codehilite'])
        html_text = f"<style>{PYGMENTS_CSS}</style>{html_text}"
        text_browser.setHtml(html_text)
        text_browser.setOpenExternalLinks(True)
        dlg.content_layout.addWidget(text_browser)

        close_button = QPushButton(_tr("Close"))
        close_button.clicked.connect(dlg.close)
        dlg.content_layout.addWidget(close_button)
        dlg.exec_()

    def values(self):
        dl_dir = self.download_dir.text().strip()
        if not dl_dir:
            from snekbooru.core.config import get_app_data_dir
            dl_dir = os.path.join(get_app_data_dir(), "data")

        enabled_sources = [name for name, checkbox in self.source_checkboxes.items() if checkbox.isChecked()]
        return {
            "enabled_sources": enabled_sources,
            "language": self.language_selector.currentData(),
            "gelbooru": {"user_id": self.gel_user.text().strip(), "api_key": self.gel_key.text().strip()},
            "danbooru": {"login": self.db_login.text().strip(), "api_key": self.db_key.text().strip()},
            "rule34": {"user_id": self.r34_user.text().strip(), "api_key": self.r34_key.text().strip()},
            "preferred_tags": self.pref_tags.toPlainText().strip(),
            "blacklisted_tags": self.black_tags.toPlainText().strip(),
            "active_theme": self.theme_selector.currentText(),
            "allow_explicit": self.allow_explicit.isChecked(),
            "allow_loli_shota": self.allow_loli_shota.isChecked(),
            "allow_guro": self.allow_guro.isChecked(),
            "allow_bestiality": self.allow_bestiality.isChecked(),
            "show_download_notification": self.show_download_notification.isChecked(),
            "enable_recommendations": self.enable_recommendations.isChecked(),
            "fetch_all_site_stats": self.fetch_all_site_stats.isChecked(),
            "download_dir": dl_dir,
            "temp_cleanup_minutes": self.temp_cleanup_minutes.value(),
            "grid_columns": self.grid_columns.value(), "thumbnail_size": self.thumbnail_size.value(),
            "ai_provider": self.ai_provider_combo.currentText(),
            "ai_api_key": self.ai_api_key.text().strip(),
            "ai_endpoint": self.ai_endpoint.text().strip(),
            "gemini_api_key": self.gemini_api_key.text().strip(),
            "hotkeys": {action: edit.keySequence().toString(QKeySequence.PortableText) for action, edit in self.hotkey_edits.items()},
            "window_mode": self.window_mode_combo.currentText(),
            "window_size_preset": self.window_size_combo.currentText(),
            "custom_window_width": self.custom_width_spin.value(),
            "custom_window_height": self.custom_height_spin.value(),
            "auto_scale_grid": self.auto_scale_grid_check.isChecked(),
            "video_playback_method": self.video_playback_method_combo.currentText(),
            # "potato_mode": self.potato_mode_check.isChecked(),
            # "cpu_limit": self.cpu_limit_spin.value(),
            # "ram_limit": self.ram_limit_spin.value(),
        }

class FirstRunDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(_tr("Welcome to Snekbooru - Initial Setup"), parent)
        self.setMinimumWidth(550)
        self.setModal(True)

        self.content_layout.setSpacing(15)

        welcome_label = QLabel(_tr("<h2>Welcome to Snekbooru!</h2>"
                               "<p>Please set up the essentials. You can change all of these and more in the main settings later.</p>"))
        welcome_label.setWordWrap(True)
        self.content_layout.addWidget(welcome_label)

        dl_group = QGroupBox("Download Directory")
        dl_layout = QHBoxLayout()
        dl_group.setLayout(dl_layout)
        from snekbooru.core.config import get_app_data_dir
        default_dl_path = os.path.join(get_app_data_dir(), "data")
        self.download_dir = QLineEdit(default_dl_path)
        pick_btn = QPushButton(qta.icon('fa5s.folder-open'), _tr(" Choose…"))
        pick_btn.clicked.connect(self.pick_dir)
        dl_layout.addWidget(self.download_dir)
        dl_layout.addWidget(pick_btn)
        self.content_layout.addWidget(dl_group)

        api_group = QGroupBox("API Keys (Optional)")
        api_form = QFormLayout()
        api_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.gel_user = QLineEdit(); self.gel_key = QLineEdit(); self.gel_key.setEchoMode(QLineEdit.Password)
        self.db_login = QLineEdit(); self.db_key = QLineEdit(); self.db_key.setEchoMode(QLineEdit.Password)
        self.r34_user = QLineEdit(); self.r34_key = QLineEdit(); self.r34_key.setEchoMode(QLineEdit.Password)
        api_form.addRow(_tr("Gelbooru User ID:"), self.gel_user)
        api_form.addRow(_tr("Gelbooru API Key:"), self.gel_key)
        api_form.addRow(_tr("Danbooru Login:"), self.db_login)
        api_form.addRow(_tr("Danbooru API Key:"), self.db_key)
        api_form.addRow(_tr("Rule34 User ID:"), self.r34_user)
        api_form.addRow(_tr("Rule34 API Key:"), self.r34_key)
        api_group.setLayout(api_form)
        self.content_layout.addWidget(api_group)

        button_box = QHBoxLayout()
        save_btn = QPushButton(qta.icon('fa5s.check'), _tr(" Get Started"))
        save_btn.clicked.connect(self.accept)
        button_box.addStretch()
        button_box.addWidget(save_btn)
        button_box.addStretch()
        self.content_layout.addLayout(button_box)

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, _tr("Choose download folder"), self.download_dir.text())
        if d:
            self.download_dir.setText(d)

    def values(self):
        return {
            "download_dir": self.download_dir.text().strip(),
            "gelbooru": {"user_id": self.gel_user.text().strip(), "api_key": self.gel_key.text().strip()},
            "danbooru": {"login": self.db_login.text().strip(), "api_key": self.db_key.text().strip()},
            "rule34": {"user_id": self.r34_user.text().strip(), "api_key": self.r34_key.text().strip()},
        }

class BulkDownloadDialog(BaseDialog):
    def __init__(self, worker, parent=None):
        super().__init__(_tr("Bulk Download"), parent)
        self.worker = worker
        self.setMinimumWidth(500)
        self.setWindowIcon(qta.icon('fa5s.cloud-download-alt'))

        self.progress_bar = QProgressBar(); self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        cancel_btn = QPushButton(_tr("Cancel"))
        self.content_layout.addWidget(QLabel(_tr("Downloading files..."))); self.content_layout.addWidget(self.progress_bar)
        self.content_layout.addWidget(self.log); self.content_layout.addWidget(cancel_btn)
        cancel_btn.clicked.connect(self.worker.cancel)
        self.worker.progress.connect(lambda cur, tot, msg: (self.progress_bar.setMaximum(tot), self.progress_bar.setValue(cur), self.log.appendPlainText(msg)))
        self.worker.finished.connect(lambda msg: (QMessageBox.information(self, _tr("Finished"), msg), self.accept()))
        self.worker.start()

    def closeEvent(self, event): self.worker.cancel(); super().closeEvent(event)

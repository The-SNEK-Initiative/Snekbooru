import os
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication

from snekbooru_linux.core.config import SETTINGS
from snekbooru_linux.core.downloader import download_media
from snekbooru_linux.ui.styling import (DARK_STYLESHEET, LIGHT_STYLESHEET,
                                  preprocess_stylesheet)


def launch_media_viewer_process(posts, current_index, favorites, settings, queue, custom_themes):
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("Snekbooru")
    QCoreApplication.setApplicationName("Snekbooru")

    single_post = settings.pop("single_post", None)

    global SETTINGS
    SETTINGS.update(settings)

    # We need to import MediaViewerDialog here, inside the function,
    # to avoid circular dependencies at the top level.
    from snekbooru_linux.ui.main_window import MediaViewerDialog

    # The MediaViewerDialog needs a mock parent to get the stylesheet and favorites.
    class MockParent:
        def __init__(self):
            self.favorites = favorites
            self.styleSheet = lambda: ""
            self.toggle_favorite = lambda post: queue.put(('favorited', post))
            self.download_post = lambda post: download_media(post)

    mock_parent = MockParent()

    w = MediaViewerDialog(posts, current_index, parent=mock_parent)

    theme_name = settings.get("active_theme", "Dark (Default)")
    if theme_name == "Dark (Default)": scss_string = DARK_STYLESHEET
    elif theme_name == "Light (Default)": scss_string = LIGHT_STYLESHEET
    elif theme_name in custom_themes: scss_string = custom_themes[theme_name]
    else: scss_string = DARK_STYLESHEET
    final_stylesheet = preprocess_stylesheet(scss_string)
    app.setStyleSheet(final_stylesheet)
    w.setStyleSheet(final_stylesheet) # Apply to dialog as well

    w.show()
    sys.exit(app.exec_())
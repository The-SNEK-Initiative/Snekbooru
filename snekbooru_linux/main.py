import os
import sys
import multiprocessing
from multiprocessing import freeze_support

from PyQt5.QtCore import QCoreApplication, qInstallMessageHandler
from PyQt5.QtWidgets import QApplication

from snekbooru_linux.common.helpers import get_resource_path
from snekbooru_linux.common.translations import load_translations
from snekbooru_linux.core.config import (load_custom_boorus, load_favorites,
                                   load_settings,
                                   save_settings, SETTINGS)
from snekbooru_linux.ui.dialogs import FirstRunDialog
from snekbooru_linux.ui.main_window import GelDanApp
from snekbooru_linux.ui.styling import load_custom_fonts


def qt_message_handler(mode, context, message):
    """
    Custom message handler to suppress specific, harmless Qt warnings.
    """
    if "OpenType support missing for" in message:
        return
    print(message, file=sys.stderr)


def main():
    """Main application entry point."""
    # For PyInstaller (Windows mostly, but harmless to check platform)
    if hasattr(sys, '_MEIPASS') and sys.platform == 'win32':
        os.environ['VLC_PLUGIN_PATH'] = os.path.join(sys._MEIPASS, 'vlc', 'plugins')

    freeze_support()
    qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("Snekbooru")
    QCoreApplication.setApplicationName("Snekbooru")

    SETTINGS.update(load_settings())
    load_translations()
    load_custom_fonts()

    if not SETTINGS.get("is_configured"):
        first_run = FirstRunDialog()
        if first_run.exec_():
            SETTINGS.update(first_run.values())
            SETTINGS["is_configured"] = True
            save_settings(SETTINGS)

    main_window = GelDanApp()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        pass
    main()
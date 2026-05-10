import os
import sys
from multiprocessing import freeze_support

from PyQt5.QtCore import QCoreApplication, qInstallMessageHandler
from PyQt5.QtWidgets import QApplication

from snekbooru.common.helpers import get_resource_path
from snekbooru.common.translations import load_translations
from snekbooru.core.config import (load_custom_boorus, load_favorites,
                                   load_settings,
                                   save_settings, SETTINGS)
from snekbooru.ui.dialogs import FirstRunDialog
from snekbooru.ui.main_window import GelDanApp
from snekbooru.ui.styling import load_custom_fonts


def qt_message_handler(mode, context, message):
    if "OpenType support missing for" in message:
        return
    print(message, file=sys.stderr)


def main():
    if hasattr(sys, '_MEIPASS'):
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
    
    exit_code = app.exec_()
    
    from snekbooru.core.temp_cache import purge_snekbooru_temp
    print("[main] Cleaning up temp directory...")
    purge_snekbooru_temp()
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
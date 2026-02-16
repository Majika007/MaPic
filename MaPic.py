#!/usr/bin/env python3
"""
Image Viewer + AI Metadata

Author: Majika77
Date: 2026-02-15
Description: A lightweight image viewer that displays AI generation metadata alongside images.
Developed with assistance from ChatGPT (OpenAI GPT-5 mini) & Claude (Anthropic) :)
"""
import sys
import os
import traceback
import requests
from packaging.version import Version

# Biztosítjuk hogy a script könyvtára benne van a Python path-ban
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from PyQt6.QtCore import QSettings, pyqtSignal, QThread, qInstallMessageHandler, QtMsgType
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

# ============ Config ============
APP_VERSION = "2.7"
GITHUB_REPO = "Majika007/MaPic"
DEBUG = False

# ============ Settings ============
settings = QSettings("Majika", "MaPic")

# Default settings értékek
def get_setting(key, default):
    """Beállítás lekérése default értékkel"""
    return settings.value(key, default, type=type(default))

def set_setting(key, value):
    """Beállítás mentése"""
    settings.setValue(key, value)

# ============ Debug funkciók ============

def dlog(*args):
    """Debug log fájlba írás"""
    try:
        with open("mapic_debug.log", "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except:
        pass

def debug_log(*args):
    """Console debug log"""
    if DEBUG:
        print("[DEBUG]", *args)

def global_exception_hook(exctype, value, tb):
    """Globális exception handler"""
    print("[UNCAUGHT EXCEPTION]")
    traceback.print_exception(exctype, value, tb)

sys.excepthook = global_exception_hook

def qt_message_handler(mode, context, message):
    """Qt üzenetek kezelése"""
    print(f"[Qt {mode.name}] {message}")

qInstallMessageHandler(qt_message_handler)

# ============ Update Checker ============

def get_latest_version():
    """GitHub API-tól lekéri a legújabb verziót"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    r = requests.get(url, timeout=5)
    data = r.json()
    return data["tag_name"].lstrip("v")

def is_newer(latest, current):
    """Verzió összehasonlítás"""
    return Version(latest) > Version(current)

class UpdateChecker(QThread):
    """Háttérben futó verzió ellenőrző thread"""
    update_found = pyqtSignal(str)  # ha új verzió van
    up_to_date = pyqtSignal()       # ha minden ok

    def __init__(self, manual=False, parent=None):
        super().__init__(parent)
        self.manual = manual

    def run(self):
        settings = QSettings("Majika", "MaPic")
        if not self.manual and settings.value("skip_update_warning", False, bool):
            return

        try:
            latest = get_latest_version()
            if is_newer(latest, APP_VERSION):
                self.update_found.emit(latest)
            else:
                self.up_to_date.emit()
        except Exception as e:
            print("Update check failed:", e)

# ============ Main Application ============

# Import UI modul (a __main__ blokk előtt, hogy biztosan betöltődjön)
try:
    from ui import ImageViewer
except ImportError as e:
    print(f"ERROR: Cannot import ui module: {e}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"sys.path: {sys.path[:3]}...")
    sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Ablak létrehozása
    w = ImageViewer()
    app.setWindowIcon(QIcon("MaPic.ico"))
    w.setWindowIcon(QIcon("MaPic.ico"))
    w.resize(1000, 850)
    
    # Parancssor argumentum kezelése (kép megnyitása)
    if len(sys.argv) > 1:
        fname = os.path.abspath(sys.argv[1])
        w.open_folder_and_select(fname)
    
    w.show()
    sys.exit(app.exec())

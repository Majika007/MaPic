"""
Styles and settings module
"""
from PyQt6.QtCore import QSettings

# ============ Settings kezelés ============
settings = QSettings("Majika", "MaPic")

def get_setting(key, default):
    """Beállítás lekérése default értékkel"""
    if default is None:
        # Ha nincs default, akkor csak visszaadjuk az értéket (None ha nem létezik)
        return settings.value(key, default)
    else:
        # Ha van default, akkor típus szerint konvertáljuk
        
        # Bool típus speciális kezelése - explicit bool típust kérünk
        if isinstance(default, bool):
            value = settings.value(key, default, type=bool)
            return value
        
        # Int típus kezelése
        if isinstance(default, int):
            value = settings.value(key, default)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return default
            return int(value) if value is not None else default
        
        # Egyéb típusok
        return settings.value(key, default)

def set_setting(key, value):
    """Beállítás mentése"""
    settings.setValue(key, value)

# ============ HTML/CSS Stílusok ============

STYLE_LIGHT = """
<style>
.key1 { font-weight: bold; color: green;}
.key2 { font-weight: bold; color: red;}
.key3 { font-weight: bold; color: navy;}
.key4 { font-weight: bold; color: blue;}
.key5 { font-weight: bold; color: black;}
.center { text-align: center; display: block; font-weight: bold; color: navy;}
body { background-color: white; color: black; }
a { text-decoration: none; font-size:16px;}
</style>
"""

STYLE_DARK = """
<style>
.key1 { font-weight: bold; color: lightgreen;}
.key2 { font-weight: bold; color: salmon;}
.key3 { font-weight: bold; color: lightskyblue;}
.key4 { font-weight: bold; color: deepskyblue;}
.key5 { font-weight: bold; color: white;}
.center { text-align: center; display: block; font-weight: bold; color: lightblue;}
body { background-color: #121212; color: white; }
a { text-decoration: none; font-size:16px;}
</style>
"""

def is_system_dark():
    """Rendszer téma detektálása"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPalette
    
    palette = QApplication.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    text_color = palette.color(QPalette.ColorRole.WindowText)
    # ha a háttér sötétebb mint a szöveg → dark mode
    return bg_color.lightness() < text_color.lightness()

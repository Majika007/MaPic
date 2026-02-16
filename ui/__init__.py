"""
UI module for MaPic Image Viewer
"""
from .viewer import ImageViewer
from .widgets import ClickableLabel, ToastMessage
from .dialogs import SettingsDialog
from .styles import STYLE_DARK, STYLE_LIGHT, get_setting, set_setting, is_system_dark

__all__ = [
    'ImageViewer',
    'ClickableLabel', 
    'ToastMessage',
    'SettingsDialog',
    'STYLE_DARK',
    'STYLE_LIGHT',
    'get_setting',
    'set_setting',
    'is_system_dark'
]

"""
Dialog windows module
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton
)
from .styles import get_setting

# ============ Settings Dialog ============

class SettingsDialog(QDialog):
    """Beállítások ablak"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        
        # Layout
        layout = QVBoxLayout(self)
        
        # Cím
        title = QLabel("Application Settings")
        title.setStyleSheet("font-weight: bold; font-size: 14pt; padding: 10px;")
        layout.addWidget(title)
        
        # Checkbox-ok
        self.wheel_scroll_cb = QCheckBox("Enable mouse wheel scroll")
        self.wheel_scroll_cb.setChecked(get_setting("wheel_scroll_enabled", True))
        layout.addWidget(self.wheel_scroll_cb)
        
        # Spacer
        layout.addStretch()
        
        # Gombok alul
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_ok)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        self.setMinimumWidth(350)
        self.setMinimumHeight(150)
    
    def get_values(self):
        """Beállítások lekérése"""
        return {
            "wheel_scroll_enabled": self.wheel_scroll_cb.isChecked()
        }

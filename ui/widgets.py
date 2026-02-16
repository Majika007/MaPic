"""
Custom widgets module
"""
from PyQt6.QtWidgets import QLabel, QToolTip, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QCursor

# ============ Custom Widgets ============

class ZoomScrollArea(QScrollArea):
    """ScrollArea ami nem reagál CTRL+wheel-re (azt a parent kapja)"""
    
    def wheelEvent(self, event):
        # Ha CTRL van lenyomva, ne csináljunk semmit - hagyjuk a parent-nek
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event.ignore()
            return
        # Különben normál scroll
        super().wheelEvent(event)

class ClickableLabel(QLabel):
    """Kattintható label a thumbnail grid megnyitásához, panning középső gombbal"""
    clicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_panning = False
        self.last_global_pos = None
        self.parent_viewer = None
    
    def mousePressEvent(self, event):
        # Bal gomb = thumbnail view (mindig)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        
        # Középső gomb = panning (ha van mit mozgatni, azaz a kép nagyobb mint a viewport)
        if event.button() == Qt.MouseButton.MiddleButton:
            if self.parent_viewer:
                # Ellenőrizzük hogy van-e scrollbar (van-e mit mozgatni)
                h_scroll = self.parent_viewer.image_scroll.horizontalScrollBar()
                v_scroll = self.parent_viewer.image_scroll.verticalScrollBar()
                
                has_scrollbar = (h_scroll.maximum() > 0) or (v_scroll.maximum() > 0)
                
                if has_scrollbar:
                    self.is_panning = True
                    self.last_global_pos = event.globalPosition().toPoint()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        if self.is_panning and self.last_global_pos and self.parent_viewer:
            # GlobalPos használata a pontosabb követéshez
            current_global = event.globalPosition().toPoint()
            delta = current_global - self.last_global_pos
            
            h_scroll = self.parent_viewer.image_scroll.horizontalScrollBar()
            v_scroll = self.parent_viewer.image_scroll.verticalScrollBar()
            
            # Simább mozgás: közvetlenül a delta-t használjuk
            h_scroll.setValue(h_scroll.value() - delta.x())
            v_scroll.setValue(v_scroll.value() - delta.y())
            
            self.last_global_pos = current_global
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if self.is_panning:
                self.is_panning = False
                self.last_global_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)

class ToastMessage:
    """Toast notification widget"""
    @staticmethod
    def display(parent, message, duration=1000):
        """Egyszerű toast üzenet megjelenítése"""
        QToolTip.showText(QCursor.pos(), message, parent, QRect(), duration)

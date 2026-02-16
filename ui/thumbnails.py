"""
Thumbnail management module
"""
from PyQt6.QtWidgets import QLabel, QApplication
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
import os
from threading import Thread

class ThumbnailManager:
    """Thumbnail cache és grid kezelő"""
    
    def __init__(self, viewer):
        self.viewer = viewer
    
    def start_thumbnail_cache(self):
        """Thumbnail cache indítása háttérben"""
        if hasattr(self.viewer, "_cache_thread_started") and self.viewer._cache_thread_started:
            return
        self.viewer._cache_thread_started = True
        thread = Thread(target=self.preload_thumbnails, daemon=True)
        thread.start()
    
    def preload_thumbnails(self):
        """Thumbnail-ek előtöltése"""
        w, h = 160, 120
        for i, path in enumerate(self.viewer.image_files, start=1):
            pix = QPixmap(path)
            if pix.isNull():
                thumb = QPixmap(w, h)
                thumb.fill(Qt.GlobalColor.transparent)
            else:
                thumb = pix.scaled(w, h, self.viewer.aspect_ratio, self.viewer.smooth)
                self.viewer.thumb_cache[path] = thumb
                self.viewer.cache_progress.emit(i, len(self.viewer.image_files))
    
    def show_thumbnails(self, event=None):
        """Thumbnail grid megjelenítése"""
        if not self.viewer.image_files:
            return
        
        thumb_w, thumb_h = 160, 120
        spacing = self.viewer.thumb_grid.horizontalSpacing() or 12
        container_width = self.viewer.first_width
        cols = max(1, container_width // (thumb_w + spacing))
        
        # Grid tartalmának törlése
        for i in reversed(range(self.viewer.thumb_grid.count())):
            widget_item = self.viewer.thumb_grid.itemAt(i)
            if widget_item:
                w = widget_item.widget()
                if w:
                    w.setParent(None)
        
        # Margók számítása (középre igazítás)
        used_cols = min(cols, len(self.viewer.image_files))
        total_thumb_width = used_cols * thumb_w + (used_cols - 1) * spacing
        side_margin = max((container_width - total_thumb_width) // 2, 0)
        
        self.viewer.thumb_grid.setContentsMargins(side_margin, 12, side_margin, 12)
        self.viewer.thumb_grid.setHorizontalSpacing(spacing)
        self.viewer.thumb_grid.setVerticalSpacing(spacing)
        
        # Thumbnail-ek hozzáadása
        for i, path in enumerate(self.viewer.image_files):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = self.viewer.thumb_cache.get(path, QPixmap(thumb_w, thumb_h))
            lbl.setPixmap(pixmap)
            lbl.setToolTip(os.path.basename(path))
            lbl.mousePressEvent = lambda e, idx=i: self.open_image_from_thumb(idx)
            row, col = divmod(i, cols)
            self.viewer.thumb_grid.addWidget(lbl, row, col)
        
        self.viewer.stack.setCurrentWidget(self.viewer.thumb_scroll)
        self.viewer.first_width = self.viewer.thumb_scroll.viewport().width()
        self.viewer.thumb_grid.update()
        self.viewer.thumb_scroll.viewport().update()
        QApplication.processEvents()
    
    def open_image_from_thumb(self, index):
        """Kép megnyitása thumbnail kattintásra"""
        if not (0 <= index < len(self.viewer.image_files)):
            return
        self.viewer.current_index = index
        self.viewer.show_image(self.viewer.image_files[self.viewer.current_index])
        self.viewer.stack.setCurrentWidget(self.viewer.image_view_widget)

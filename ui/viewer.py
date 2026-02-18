"""
Main ImageViewer class
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QMessageBox, QFileDialog, 
    QPushButton, QHBoxLayout, QSplitter, QMainWindow, QSizePolicy, 
    QScrollArea, QGridLayout, QStackedWidget, QTextBrowser, QApplication, QDialog
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence, QIcon, QWheelEvent, QAction, QDesktopServices
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl

from metadata import extract_prompts, ImageMeta, empty_meta
from .styles import STYLE_DARK, STYLE_LIGHT, is_system_dark, get_setting, set_setting
from .widgets import ClickableLabel, ToastMessage, ZoomScrollArea
from .dialogs import SettingsDialog
from .thumbnails import ThumbnailManager

class ImageViewer(QMainWindow):
    cache_progress = pyqtSignal(int, int)  # (current, total) thumbnail cache progress

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MaPic - Majika Picture Viewer")
        
        # Verzió tárolása osztály változóként (exe kompatibilitás)
        try:
            from MaPic import APP_VERSION
            self.app_version = APP_VERSION
        except ImportError:
            self.app_version = "2.7"
        
        # Állapot változók
        self.image_files = []
        self.current_index = -1
        self.current_pixmap = None
        self.current_meta = empty_meta()
        
        # Rendszer téma detektálása
        try:
            self.dark_mode = is_system_dark()
        except Exception:
            self.dark_mode = False
        
        self.thumb_cache = {}
        self._cache_thread_started = False
        self.cache_total = 0
        self.cache_current = 0
        
        # Qt beállítások
        self.aspect_ratio = Qt.AspectRatioMode.KeepAspectRatio
        self.smooth = Qt.TransformationMode.SmoothTransformation
        
        # Zoom beállítások
        self.zoom_level = 1.0  # 1.0 = 100%
        self.zoom_min = 0.1    # 10%
        self.zoom_max = 5.0    # 500%
        
        # Pan beállítások (mozgatás)
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.is_panning = False
        self.last_mouse_pos = None
        
        # Thumbnail manager
        self.thumb_manager = ThumbnailManager(self)
        
        # ============ UI építése ============
        self._build_ui()
        self._setup_menu()
        self._setup_shortcuts()
        
        # Kezdeti betöltés
        try:
            self.load_current_folder()
        except Exception:
            pass
        
        # Ablak beállítások visszaállítása (késleltetett hogy a UI teljesen felépüljön)
        QTimer.singleShot(10, self.restore_window_settings)
        
        QTimer.singleShot(50, self._update_image_label)
        QTimer.singleShot(0, lambda: self.start_update_check(manual=False))
    
    def _build_ui(self):
        """UI felépítése"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Cache progress label
        self.cache_label = QLabel("Thumbnail cache: 0 / 0")
        self.cache_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.cache_label)
        self.cache_progress.connect(self.update_cache_label)
        
        # Stack widget
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # Image view
        self._build_image_view()
        
        # Thumbnail view
        self._build_thumbnail_view()
        
        # Gombok
        self._build_buttons(main_layout)
    
    def _build_image_view(self):
        """Image view felépítése"""
        self.image_view_widget = QWidget()
        image_view_layout = QVBoxLayout(self.image_view_widget)
        image_view_layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        image_view_layout.addWidget(self.splitter)
        
        # Image scroll area (zoom/pan támogatáshoz)
        self.image_scroll = ZoomScrollArea()
        self.image_scroll.setWidgetResizable(False)  # FONTOS: False kell a zoom-hoz
        self.image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.image_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Image label
        self.image_label = ClickableLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(200, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.clicked.connect(self.show_thumbnails)
        self.image_label.parent_viewer = self  # Panning támogatáshoz
        
        # Mouse tracking panning-hez
        self.image_label.setMouseTracking(True)
        
        self.image_scroll.setWidget(self.image_label)
        self.splitter.addWidget(self.image_scroll)
        
        # Metadata panel
        self.meta_text = QTextBrowser()
        self.meta_text.setOpenLinks(False)
        self.meta_text.anchorClicked.connect(self.copy_link)
        self.meta_text.setMinimumSize(120, 120)
        self.splitter.addWidget(self.meta_text)
        
        # Splitter beállítások
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([700, 150])
        
        self.stack.addWidget(self.image_view_widget)
    
    def _build_thumbnail_view(self):
        """Thumbnail view felépítése"""
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        thumb_container = QWidget()
        self.thumb_grid = QGridLayout(thumb_container)
        self.thumb_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.thumb_scroll.setWidget(thumb_container)
        self.stack.addWidget(self.thumb_scroll)
        self.first_width = 800
    
    def _build_buttons(self, main_layout):
        """Gombok felépítése"""
        btn_layout = QHBoxLayout()
        
        self.btn_open = QPushButton("Open Folder")
        self.btn_open.clicked.connect(self.open_folder)
        btn_layout.addWidget(self.btn_open)
        
        self.btn_theme = QPushButton("Toggle Theme")
        self.btn_theme.clicked.connect(self.toggle_theme)
        btn_layout.addWidget(self.btn_theme)
        
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.show_prev)
        btn_layout.addWidget(self.btn_prev)
        
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.show_next)
        btn_layout.addWidget(self.btn_next)
        
        self.btn_toggle = QPushButton("↔ / ↕")
        self.btn_toggle.clicked.connect(self.toggle_orientation)
        btn_layout.addWidget(self.btn_toggle)
        
        self.btn_save = QPushButton("Save .txt")
        self.btn_save.clicked.connect(self.save_meta)
        btn_layout.addWidget(self.btn_save)
        
        main_layout.addLayout(btn_layout)
    
    def _setup_menu(self):
        """Menu bar felépítése"""
        menubar = self.menuBar()
        
        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        act_settings = QAction("Preferences...", self)
        act_settings.triggered.connect(self.show_settings)
        settings_menu.addAction(act_settings)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        act_about = QAction("About", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)
        
        act_update = QAction("Check for updates", self)
        act_update.triggered.connect(lambda: self.start_update_check(manual=True))
        help_menu.addAction(act_update)
    
    def _setup_shortcuts(self):
        """Billentyű shortcut-ok felépítése"""
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(self.show_next)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(self.show_prev)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self).activated.connect(self.show_next)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self).activated.connect(self.show_prev)
        
        # Zoom shortcuts
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.zoom_in)  # alternatív
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.reset_zoom)
        
        # Refresh shortcut
        QShortcut(QKeySequence(Qt.Key.Key_F5), self).activated.connect(self.refresh_folder)
    
    # ============ Update kezelés ============
    
    def start_update_check(self, manual=False):
        """Frissítés ellenőrzése háttérben"""
        try:
            from MaPic import UpdateChecker
            self.update_thread = UpdateChecker(manual=manual)
            self.update_thread.update_found.connect(lambda v: self.show_update_popup(v, manual))
            self.update_thread.up_to_date.connect(lambda: self.show_up_to_date(manual))
            self.update_thread.start()
        except Exception as e:
            if manual:
                QMessageBox.warning(self, "Update Check Failed", f"Could not check for updates: {e}")
    
    def show_update_popup(self, latest_version, manual):
        """Frissítési popup ablak"""
        try:
            from MaPic import GITHUB_REPO
            github_repo = GITHUB_REPO
        except ImportError:
            github_repo = "Majika007/MaPic"
        
        from PyQt6.QtWidgets import QCheckBox
        from PyQt6.QtCore import QSettings
        
        settings = QSettings("Majika", "MaPic")
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Update available")
        msg.setText(f"New version available: {latest_version}\nCurrent: {self.app_version}")
        
        btn_download = msg.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        btn_close = msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        
        # Checkbox létrehozása és jelenlegi érték beolvasása
        checkbox = QCheckBox("Don't notify me again")
        current_setting = settings.value("skip_update_warning", False, bool)
        checkbox.setChecked(current_setting)
        msg.setCheckBox(checkbox)
        
        msg.exec()
        
        # Beállítás mentése (akár be van pipálva, akár ki van véve a pipa)
        settings.setValue("skip_update_warning", checkbox.isChecked())
        
        if msg.clickedButton() == btn_download:
            QDesktopServices.openUrl(QUrl(f"https://github.com/{github_repo}/releases/latest"))
    
    def show_up_to_date(self, manual):
        """Naprakész verzió üzenet"""
        if manual:
            QMessageBox.information(self, "Up to date", "You are using the latest version.")
    
    def show_about(self):
        """About dialog"""
        QMessageBox.information(
            self,
            "About MaPic",
            f"MaPic – Majika Picture Viewer\n"
            f"Version: {self.app_version}\n\n"
            "AI image metadata viewer\n"
            "GitHub: github.com/Majika007/MaPic"
        )
    
    def show_settings(self):
        """Settings dialog megjelenítése"""
        dialog = SettingsDialog(self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            values = dialog.get_values()
            for key, value in values.items():
                set_setting(key, value)
    
    # ============ Kép megjelenítés ============
    
    def show_image(self, fname):
        """Kép betöltése és metadata megjelenítése"""
        pix = QPixmap(fname)
        if pix.isNull():
            self.image_label.setText("Failed to load image")
            self.meta_text.setPlainText(f"Failed to load: {fname}")
            self.current_pixmap = None
            return
        
        self.current_pixmap = pix
        
        # Zoom reset új képnél
        self.zoom_level = 1.0
        
        # Label méret visszaállítása (ne maradjon fix méret az előző képről)
        self.image_label.setMinimumSize(200, 200)
        self.image_label.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
        
        if fname in self.image_files:
            self.current_index = self.image_files.index(fname)
        
        # Metadata kinyerése
        try:
            result = extract_prompts(fname)
        except Exception as e:
            print(f"[ERROR] extract_prompts({fname}): {e}")
            result = ImageMeta("Error: {e}", *["N/A"]*10)
        
        self.current_meta = result
        pos = " ".join(result.prompt.split())
        neg = " ".join(result.neg_prompt.split())
        img_width = pix.width()
        img_height = pix.height()
        
        # HTML formázás
        style_block = STYLE_DARK if self.dark_mode else STYLE_LIGHT
        
        meta_html = f"""
        {style_block}
        <div class="center">{os.path.basename(fname)} </div>&nbsp;&nbsp;({img_width} x {img_height} px)<br>
        <span class="key1">✅ Prompt:<a href='pos_prompt' title="Copy to clipboard"> 📋 </a></span> {pos}<br>
        <span class="key2">🚫 Negative Prompt:<a href='neg_prompt' title="Copy to clipboard"> 📋 </a></span> {neg}<br>
        <span class="key1">📦 Checkpoint: </span><span class="key5">{result.model}</span><br>
        <span class="key3">🔁 Sampler:</span> {result.sampler} &nbsp;&nbsp;&nbsp;&nbsp;
        <span class="key3">📈 Scheduler:</span> {result.scheduler} &nbsp;&nbsp;&nbsp;&nbsp;
        <span class="key3">📏 Steps:</span> {result.steps}<br>
        <span class="key3">🎯 CFG scale:</span> {result.cfg_scale} &nbsp;&nbsp;&nbsp;&nbsp;
        <span class="key3">🎲 Seed:<a href='seed_nr' title="Copy to clipboard"> 📋 </a></span> {result.seed} &nbsp;&nbsp;&nbsp;&nbsp;<br>
        <span class="key3">✨ LoRA:</span> {result.loras}
        """
        
        self.meta_text.setHtml(meta_html)
        self.stack.setCurrentWidget(self.image_view_widget)
        
        QTimer.singleShot(50, self._update_image_label)
    
    def _update_image_label(self):
        """Kép átméretezése a label-hez"""
        if not self.current_pixmap or self.current_pixmap.isNull():
            self.image_label.setText("No image loaded")
            return
        
        # Eredeti kép mérete
        orig_w = self.current_pixmap.width()
        orig_h = self.current_pixmap.height()
        
        # Ha nincs zoom (1.0), akkor fit-to-window
        if abs(self.zoom_level - 1.0) < 0.01:
            QApplication.processEvents()
            
            w = self.image_scroll.viewport().width()
            h = self.image_scroll.viewport().height()
            
            if w <= 1 or h <= 1:
                w, h = 800, 600
            
            scaled = self.current_pixmap.scaled(w, h, self.aspect_ratio, self.smooth)
            self.image_label.setPixmap(scaled)
            self.image_label.adjustSize()
            
            # FONTOS: frissítjük a zoom_level-t a tényleges méret alapján
            actual_w = scaled.width()
            actual_h = scaled.height()
            # Használjuk a kisebb arány-t (hogy biztosan beleférjen)
            actual_zoom = min(actual_w / orig_w, actual_h / orig_h)
            self.zoom_level = actual_zoom
        else:
            # Zoom esetén: fix méret a zoom level alapján
            zoom_w = int(orig_w * self.zoom_level)
            zoom_h = int(orig_h * self.zoom_level)
            
            scaled = self.current_pixmap.scaled(zoom_w, zoom_h, self.aspect_ratio, self.smooth)
            self.image_label.setPixmap(scaled)
            self.image_label.setFixedSize(scaled.size())
    
    def resizeEvent(self, event):
        """Ablak átméretezésekor frissíti a képet"""
        super().resizeEvent(event)
        QTimer.singleShot(10, self._update_image_label)
    
    # ============ Navigáció ============
    
    def show_next(self):
        """Következő kép"""
        if self.image_files and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.show_image(self.image_files[self.current_index])
    
    def show_prev(self):
        """Előző kép"""
        if self.image_files and self.current_index > 0:
            self.current_index -= 1
            self.show_image(self.image_files[self.current_index])
    
    def wheelEvent(self, event: QWheelEvent):
        """Egérgörgő kezelése"""
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        
        # CTRL+wheel = zoom (kurzor pozícióra)
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Kurzor pozíció a VIEWPORT-hoz képest (nem az image_label-hez!)
            cursor_pos = self.image_scroll.viewport().mapFromGlobal(event.globalPosition().toPoint())
            
            # Finomabb zoom: ~15% per scroll
            zoom_factor = 1.15
            if delta > 0:
                self.zoom_at_cursor(zoom_factor, cursor_pos)
            elif delta < 0:
                self.zoom_at_cursor(1.0 / zoom_factor, cursor_pos)
            event.accept()
            return
        
        # Sima wheel = navigáció (ha be van kapcsolva)
        if not get_setting("wheel_scroll_enabled", True):
            event.ignore()
            return
        
        if delta > 0:
            self.show_prev()
        elif delta < 0:
            self.show_next()
        event.accept()
    
    def keyPressEvent(self, event):
        """Billentyűzet kezelése"""
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.show_next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.show_prev()
        else:
            super().keyPressEvent(event)
    
    # ============ Zoom funkciók ============
    
    def zoom_in(self):
        """Zoom in (nagyítás) - középre"""
        self.zoom_level = min(self.zoom_level * 1.1, self.zoom_max)
        self._update_image_label()
    
    def zoom_out(self):
        """Zoom out (kicsinyítés) - középre"""
        self.zoom_level = max(self.zoom_level / 1.1, self.zoom_min)
        self._update_image_label()
    
    def zoom_at_cursor(self, factor, cursor_pos):
        """Zoom a kurzor pozícióra"""
        if not self.current_pixmap or self.current_pixmap.isNull():
            return
        
        old_zoom = self.zoom_level
        self.zoom_level = max(self.zoom_min, min(self.zoom_level * factor, self.zoom_max))
        
        # Ha elérte a limitet, ne csináljon semmit
        if abs(old_zoom - self.zoom_level) < 0.001:
            return
        
        # ScrollArea scroll pozíciók
        h_scroll = self.image_scroll.horizontalScrollBar()
        v_scroll = self.image_scroll.verticalScrollBar()
        
        # Régi pozíciók mentése
        old_h_scroll = h_scroll.value()
        old_v_scroll = v_scroll.value()
        
        # Kurzor relatív pozíciója a viewport-ban
        cursor_in_viewport_x = cursor_pos.x()
        cursor_in_viewport_y = cursor_pos.y()
        
        # Abszolút pozíció a teljes képen (a jelenlegi zoom szerint)
        point_on_image_x = old_h_scroll + cursor_in_viewport_x
        point_on_image_y = old_v_scroll + cursor_in_viewport_y
        
        # Kép frissítése
        self._update_image_label()
        
        # Zoom arány
        zoom_ratio = self.zoom_level / old_zoom
        
        # Új pozíció a képen (skálázva)
        new_point_x = point_on_image_x * zoom_ratio
        new_point_y = point_on_image_y * zoom_ratio
        
        # Új scroll értékek
        new_h_scroll = new_point_x - cursor_in_viewport_x
        new_v_scroll = new_point_y - cursor_in_viewport_y
        
        h_scroll.setValue(int(new_h_scroll))
        v_scroll.setValue(int(new_v_scroll))
    
    def reset_zoom(self):
        """Zoom visszaállítása 100%-ra"""
        self.zoom_level = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        
        # Label méret visszaállítása
        self.image_label.setMinimumSize(200, 200)
        self.image_label.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
        
        self._update_image_label()
        
        # Scroll reset
        self.image_scroll.horizontalScrollBar().setValue(0)
        self.image_scroll.verticalScrollBar().setValue(0)
    
    # ============ Mappa kezelés ============
    
    def open_folder(self):
        """Mappa megnyitása"""
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if not folder:
            return
        exts = (".png", ".jpg", ".jpeg", ".webp")
        self.image_files = sorted([
            os.path.join(folder, f) 
            for f in os.listdir(folder) 
            if f.lower().endswith(exts)
        ])
        self.current_index = 0 if self.image_files else -1
        self._cache_thread_started = False
        self.thumb_cache.clear()
        self.cache_total = 0
        self.cache_current = 0
        if self.image_files:
            self.show_image(self.image_files[self.current_index])
        QTimer.singleShot(100, self.start_thumbnail_cache)
    
    def load_current_folder(self):
        """Jelenlegi mappa betöltése induláskor"""
        folder = os.getcwd()
        exts = (".png", ".jpg", ".jpeg", ".webp")
        self.image_files = sorted([
            os.path.join(folder, f) 
            for f in os.listdir(folder) 
            if f.lower().endswith(exts)
        ])
        self.current_index = 0 if self.image_files else -1
        self.thumb_cache.clear()
        if self.image_files:
            self.show_image(self.image_files[self.current_index])
        QTimer.singleShot(100, self.start_thumbnail_cache)
    
    def open_folder_and_select(self, fname):
        """Mappa megnyitása és kép kiválasztása"""
        folder = os.path.dirname(fname)
        exts = (".png", ".jpg", ".jpeg", ".webp")
        self.image_files = sorted([
            os.path.join(folder, f) 
            for f in os.listdir(folder) 
            if f.lower().endswith(exts)
        ])
        self.current_index = self.image_files.index(fname)
        self.show_image(self.image_files[self.current_index])
    
    def refresh_folder(self):
        """Aktuális mappa újratöltése (F5)"""
        if not self.image_files:
            # Ha nincs betöltve mappa, próbáljuk az aktuális mappát
            self.load_current_folder()
            return
        
        # Aktuális kép neve (ha van)
        current_file = self.image_files[self.current_index] if 0 <= self.current_index < len(self.image_files) else None
        current_folder = os.path.dirname(current_file) if current_file else os.getcwd()
        
        # Fájlok újratöltése
        exts = (".png", ".jpg", ".jpeg", ".webp")
        old_count = len(self.image_files)
        self.image_files = sorted([
            os.path.join(current_folder, f) 
            for f in os.listdir(current_folder) 
            if f.lower().endswith(exts)
        ])
        new_count = len(self.image_files)
        
        # Thumbnail cache frissítése
        self._cache_thread_started = False
        self.thumb_cache.clear()
        
        # Megpróbáljuk megtartani a jelenlegi képet
        if current_file and current_file in self.image_files:
            self.current_index = self.image_files.index(current_file)
        elif self.image_files:
            # Ha a jelenlegi kép törlődött, válasszuk a legközelebbit
            self.current_index = min(self.current_index, len(self.image_files) - 1)
        else:
            self.current_index = -1
        
        # Kép megjelenítése
        if self.image_files and self.current_index >= 0:
            self.show_image(self.image_files[self.current_index])
        
        # Toast notification
        if new_count != old_count:
            diff = new_count - old_count
            if diff > 0:
                ToastMessage.display(self, f"✔ Refreshed: +{diff} images ({new_count} total)")
            else:
                ToastMessage.display(self, f"✔ Refreshed: {abs(diff)} images removed ({new_count} total)")
        else:
            ToastMessage.display(self, f"✔ Refreshed: {new_count} images")
        
        # Thumbnail cache újraindítása
        QTimer.singleShot(100, self.start_thumbnail_cache)
    
    # ============ Thumbnail kezelés ============
    
    def start_thumbnail_cache(self):
        """Thumbnail cache indítása"""
        self.thumb_manager.start_thumbnail_cache()
    
    def show_thumbnails(self, event=None):
        """Thumbnail grid megjelenítése"""
        self.thumb_manager.show_thumbnails(event)
    
    def update_cache_label(self, current, total):
        """Cache progress frissítése"""
        self.cache_label.setText(f"Thumbnail cache: {current} / {total}")
    
    # ============ További funkciók ============
    
    def toggle_theme(self):
        """Téma váltása"""
        self.dark_mode = not self.dark_mode
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            self.show_image(self.image_files[self.current_index])
        else:
            style_block = STYLE_DARK if self.dark_mode else STYLE_LIGHT
            self.meta_text.setHtml(style_block)
    
    def toggle_orientation(self):
        """Splitter tájolás váltása"""
        s = self.splitter
        old_sizes = s.sizes()
        total_old = sum(old_sizes) if sum(old_sizes) > 0 else 1
        ratios = [float(x) / total_old for x in old_sizes]
        
        for i in range(s.count()):
            w = s.widget(i)
            if w:
                w.setMinimumSize(50, 50)
        
        if s.orientation() == Qt.Orientation.Vertical:
            s.setOrientation(Qt.Orientation.Horizontal)
        else:
            s.setOrientation(Qt.Orientation.Vertical)
        
        s.setSizes([max(50, int(r * (s.width() if s.orientation()==Qt.Orientation.Horizontal else s.height()))) for r in ratios])
        self._update_image_label()
    
    def save_meta(self):
        """Metadata mentése txt fájlba"""
        if not (self.image_files and 0 <= self.current_index < len(self.image_files)):
            return
        fname = self.image_files[self.current_index]
        try:
            result = extract_prompts(fname)
        except Exception as e:
            result = ImageMeta("Error: {e}", *["N/A"]*10)
        
        pos = " ".join(result.prompt.split())
        neg = " ".join(result.neg_prompt.split())
        img_width = self.current_pixmap.width() if self.current_pixmap else 0
        img_height = self.current_pixmap.height() if self.current_pixmap else 0
        
        text_content = (
            f"📐 Size: {img_width} x {img_height}\n"
            f"✅ Prompt: {pos}\n"
            f"🚫 Negative Prompt: {neg}\n"
            f"📦 Checkpoint: {result.model}\n"
            f"🔁 Sampler: {result.sampler}\n"
            f"📈 Scheduler: {result.scheduler}\n"
            f"📏 Steps: {result.steps}\n"
            f"🎯 CFG scale: {result.cfg_scale}\n"
            f"🎲 Seed: {result.seed}\n"
            f"🧠 VAE: {result.vae}\n"
            f"✨ LoRA: {result.loras}\n"
        )
        txt_file = os.path.splitext(fname)[0] + ".txt"
        try:
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(text_content)
            ToastMessage.display(self, "✔ Metadata saved")
        except Exception as e:
            print("Save error:", e)
    
    def copy_link(self, url):
        """Vágólapra másolás kattintott linkből"""
        pos = " ".join(self.current_meta.prompt.split())
        neg = " ".join(self.current_meta.neg_prompt.split())
        
        clipboard = QApplication.clipboard()
        if url.toString() == "pos_prompt":
            clipboard.setText(pos)
        elif url.toString() == "neg_prompt":
            clipboard.setText(neg)
        elif url.toString() == "seed_nr":
            clipboard.setText(str(self.current_meta.seed))
        
        ToastMessage.display(self, "✔ Text copied")
    
    # ============ Ablak beállítások mentése/betöltése ============
    
    def closeEvent(self, event):
        """Ablak bezárásakor menti a beállításokat"""
        from .styles import set_setting
        
        # Ablak mérete
        set_setting("window_width", self.width())
        set_setting("window_height", self.height())
        
        # Ablak pozíciója
        set_setting("window_x", self.x())
        set_setting("window_y", self.y())
        
        # Splitter arányok (lista)
        sizes = self.splitter.sizes()
        if len(sizes) == 2:
            set_setting("splitter_top", sizes[0])
            set_setting("splitter_bottom", sizes[1])
        
        # Splitter orientáció (0=Horizontal, 1=Vertical)
        orientation = 0 if self.splitter.orientation() == Qt.Orientation.Horizontal else 1
        set_setting("splitter_orientation", orientation)
        
        event.accept()
    
    def restore_window_settings(self):
        """Ablak beállítások visszaállítása"""
        from .styles import get_setting
        
        # Splitter orientáció visszaállítása ELŐSZÖR (mielőtt a méreteket állítanánk)
        orientation = get_setting("splitter_orientation", 1)  # default: Vertical (1)
        if orientation == 0:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
        else:
            self.splitter.setOrientation(Qt.Orientation.Vertical)
        
        # Splitter arányok (default 700, 150)
        top = get_setting("splitter_top", 700)
        bottom = get_setting("splitter_bottom", 150)
        self.splitter.setSizes([top, bottom])
        
        # Ablak mérete (default 1000x850) - UTOLJÁRA, hogy a splitter már kész legyen
        width = get_setting("window_width", 1000)
        height = get_setting("window_height", 850)
        self.resize(width, height)
        
        # Ablak pozíciója (None = nincs mentve)
        x = get_setting("window_x", None)
        y = get_setting("window_y", None)
        if x is not None and y is not None:
            # QSettings string-ként mentheti, konvertáljuk int-re
            try:
                x = int(x)
                y = int(y)
                self.move(x, y)
            except (ValueError, TypeError):
                pass  # Ha nem sikerül, hagyjuk az alapértelmezett pozíciót

"""
Image Viewer + AI Metadata

Author: Majika77
Date: 2026-01-06
Description: A lightweight image viewer that displays AI generation metadata alongside images.
Developed with assistance from ChatGPT (OpenAI GPT-5 mini) :)
"""
APP_VERSION = "2.45"
GITHUB_REPO = "Majika007/mapic"
#!/usr/bin/env python3
import sys
import os
import subprocess, json
import exifread, re
import html
import unicodedata
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QToolTip, QMessageBox, QCheckBox, QMenuBar, 
    QTextEdit, QFileDialog, QPushButton, QHBoxLayout, QSplitter, QMainWindow,
    QSizePolicy, QScrollArea, QGridLayout, QStackedWidget, QTextBrowser
)
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence, QPalette, QColor, QIcon, QClipboard, QCursor, QWheelEvent, QAction
from PyQt6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve, QPoint, qInstallMessageHandler, QtMsgType, QSettings, pyqtSignal, QThread
from PIL import Image
from threading import Thread
from collections import namedtuple
import time
import traceback
import requests

settings = QSettings("Majika", "MaPic")
updates = True

def get_latest_version():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    r = requests.get(url, timeout=5)
    data = r.json()
    return data["tag_name"].lstrip("v")

def is_newer(latest, current):
    def v(x): return [int(i) for i in x.split(".")]
    return v(latest) > v(current)

class UpdateChecker(QThread):
    update_found = pyqtSignal(str)  # ha új verzió van, elküldi a verziót
    up_to_date = pyqtSignal()       # ha minden ok

    def __init__(self, manual=False, parent=None):
        super().__init__(parent)
        self.manual = manual

    def run(self):
        settings = QSettings("Majika", "MaPic")
        if not self.manual and settings.value("skip_update_warning", False, bool):
            return

        try:
            latest = get_latest_version()  # a GitHub API hívás
            if is_newer(latest, APP_VERSION):
                self.update_found.emit(latest)
            else:
                self.up_to_date.emit()
        except Exception as e:
            print("Update check failed:", e)
            
"""
def check_for_updates(parent, manual=False):
    settings = QSettings("Majika", "MaPic")

    if not manual and settings.value("skip_update_warning", False, bool):
        return

    try:
        latest = get_latest_version()

        if is_newer(latest, APP_VERSION):
            box = QMessageBox(parent)
            box.setWindowTitle("Update available")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(
                f"New version available: {latest}\n"
                f"Current version: {APP_VERSION}\n\n"
                "Download from GitHub Releases."
            )

            checkbox = QCheckBox("Don't notify me again")
            box.setCheckBox(checkbox)

            box.exec()

            if checkbox.isChecked():
                settings.setValue("skip_update_warning", True)

        elif manual:
            QMessageBox.information(
                parent,
                "Up to date",
                "You are using the latest version."
            )

    except Exception as e:
        if manual:
            QMessageBox.warning(parent, "Error", str(e))
"""
            
DEBUG = True                            ##########################################################################

def debug_log(*args):
    if DEBUG:
        print("[DEBUG]", *args)          ##################################################
        
def global_exception_hook(exctype, value, tb):
    print("[UNCAUGHT EXCEPTION]")
    traceback.print_exception(exctype, value, tb)

sys.excepthook = global_exception_hook
img_width=0
img_height=0


def qt_message_handler(mode, context, message):
    print(f"[Qt {mode.name}] {message}")

qInstallMessageHandler(qt_message_handler)

# Definiáljuk a metaadat struktúrát
ImageMeta = namedtuple("ImageMeta", [
    "prompt",           # 0
    "neg_prompt",      
    "model",           
    "sampler",         
    "scheduler",       
    "steps",           
    "cfg_scale",       
    "seed",            
    "denoise",          # 8 - opcionális, ha kell
    "vae",            
    "loras"             # 10 - lista a több LoRA-ra
])

def empty_meta():
    """Visszaad egy alapértelmezett, üres ImageMeta namedtuple-t."""
    return ImageMeta(
        prompt="N/A",
        neg_prompt="N/A",
        model="-",
        sampler="-",
        scheduler="-",
        steps="-",
        cfg_scale="-",
        seed="-",
        denoise="-",
        vae="-",
        loras=[]
    )

def find_all_keys(d, key):
    """
    Rekurzívan megkeresi az összes adott kulcsot a JSON-ban.
    Minden előfordulás értékét listában adja vissza.
    """
    results = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k == key:
                results.append(v)
            elif isinstance(v, (dict, list)):
                results.extend(find_all_keys(v, key))
    elif isinstance(d, list):
        for item in d:
            results.extend(find_all_keys(item, key))
    return results

def extract_loras_from_usercomment(raw_uc):
    """
    Kinyeri a LoRA-kat a JPG UserComment mezőből JSON formátumból.
    Visszaad egy listát: [(name, weight), ...]
    Ha hiba történik, kiírja a konzolra, de nem áll le.
    """
    loras = []
    if isinstance(raw_uc, str):
        raw_text = raw_uc
    else:
        try:
            raw_text = json.dumps(raw_uc, ensure_ascii=False)
        except Exception:
            raw_text = str(raw_uc)

    try:
        # A UserComment tartalmazhat több JSON objektumot egymás után
        # Például: [{"type":"lora",...}, {"type":"lora",...}]
        matches = re.findall(r'\{[^\}]*"type"\s*:\s*"lora"[^\}]*\}', raw_text)
        for m in matches:
            try:
                d = json.loads(m)
                if d.get("type") == "lora":
                    name = d.get("modelName", "Unknown")
                    weight = d.get("weight", 1.0)
                    loras.append((name, weight))
            except Exception as inner_e:
                debug_log(f"[ERROR] Failed to parse LoRA block: {inner_e}\nBlock: {m}")
                continue

    except Exception as e:
        debug_log(f"[ERROR] Failed to extract LoRA from UserComment: {e}\nUserComment: {raw_text}")

    return loras

def extract_loras(obj):
    """Kinyeri a LoRA-kat PNG formátumokból.
    Támogatja a 'lora_name' + 'strength_model' mezőket ÉS a <lora:name:weight> formátumot is.
    Visszatér: [(name, weight), ...]"""
    
    results = []

    # --- 1) JSON-szerű kulcsok keresése ---
    def recursive_find_lora(o):
        if isinstance(o, dict):
            # ha tartalmaz lora_name és strength_model kulcsot
            if "lora_name" in o:
                name = o["lora_name"]
                weight = o.get("strength_model", o.get("weight", 1.0))
                results.append((name, weight))
            # rekurzió a többi kulcsra
            for v in o.values():
                recursive_find_lora(v)
        elif isinstance(o, list):
            for item in o:
                recursive_find_lora(item)

    recursive_find_lora(obj)

    # --- 2) Text formátum (pl. <lora:Name:0.8>) keresése ---
    if isinstance(obj, str):
        text = obj
    else:
        text = str(obj)

    lora_pattern = r"<lora:([^:>]+):([\d.]+)>"
    matches = re.findall(lora_pattern, text)
    for name, weight in matches:
        try:
            w = float(weight)
        except ValueError:
            w = 1.0
        results.append((name.strip(), w))

    # --- 3) Duplikátumok kiszűrése (név alapján) ---
    unique = {}
    for name, weight in results:
        unique[name] = weight  # utolsó előfordulás marad
    final_list = [(n, unique[n]) for n in unique]

    return final_list
    
# --- HTML/CSS stílus definíció ---
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

def decode_surrogate_pair(txt):
    if not txt:
        return "-"
    try:
        import codecs
        return codecs.decode(txt, 'unicode_escape')
    except Exception:
        return txt
        
def decode_surrogates(txt):
    if not txt:
        return "-"
    try:
        # kényszerített dekódolás surrogate-okból
        return txt.encode('utf-16', 'surrogatepass').decode('utf-16')
    except Exception:
        return txt
    
# ---------- Prompt extract (robosztusabb) ----------
def extract_from_usercomment(raw_uc):
    pos = neg = step = sampler = cfg = seed = denoise = scheduler = vae = loras = lora_names = lora_strengths = "no"
    try:
        # --- JSON-szerű formátum ---
        if raw_uc.strip().startswith("{"):
            data = json.loads(raw_uc)

            # Positive/negative prompt
            if "extraMetadata" in data:
                extra = json.loads(data["extraMetadata"])
                pos = extra.get("prompt", "-")
                neg = extra.get("negativePrompt", "-")
                sampler = extra.get("sampler", "-")
                step = str(extra.get("steps", "-"))
                cfg = str(extra.get("cfgScale", "-"))
                ckpt = extra.get("modelName", "-")  # ha van
                seed = str(extra.get("seed", "-")) 
                scheduler = str(extra.get("scheduler", "-")) 
                denoise = str(extra.get("denoise", "-"))
                vae = str(extra.get("vae", "-"))
                loras = extract_loras_from_usercomment(data)
                if not seed or seed == "-":
                    seeds = find_all_keys(data, "seed")
                    seed = seeds[0] if seeds else "-"
                if not scheduler or scheduler == "-":
                    schedulers = find_all_keys(data, "scheduler")
                    scheduler = schedulers[0] if schedulers else "-"
                if not loras or loras == "no":
                    lora_names = find_all_keys(data, "lora_name")
                    lora_strengths = find_all_keys(data, "strength_model")
                    loras = list(zip(lora_names, lora_strengths))
            
            # Bizonyos A1111/Comfy mentésnél a text közvetlenül van
            for k, v in data.items():
                if isinstance(v, dict) and v.get("class_type") == "smZ CLIPTextEncode":
                    if v["_meta"]["title"] == "Positive":
                        pos = v["inputs"].get("text", pos)
                    elif v["_meta"]["title"] == "Negative":
                        neg = v["inputs"].get("text", neg)

                if isinstance(v, dict) and v.get("class_type") == "CheckpointLoaderSimple":
                    ckpt = v["inputs"].get("ckpt_name", ckpt)

                if isinstance(v, dict) and v.get("class_type") == "FaceDetailer":
                    step = str(v["inputs"].get("steps", step))
                    cfg = str(v["inputs"].get("cfg", cfg))
                    sampler = v["inputs"].get("sampler_name", sampler)
                    seed = str(v["inputs"].get("seed", seed))
                    scheduler = str(v["inputs"].get("scheduler", scheduler))
                    denoise = str(v["inputs"].get("denoise", denoise))
                    vae = str(v["inputs"].get("vae", seed))
                    loras = extract_loras_from_usercomment(raw_uc)

        # --- sima szöveges formátum ---
        else:
            # Positive prompt (eleje a "Steps:" előtt)
            m = re.split(r"Steps:|steps:", raw_uc, 1)
            if len(m) > 1:
                pos = m[0].strip().rstrip(",.")
            else:
                pos = raw_uc.strip()

            # Negative prompt
            neg_m = re.search(r"Negative prompt:\s*(.*)", raw_uc, re.IGNORECASE)
            if neg_m:
                neg = neg_m.group(1).strip()

            # Steps
            step_m = re.search(r"Steps:\s*(\d+)", raw_uc)
            if step_m:
                step = step_m.group(1)

            # Sampler
            sampler_m = re.search(r"Sampler:\s*([^\n,]+)", raw_uc)
            if sampler_m:
                sampler = sampler_m.group(1).strip()

            # CFG
            cfg_m = re.search(r"CFG scale:\s*([\d.]+)", raw_uc, re.IGNORECASE)
            if cfg_m:
                cfg = cfg_m.group(1)

            # Seed
            seed_m = re.search(r"Seed:\s*(\d+)", raw_uc)
            if seed_m:
                seed = seed_m.group(1)

            # Scheduler
            scheduler_m = re.search(r"Scheduler:\s*(\d+)", raw_uc)
            if scheduler_m:
                scheduler = scheduler_m.group(1)

            # Denoise
            denoise_m = re.search(r"Denoise:\s*(\d+)", raw_uc)
            if denoise_m:
                denoise = denoise_m.group(1)

            # Vae
            vae_m = re.search(r"Vae:\s*(\d+)", raw_uc)
            if vae_m:
                vae = vae_m.group(1)

            # Lora
            loras = extract_loras_from_usercomment(raw_uc)

            # ModelName
            model_m = re.search(r'"modelName":"([^"]+)"', raw_uc)
            if model_m:
                ckpt = model_m.group(1)
                
            pos = decode_surrogate_pair(pos)
            neg = decode_surrogate_pair(neg)
            ckpt = decode_surrogate_pair(ckpt)

#    except Exception as e:
#        pos = f"Error: {e}"

    except Exception as e:
        debug_log(f"[ERROR] extract_prompts_jpg_useComments: ({e})")
    
    return ImageMeta(
        prompt = pos,
        neg_prompt = neg,
        model = ckpt,
        sampler = sampler,
        scheduler = scheduler,
        steps = step,
        cfg_scale = cfg,
        seed = seed,
        denoise = denoise,
        vae = vae,
        loras = loras           # lista
    )
        
def extract_prompts_jpg(image_path):
    try:
        # 1) exiftool meghívása JSON kimenettel
        result = subprocess.run(
            ["exiftool", "-j", "-UserComment", image_path],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data and "UserComment" in data[0]:
                raw_uc = data[0]["UserComment"]

                parsed = extract_from_usercomment(raw_uc)
                if parsed:
                    return parsed

        # ha nincs értelmezhető adat
        return empty_meta()

    except Exception as e:
        debug_log(f"[ERROR] extract_prompts_jpg: ({e})")
        return empty_meta()
        

def extract_prompts_png(image_path):
    try:
        img = Image.open(image_path)
        metadata = img.info

        # gyakori kulcsok, ahol a prompt/params előfordulhat
        raw_prompt = metadata.get("prompt") or metadata.get("parameters") or metadata.get("Description") or metadata.get("comment") or None
        if not raw_prompt:
            return empty_meta()

        # Ha raw_prompt nem JSON, próbáljuk meg JSON-ként parse-olni továbbra is.
        try:
            prompt_json = json.loads(raw_prompt)
        except Exception:
            # Ha nem JSON, visszaadjuk a teljes stringet mint positive prompt (biztonsági fallback)
            text_all = str(raw_prompt)
            text_all = " ".join(text_all.split())  # collapse whitespace
            meta = empty_meta()
            return meta._replace(prompt=text_all)

        # --- összegyűjtjük az első két "text" mezőt rekurzívan ---
        texts = []
        def collect_texts(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "text" and isinstance(v, str):
                        texts.append(v)
                    else:
                        collect_texts(v)
            elif isinstance(obj, list):
                for item in obj:
                    collect_texts(item)
        collect_texts(prompt_json)

        pos = texts[0] if len(texts) > 0 else "N/A"
        neg = texts[1] if len(texts) > 1 else "N/A"

        # --- kereső segédfüggvény (bárhol a JSON-ban) ---
        def find_key(obj, target):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == target:
                        return v
                    res = find_key(v, target)
                    if res is not None:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_key(item, target)
                    if res is not None:
                        return res
            return None

        ckpt     = find_key(prompt_json, "ckpt_name") or "-"
        if ckpt == "-":
            ckpt     = find_key(prompt_json, "unet_name") or "-"
        sampler  = find_key(prompt_json, "sampler_name") or "-"
        scheduler= find_key(prompt_json, "scheduler") or "-"
        step     = find_key(prompt_json, "steps") or "-"
        cfg      = find_key(prompt_json, "cfg") or "-"
        seed     = find_key(prompt_json, "seed") or "-"
        denoise     = find_key(prompt_json, "denoise") or "-"
        vae     = find_key(prompt_json, "vae") or "-"
        loras = extract_loras(prompt_json)

        return ImageMeta(
            prompt = pos,
            neg_prompt = neg,
            model = ckpt,
            sampler = sampler,
            scheduler = scheduler,
            steps = step,
            cfg_scale = cfg,
            seed = seed,
            denoise = denoise,
            vae = vae,
            loras = loras           # lista
        )

    except Exception as e:        
        result = ImageMeta("Error", *["N/A"]*11)
        debug_log(f"[ERROR] extract_prompts_png: ({e})")

def extract_prompts(fname):
    ext = os.path.splitext(fname)[1].lower()
    pos = neg = step = sampler = cfg = seed = denoise = scheduler = vae = loras = "no"
    
    if ext == ".png":
        from PIL import Image
        import re, json

        img = Image.open(fname)
        metadata = img.info

        if "prompt" in metadata:
            return extract_prompts_png(fname)  # meglévő JSON feldolgozás
        elif "parameters" in metadata:
            raw = metadata["parameters"]

            pos = re.search(r'^(.*?)\s*,?\s*Negative prompt:', raw, re.DOTALL)
            neg = re.search(r'Negative prompt:\s*(.*?)\s*,?\s*Steps:', raw)
            sampler = re.search(r'Sampler:\s*(.*?)(?=,|$)', raw)
            cfg = re.search(r'CFG scale:\s*(.*?)(?=,|$)', raw)
            step = re.search(r'Steps:\s*(.*?)(?=,|$)', raw)
            seed = re.search(r'Seed:\s*(.*?)(?=,|$)', raw)
            ckpt = re.search(r'Model:\s*(.*?)(?=,|$)', raw)
            scheduler = re.search(r'scheduler:\s*(.*?)(?=,|$)', raw)
            denoise = re.search(r'denoise:\s*(.*?)(?=,|$)', raw)
            vae = re.search(r'Vae:\s*(.*?)(?=,|$)', raw)
            loras = extract_loras(raw)
            
            pos = pos.group(1).replace("\n", " ") if pos else "N/A"
            neg = neg.group(1).replace("\n", " ") if neg else "N/A"
            ckpt = ckpt.group(1) if ckpt else "-"
            sampler = sampler.group(1) if sampler else "-"
            step = step.group(1) if step else "-"
            scheduler = scheduler.group(1) if scheduler else "-"
            cfg = cfg.group(1) if cfg else "-"
            seed = seed.group(1) if seed else "-"
            denoise = denoise.group(1) if denoise else "-"
            vae = vae.group(1) if vae else "-"
            
            return ImageMeta(
                prompt=pos,
                neg_prompt=neg,
                model=ckpt,
                sampler=sampler,
                scheduler=scheduler,
                steps=step,
                cfg_scale=cfg,
                seed=seed,
                denoise=denoise,
                vae=vae,
                loras=loras
            )
        else:
            return empty_meta()

    elif ext in (".jpg", ".jpeg"):
        return extract_prompts_jpg(fname)
    else:
        return empty_meta()

def is_system_dark():
    palette = QApplication.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    text_color = palette.color(QPalette.ColorRole.WindowText)
    # ha a háttér sötétebb mint a szöveg → dark mode
    return bg_color.lightness() < text_color.lightness()
    
class ToastMessage(QWidget):
    def __init__(self, parent, text, duration=1200):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.ToolTip |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Tartalom
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                background-color: rgba(40, 40, 40, 210);
                color: white;
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 12pt;
            }
        """)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.setContentsMargins(0, 0, 0, 0)

        # Elhelyezés a szülő közép-aljára
        pw = parent.width()
        ph = parent.height()
        self.adjustSize()  # kell a méret kiszámításhoz
        w = self.width()
        h = self.height()
        self.setGeometry((pw - w)//2, ph - h - 40, w, h)  # bottom-center

        # Fade-in
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(250)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Fade-out
        self.animation_out = QPropertyAnimation(self, b"windowOpacity")
        self.animation_out.setDuration(400)
        self.animation_out.setStartValue(1.0)
        self.animation_out.setEndValue(0.0)
        self.animation_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation_out.finished.connect(self.close)

        # Automatikus eltűnés
        QTimer.singleShot(duration, self.fade_out)

        self.animation.start()

    def fade_out(self):
        self.animation_out.start()

    @staticmethod
    def display(parent, text, duration=1000):
        toast = ToastMessage(parent, text, duration)
        toast.adjustSize()
        cursor_pos = QCursor.pos()
        tpos = QPoint(cursor_pos.x() - toast.width()//2, cursor_pos.y() - toast.height()//2)
        toast.move(tpos)    
        toast.show()
        return toast
        
# ---------- Main viewer ----------
class ImageViewer(QWidget):
    cache_progress = pyqtSignal(int, int)  # current, total
    
    def __init__(self):
        super().__init__()

#        self.thumbnail_cache_done = False
        # Ha van globális is_system_dark függvény, használjuk, különben False
        try:
            self.dark_mode = is_system_dark()
        except Exception:
            self.dark_mode = False

        # shortcuts (QShortcut import a QtGui-ból)
        QShortcut(QKeySequence("Right"), self, self.show_next)
        QShortcut(QKeySequence("Left"), self, self.show_prev)
        QShortcut(QKeySequence("Down"), self, self.show_next)
        QShortcut(QKeySequence("Up"), self, self.show_prev)

        self.setWindowTitle("MaPic - ImageView + AIMeta")

        # state
        self.image_files = []
        self.current_index = -1
        self.current_pixmap = None
        self.thumb_cache = {}
        self.aspect_ratio = Qt.AspectRatioMode.KeepAspectRatio
        self.smooth = Qt.TransformationMode.SmoothTransformation

        # main layout
        main_layout = QVBoxLayout(self)

        # ---------- build the existing image+meta splitter first ----------
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)

        # image label (large view)
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(200, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.splitter.addWidget(self.image_label)

        # meta text area (use QTextBrowser to support HTML)
        self.meta_text = QTextBrowser()
        self.meta_text.setReadOnly(True)
        self.meta_text.setMinimumSize(120, 120)
        self.splitter.addWidget(self.meta_text)
        # most, hogy mindkét widget bent van:
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        # --- ide jön a "link kezelés" - szöveg másolása vágólapra! ---
        self.meta_text.setOpenLinks(False)  # ne nyisson linket automatikusan
        self.meta_text.anchorClicked.connect(self.copy_link)

        self.splitter.setSizes([700, 150])

        # ---------- Stacked widget: image view and thumbnail view ----------
        self.stack = QStackedWidget(self)
        # image view widget (contains the splitter)
        self.image_view_widget = QWidget()
        iv_layout = QVBoxLayout(self.image_view_widget)
        iv_layout.addWidget(self.splitter)
        self.stack.addWidget(self.image_view_widget)

        # thumbnail view (scrollable)
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_container = QWidget()
        self.thumb_grid = QGridLayout(self.thumb_container)
        self.thumb_grid.setHorizontalSpacing(12)
        self.thumb_grid.setVerticalSpacing(12)
        self.thumb_grid.setContentsMargins(8, 8, 8, 8)
        self.thumb_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.first_width = 960
        self.thumb_scroll.setWidget(self.thumb_container)
        self.stack.addWidget(self.thumb_scroll)
        
        # thumbnail cache progress bar
        self.cache_label = QLabel("Thumbnail cache: 0 / 0")
        self.cache_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.cache_label)     
        self.cache_progress.connect(self.update_cache_label)   

        # show image view by default
        main_layout.addWidget(self.stack)
        self.stack.setCurrentWidget(self.image_view_widget)

        # ---------- control buttons ----------
        btn_layout = QHBoxLayout()
        # open folder
        self.btn_open = QPushButton("Open folder")
        self.btn_open.clicked.connect(self.open_folder)
        btn_layout.addWidget(self.btn_open)

        # theme toggle
        self.btn_toggle_theme = QPushButton("☯")
        self.btn_toggle_theme.clicked.connect(self.toggle_theme)
        btn_layout.addWidget(self.btn_toggle_theme)

        # prev / next
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self.show_prev)
        btn_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self.show_next)
        btn_layout.addWidget(self.btn_next)

        # orientation toggle (kept)
        self.btn_toggle = QPushButton("↔ / ↕")
        self.btn_toggle.clicked.connect(self.toggle_orientation)
        btn_layout.addWidget(self.btn_toggle)

        # save metadata
        self.btn_save = QPushButton("Save .txt")
        self.btn_save.clicked.connect(self.save_meta)
        btn_layout.addWidget(self.btn_save)
        
        self.current_meta = empty_meta()  # Namedtuple alapértelmezett értékekkel

        main_layout.addLayout(btn_layout)

        # ---------- interactions ----------
        # single-click the large image -> open thumbnails
        # assign inside __init__ (self exists here)
        self.image_label.mousePressEvent = self.show_thumbnails

        # ensure we have a small startup load (keeps the previous behavior)
        try:
            self.load_current_folder()
        except Exception:
            # if you don't have load_current_folder, it's OK; nothing loaded
            pass

        QTimer.singleShot(50, self._update_image_label)
        menubar = QMenuBar(self)
        help_menu = menubar.addMenu("Help")
        act_about = QAction("About", self)
        act_update = QAction("Check for updates", self)
        help_menu.addAction(act_about)
        help_menu.addAction(act_update)
#        main_layout.setMenuBar(menubar)
        act_update.triggered.connect(lambda: self.start_update_check(manual=True))
        act_about.triggered.connect(self.show_about)
        QTimer.singleShot(0, lambda: w.start_update_check(manual=False))        
        
    def show_update_popup(self, latest_version, manual):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Update available")
        msg.setText(f"New version available: {latest_version}\nCurrent: {APP_VERSION}")
        checkbox = QCheckBox("Don't notify me again")
        msg.setCheckBox(checkbox)
        msg.exec()

        if checkbox.isChecked():
            settings = QSettings("Majika", "MaPic")
            settings.setValue("skip_update_warning", True)

    def show_up_to_date(self, manual):
        if manual:
            QMessageBox.information(self, "Up to date", "You are using the latest version.")

    def start_update_check(self, manual=False):
        self.update_thread = UpdateChecker(manual=manual)
        self.update_thread.update_found.connect(lambda v: self.show_update_popup(v, manual))
        self.update_thread.up_to_date.connect(lambda: self.show_up_to_date(manual))
        self.update_thread.start()
    
    def show_about(self):
        QMessageBox.information(
            self,
            "About MaPic",
            f"MaPic – Majika Picture Viewer\n"
            f"Version: {APP_VERSION}\n\n"
            "AI image metadata viewer\n"
            "GitHub: github.com/Majika007/MaPic"
        )
    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.show_prev()   # görgő fel → előző kép
        elif delta < 0:
            self.show_next()   # görgő le → következő kép
        event.accept()

    def open_folder_and_select(self, fname):
        folder = os.path.dirname(fname)
        exts = (".png", ".jpg", ".jpeg", ".webp")
        self.image_files = sorted([
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(exts)
        ])
        # kiválasztott kép indexe
        self.current_index = self.image_files.index(fname)
        self.show_image(self.image_files[self.current_index])


    # ---------------- helper: get a thumbnail (with cache) ----------------
    
    def start_thumbnail_cache(self):
        if hasattr(self, "_cache_thread_started") and self._cache_thread_started:
            return
        self._cache_thread_started = True
        thread = Thread(target=self.preload_thumbnails, daemon=True)
        thread.start()

    def preload_thumbnails(self):
        w, h = 160, 120  # thumbnail méret
        for i, path in enumerate(self.image_files, start=1):
            pix = QPixmap(path)
            if pix.isNull():
                # üres thumbnail, ha valami hiba
                thumb = QPixmap(w, h)
                thumb.fill(Qt.GlobalColor.transparent)
            else:
                thumb = pix.scaled(w, h, self.aspect_ratio, self.smooth)
                self.thumb_cache[path] = thumb
                self.cache_progress.emit(i, len(self.image_files))  # frissítjük a progress jelzést
#            self.cache_progress.emit(i, total)  # frissítjük a progress jelzést
            
    # ---------------- show thumbnails grid ----------------
#    def resizeEvent(self, event):
#        super().resizeEvent(event)
#        if hasattr(self, 'thumb_grid') and hasattr(self, 'image_files'):
#            self.show_thumbnails()

    def update_cache_label(self, current, total):
        self.cache_label.setText(f"Thumbnail cache: {current} / {total}")

    def show_thumbnails(self, event=None):
        if not self.image_files:
            return
        # thumbnail méret + spacing
        thumb_w, thumb_h = 160, 120
        spacing = self.thumb_grid.horizontalSpacing() or 12

        container_width = self.first_width
        sys.stdout.flush()    
        # számoljuk, hány fér el vízszintesen
        cols = max(1, container_width // (thumb_w + spacing))
        
        for i in reversed(range(self.thumb_grid.count())):
            widget_item = self.thumb_grid.itemAt(i)
            if widget_item:
                w = widget_item.widget()
                if w:
                    w.setParent(None)

        # ha kevés a kép: számold ki hány oszlop van
        used_cols = min(cols, len(self.image_files))
        total_thumb_width = used_cols * thumb_w + (used_cols - 1) * spacing

        # mennyi maradék hely van két oldalon:
        side_margin = max((container_width - total_thumb_width) // 2, 0)

        # ezt állítsd be bal és jobb margónak
        self.thumb_grid.setContentsMargins(side_margin, 12, side_margin, 12)
        self.thumb_grid.setHorizontalSpacing(spacing)
        self.thumb_grid.setVerticalSpacing(spacing)
        
        for i, path in enumerate(self.image_files):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = self.thumb_cache.get(path, QPixmap(thumb_w, thumb_h))
            lbl.setPixmap(pixmap)
            lbl.setToolTip(os.path.basename(path))
            lbl.mousePressEvent = lambda e, idx=i: self.open_image_from_thumb(idx)
            row, col = divmod(i, cols)
            self.thumb_grid.addWidget(lbl, row, col)

        # mutassuk a thumb scrollt
        self.stack.setCurrentWidget(self.thumb_scroll)
        self.first_width = self.thumb_scroll.viewport().width()
        self.thumb_grid.update()
        self.thumb_scroll.viewport().update()
        QApplication.processEvents()

    # ---------------- open image from thumbnail click ----------------
    def open_image_from_thumb(self, index):
        if not (0 <= index < len(self.image_files)):
            return
        self.current_index = index
        self.show_image(self.image_files[self.current_index])
        # switch back to primary image view
        self.stack.setCurrentWidget(self.image_view_widget)

    # ---------------- safe image rescale from cached pixmap ----------------    #
    def _update_image_label(self):
        if not self.current_pixmap or self.current_pixmap.isNull():
            self.image_label.setText("No image loaded")
            return
        w = max(50, self.image_label.width())
        h = max(50, self.image_label.height())
        scaled = self.current_pixmap.scaled(w, h, self.aspect_ratio, self.smooth)
        self.image_label.setPixmap(scaled)
        

    # ---------------- show a single image + meta ----------------
    def show_image(self, fname):
        pix = QPixmap(fname)
        if pix.isNull():
            self.image_label.setText("Failed to load image")
            self.meta_text.setPlainText(f"Failed to load: {fname}")
            self.current_pixmap = None
            return

#        global updates
#        if updates:
#            check_for_updates(self)
#            updates = False
            
#        QTimer.singleShot(50, self._update_image_label)

        self.current_pixmap = pix
        # update label from cache pixmap
        self._update_image_label()

        # keep current_index in sync
        if fname in self.image_files:
            self.current_index = self.image_files.index(fname)

        # AI meta extraction (uses your existing extract_prompts function)
        try:
            result = extract_prompts(fname)
        except Exception as e:
            debug_log(f"[ERROR] extract_prompts({fname}): {e}")
            result = ImageMeta("Error: {e}", *["N/A"]*12)

        self.current_meta = result  # ahol parsed_meta egy ImageMeta objektum
        pos = " ".join(result.prompt.split())
        neg = " ".join(result.neg_prompt.split())
        img_width = pix.width()
        img_height = pix.height()

        # build HTML using your get_style() method if exists, else fallback
        
        try:
            style_block = self.get_style()
        except Exception:
            # fallback: try global styles
            style_block = (globals().get("STYLE_DARK") if self.dark_mode else globals().get("STYLE_LIGHT", ""))

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
        <span class="key3">🎲 Seed:<a href='seed_nr' title="Copy to clipboard"> 📋 </a></span> {result.seed} &nbsp;&nbsp;&nbsp;&nbsp;
        <!--<span class="key">🌀 Denoise:</span> {result.denoise}<br>
        <span class="key">🧠 VAE:</span> {result.vae}--> <br>
        <span class="key3">✨ LoRA:</span> {result.loras}
        """

        self.meta_text.setHtml(meta_html)
        # ensure we are in the image view
        self.stack.setCurrentWidget(self.image_view_widget)
        
#        if not self.thumbnail_cache_done:
#            self.start_thumbnail_cache()
#            self.thumbnail_cache_done = True


    # ---------------- get_style method (uses your global STYLE_* constants) ----------------
    def get_style(self):
        # prefer an internal dark_mode flag; STYLE_LIGHT/STYLE_DARK expected global
        return globals().get("STYLE_DARK") if self.dark_mode else globals().get("STYLE_LIGHT", "")

    # ---------------- toggle theme ----------------
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        # refresh meta display / style
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            self.show_image(self.image_files[self.current_index])
        else:
            # just update style block in the meta area
            self.meta_text.setHtml(self.get_style())

    # ---------------- next / prev image ----------------
    def show_next(self):
        if self.image_files and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.show_image(self.image_files[self.current_index])

    def show_prev(self):
        if self.image_files and self.current_index > 0:
            self.current_index -= 1
            self.show_image(self.image_files[self.current_index])

    # ---------------- open folder (clears thumbnail cache) ----------------
    def open_folder(self): 
        folder = QFileDialog.getExistingDirectory(self, "Select folder") 
        if not folder: 
            return 
        exts = (".png", ".jpg", ".jpeg", ".webp") 
        self.image_files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]) 
        self.current_index = 0 if self.image_files else -1 
        self._cache_thread_started = False
        self.thumb_cache.clear() # clear old thumbs 
        self.cache_total = 0
        self.cache_current = 0
        if self.image_files: 
            self.show_image(self.image_files[self.current_index]) 
        QTimer.singleShot(100, self.start_thumbnail_cache)

    # ---------------- load current folder at startup ----------------
    def load_current_folder(self):
        folder = os.getcwd()
        exts = (".png", ".jpg", ".jpeg", ".webp")
        self.image_files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)])
        self.current_index = 0 if self.image_files else -1
        self.thumb_cache.clear()
        if self.image_files:
            self.show_image(self.image_files[self.current_index])
        QTimer.singleShot(100, self.start_thumbnail_cache)

    # ---------------- toggle splitter orientation ----------------
    def toggle_orientation(self):
        s = self.splitter
        old_sizes = s.sizes()
        total_old = sum(old_sizes) if sum(old_sizes) > 0 else 1
        ratios = [float(x) / total_old for x in old_sizes]
        # set minimums so nothing collapses
        for i in range(s.count()):
            w = s.widget(i)
            if w:
                w.setMinimumSize(50, 50)
        # toggle orientation
        if s.orientation() == Qt.Orientation.Vertical:
            s.setOrientation(Qt.Orientation.Horizontal)
        else:
            s.setOrientation(Qt.Orientation.Vertical)
        # apply sizes based on new geometry after layout settles
        s.setSizes([max(50, int(r * (s.width() if s.orientation()==Qt.Orientation.Horizontal else s.height()))) for r in ratios])
        # update image scale
        self._update_image_label()

    # ---------------- save metadata to txt ----------------
    def save_meta(self):
        if not (self.image_files and 0 <= self.current_index < len(self.image_files)):
            return
        fname = self.image_files[self.current_index]
        try:
            result = extract_prompts(fname)
        except Exception as e:
            result = ImageMeta("Error: {e}", *["N/A"]*12)
        pos = " ".join(result.prompt.split())
        neg = " ".join(result.neg_prompt.split())
        
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
        except Exception as e:
            print("Save error:", e)

    # ---------------- handle resize -> rescale current pixmap ----------------
#    def resizeEvent(self, event):
#        super().resizeEvent(event)
#        # use a slight delay to allow layout updates, then rescale
#        self._update_image_label()

    def copy_link(self, url):

        pos = " ".join(self.current_meta.prompt.split())
        neg = " ".join(self.current_meta.neg_prompt.split())
        if url.toString() == "pos_prompt":
            clipboard = QApplication.clipboard()
            clipboard.setText(pos)
        if url.toString() == "neg_prompt":
            clipboard = QApplication.clipboard()
            clipboard.setText(neg)  
        if url.toString() == "seed_nr":
            clipboard = QApplication.clipboard()
            clipboard.setText(str(self.current_meta.seed))
        # Tooltip a kurzor közelében
#        QToolTip.showText(self.cursor().pos(), "✔ Text copied", self, QRect(), 1000)
        ToastMessage.display(self, "✔ Text copied")

    # ---------------- optional: keyPressEvent fallback ----------------

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.show_next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.show_prev()
        else:
            super().keyPressEvent(event)


# ---------- run ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ImageViewer()
    app.setWindowIcon(QIcon("MaPic.ico"))
    w.setWindowIcon(QIcon("MaPic.ico"))
    w.resize(1000, 850)
    if len(sys.argv) > 1:
        debug_log("Path -------- ", sys.argv)
        fname = os.path.abspath(sys.argv[1])
        w.open_folder_and_select(fname)
    w.show()
    sys.exit(app.exec())

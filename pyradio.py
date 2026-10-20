import os
import sys
import json
import math
import random
import socket
import time
import datetime
import threading
import urllib.request

import vlc
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF, QRectF, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSlider, QMessageBox, QLayout,
    QDialog, QTextEdit, QLineEdit, QStyle, QStyleOptionComboBox, QStylePainter, QStyledItemDelegate
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_SIZE = QSize(24, 24)
FAVORITE_GREEN = QColor(46, 204, 113)
ICON_LIGHT = QColor(225, 227, 230)
STATUS_COLORS = {"playing": "#2ecc71", "paused": "#f0a030", "stopped": "#8a8d93"}

API_DNS_HOST = "all.api.radio-browser.info"
API_FALLBACK_SERVERS = ["de1.api.radio-browser.info"]
API_TIMEOUT_SECONDS = 8
API_ATTEMPTS_PER_SERVER = 2
API_RETRY_DELAY_SECONDS = 1
USER_AGENT = "pyradio-qt/1.0"
CACHE_TTL_SECONDS = 2 * 60 * 60
MY_RADIOS_FILE = os.path.join(BASE_DIR, "my_radios.json")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pyradio")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")
API_CACHE_DIR = os.path.join(CONFIG_DIR, "cache")

WINDOW_MIN_WIDTH = 440
LABEL_WIDTH = 75
VOLUME_VALUE_WIDTH = 40
COMBO_WIDTH = 300
BUTTON_WIDTH = 100
BUTTON_HEIGHT = 32
UI_IMAGES_DIR = os.path.join(CONFIG_DIR, "ui")

STYLESHEET = """
QWidget { color: #eceef0; font-size: 11pt; }
QWidget#mainWindow {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f3136, stop:1 #1f2023);
}
QDialog, QMessageBox { background: #26272b; }
QLabel { background: transparent; color: #e4e6e9; }

QComboBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8a8d93, stop:0.08 #6d7076, stop:0.48 #55585d, stop:0.52 #45484d, stop:1 #393b3f);
    border: 1px solid #222326;
    border-top-color: #9a9da3;
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 20px;
    color: #f2f3f5;
}
QComboBox:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #9a9da3, stop:0.08 #7a7d83, stop:0.48 #61646a, stop:0.52 #505358, stop:1 #424448); }
QComboBox:disabled { color: #7d8086; }
QComboBox[favorite="true"] { color: #2ecc71; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(@CHEVRON_DOWN@); width: 12px; height: 12px; }
QComboBox#radioCombo::down-arrow { image: url(@CHEVRON_RIGHT@); }
QComboBox QAbstractItemView {
    background: #2b2d31;
    color: #f2f3f5;
    border: 1px solid #44474c;
    selection-background-color: #3d6b4f;
    selection-color: #ffffff;
    outline: 0;
}
QComboBox QAbstractItemView::item { min-height: 24px; padding: 0 6px; }

QLineEdit {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1f2023, stop:1 #2b2d31);
    border: 1px solid #55585d;
    border-top-color: #2a2b2e;
    border-radius: 12px;
    padding: 2px 12px;
    min-height: 20px;
    color: #f2f3f5;
    selection-background-color: #3d6b4f;
}
QLineEdit:focus { border-color: #2ecc71; }

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8a8d93, stop:0.08 #6d7076, stop:0.48 #55585d, stop:0.52 #45484d, stop:1 #393b3f);
    border: 1px solid #1c1d20;
    border-top-color: #9a9da3;
    border-radius: 4px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #9a9da3, stop:0.08 #7a7d83, stop:0.48 #61646a, stop:0.52 #505358, stop:1 #424448);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2c2e32, stop:1 #3d4045);
}
QPushButton:disabled {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6a6d72, stop:0.08 #55585d, stop:0.48 #46494d, stop:0.52 #3b3d41, stop:1 #313336);
    border-top-color: #7a7d82;
}
QPushButton#favoriteButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2c30, stop:1 #1b1c1f);
    border: 1px solid #45484d;
}
QPushButton#favoriteButton[favorite="true"] {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.5, fy:0.5,
        stop:0 #1e3a29, stop:1 #17191b);
    border: 1px solid #2f7a4d;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #121315;
    border: 1px solid #0b0b0c;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6ff2a5, stop:0.45 #34d27a, stop:1 #178a46);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #ffffff, stop:0.45 #c4c7cc, stop:0.55 #8d9095, stop:1 #5d6065);
    border: 1px solid #1a1b1d;
    width: 14px;
    margin: -7px 0;
    border-radius: 3px;
}

QTextEdit {
    background: #17181b;
    border: 1px solid #3f4247;
    border-radius: 6px;
    color: #cfd1d4;
}
QScrollBar:vertical { background: #1e1f22; width: 10px; }
QScrollBar::handle:vertical { background: #4a4d52; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""

GENRE_TAGS = {
    "rock", "pop", "sertanejo", "sertanejo universitario", "mpb", "funk",
    "samba", "pagode", "forró", "axé", "gospel", "jazz",
    "blues", "classical", "clássica", "electronic", "electronica",
    "eletronica", "eletrônica", "house", "techno", "trance", "hip hop",
    "hiphop", "hip-hop", "rap", "reggae", "reggaeton", "country", "dance",
    "disco", "folk", "indie", "metal", "punk", "ska", "soul", "rnb", "r&b",
    "latin", "latino", "salsa", "bachata", "merengue", "k-pop", "kpop",
    "j-pop", "jpop", "world music", "ambient", "chillout", "lounge",
    "instrumental", "adult hits", "oldies", "top 40", "alternative",
    "alternativo", "romantico", "romântico", "brega", "piseiro", "arrocha",
    "vaporwave", "lofi", "lo-fi", "drum and bass", "dubstep", "grime",
    "gothic", "industrial", "new age", "opera", "symphonic", "ballad",
    "acoustic", "bossa nova", "bossanova", "swing", "gaucha", "gaúcha",
    "vaquejada", "trap", "grunge", "hardrock", "hard rock", "classic rock",
    "soft rock", "worship", "praise", "flashback", "80s", "90s", "70s",
    "musica popular brasileira", "regional",
}


def discover_api_servers():
    """Resolve the Radio-Browser server list via DNS (as recommended by the API docs), shuffled"""
    servers = set()
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(API_DNS_HOST, 443, proto=socket.IPPROTO_TCP)}
        for address in addresses:
            try:
                hostname = socket.gethostbyaddr(address)[0]
            except OSError:
                continue
            if hostname.endswith(".api.radio-browser.info"):
                servers.add(hostname)
    except OSError:
        pass
    servers = list(servers) or list(API_FALLBACK_SERVERS)
    random.shuffle(servers)
    return servers


def load_disk_cache(name):
    try:
        with open(os.path.join(API_CACHE_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_disk_cache(name, data):
    try:
        os.makedirs(API_CACHE_DIR, exist_ok=True)
        with open(os.path.join(API_CACHE_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def _new_canvas(size):
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    return pixmap, painter


def _make_star_icon(size, color, filled=True):
    """Draw a 5-point star of the given color, filled or as an outline"""
    pixmap, painter = _new_canvas(size)
    if filled:
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
    else:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    cx, cy = size.width() / 2, size.height() / 2
    outer_r = min(size.width(), size.height()) / 2 * 0.95
    inner_r = outer_r * 0.5

    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        points.append(QPointF(cx - r * math.cos(angle), cy - r * math.sin(angle)))

    if filled:
        glow = QRadialGradient(cx, cy, outer_r * 1.05)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 150))
        glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), outer_r * 1.05, outer_r * 1.05)
        painter.setBrush(color)
        star = [QPointF(cx + (p.x() - cx) * 0.8, cy + (p.y() - cy) * 0.8) for p in points]
        painter.drawPolygon(QPolygonF(star))
    else:
        painter.drawPolygon(QPolygonF(points))
    painter.end()
    return QIcon(pixmap)


def _make_control_icon(kind, size, color=ICON_LIGHT):
    """Draw a flat play / pause / stop glyph"""
    pixmap, painter = _new_canvas(size)
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)
    w, h = size.width(), size.height()
    if kind == "play":
        painter.drawPolygon(QPolygonF([
            QPointF(w * 0.30, h * 0.20), QPointF(w * 0.30, h * 0.80), QPointF(w * 0.80, h * 0.50)
        ]))
    elif kind == "pause":
        painter.drawRoundedRect(QRectF(w * 0.24, h * 0.22, w * 0.18, h * 0.56), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(w * 0.58, h * 0.22, w * 0.18, h * 0.56), 1.5, 1.5)
    else:
        painter.drawRoundedRect(QRectF(w * 0.25, h * 0.25, w * 0.50, h * 0.50), 2, 2)
    painter.end()
    return QIcon(pixmap)


def _make_emoji_icon(emoji, px=18):
    """Render an emoji glyph as an icon (used as the leading icon of the filter combos)"""
    pixmap, painter = _new_canvas(QSize(px, px))
    font = QFont()
    font.setPixelSize(int(px * 0.8))
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, emoji)
    painter.end()

    image = pixmap.toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            gray = min(255, int(0.3 * c.red() + 0.59 * c.green() + 0.11 * c.blue()) + 60)
            image.setPixelColor(x, y, QColor(gray, gray, gray, c.alpha()))
    return QIcon(QPixmap.fromImage(image))


def _make_wave_pixmap(color, size=QSize(16, 16)):
    """Draw a small equalizer-like waveform used as the status indicator"""
    pixmap, painter = _new_canvas(size)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    w, h = size.width(), size.height()
    heights = [0.35, 0.7, 1.0, 0.55, 0.85, 0.4]
    bar_w = w / (len(heights) * 1.7)
    for i, factor in enumerate(heights):
        bar_h = h * factor
        x = i * bar_w * 1.7
        painter.drawRoundedRect(QRectF(x, (h - bar_h) / 2, bar_w, bar_h), 1, 1)
    painter.end()
    return pixmap


def _make_chevron_image(path, direction, color=ICON_LIGHT, size=QSize(24, 24)):
    pixmap, painter = _new_canvas(size)
    painter.setPen(QPen(color, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    w, h = size.width(), size.height()
    if direction == "down":
        points = [QPointF(w * 0.25, h * 0.38), QPointF(w * 0.5, h * 0.63), QPointF(w * 0.75, h * 0.38)]
    else:
        points = [QPointF(w * 0.38, h * 0.25), QPointF(w * 0.63, h * 0.5), QPointF(w * 0.38, h * 0.75)]
    painter.drawPolyline(QPolygonF(points))
    painter.end()
    pixmap.save(path, "PNG")


def build_stylesheet():
    """Generate the chevron images the stylesheet references and return the final QSS"""
    os.makedirs(UI_IMAGES_DIR, exist_ok=True)
    paths = {}
    for direction in ("down", "right"):
        path = os.path.join(UI_IMAGES_DIR, f"chevron_{direction}.png")
        _make_chevron_image(path, direction)
        paths[direction] = path.replace(os.sep, "/")
    return STYLESHEET.replace("@CHEVRON_DOWN@", paths["down"]).replace("@CHEVRON_RIGHT@", paths["right"])


class ComboItemDelegate(QStyledItemDelegate):
    """Item delegate that honors each item's own color (instead of the combo's palette) and draws separators"""

    def _is_separator(self, index):
        return index.data(Qt.AccessibleDescriptionRole) == "separator"

    def sizeHint(self, option, index):
        if self._is_separator(index):
            return QSize(0, 7)
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        if self._is_separator(index):
            y = option.rect.center().y()
            painter.setPen(QPen(QColor("#55585d"), 1))
            painter.drawLine(option.rect.left() + 4, y, option.rect.right() - 4, y)
            return
        super().paint(painter, option, index)


class TopAlignedComboBox(QComboBox):
    """A QComboBox whose popup always opens right below the box, scrolled to the top of the list,
    optionally showing a fixed leading icon next to the current text"""

    def __init__(self, leading_icon=None, parent=None):
        super().__init__(parent)
        self.leading_icon = leading_icon

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        if self.leading_icon is not None:
            option.currentIcon = self.leading_icon
            option.iconSize = QSize(18, 18)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)

    def showPopup(self):
        super().showPopup()
        self.view().scrollToTop()
        popup = self.view().window()
        popup.move(self.mapToGlobal(QPoint(0, self.height())))


class LogWindow(QDialog):
    def __init__(self, parent, messages):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.resize(700, 400)

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFontFamily("Courier New")
        self.text_edit.setFontPointSize(9)
        layout.addWidget(self.text_edit)

        if messages:
            self.text_edit.setPlainText("\n".join(messages))
            self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())

    def append_message(self, entry):
        self.text_edit.append(entry)


class RadioApp(QWidget):
    playback_started = Signal()
    playback_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Online Radio")
        self.setObjectName("mainWindow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(WINDOW_MIN_WIDTH)

        # Log window state (must exist before anything calls self.log)
        self.log_messages = []
        self.log_window = None

        # Initialize VLC
        try:
            self.vlc_instance = vlc.Instance("--no-video", "--network-caching=3000")
            self.player = self.vlc_instance.media_player_new()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not initialize VLC: {e}")
            self.log(f"Could not initialize VLC: {e}")

        # State variables
        self.is_playing = False
        self.current_stream = None
        self.current_radio = None
        self.volume_value = 70
        self.radios = {}
        self.radios_cache = {}
        self.favorites = self.load_favorites()
        self.api_servers = discover_api_servers()
        self.log(f"Radio-Browser servers: {', '.join(self.api_servers)}")

        self.playback_started.connect(self._update_ui_playing)
        self.playback_error.connect(self._on_playback_error)

        self.countries = self.load_countries()
        self.country_code_by_name = {name: code for name, code in self.countries}
        default_country = self.countries[0][0] if self.countries else ""

        self.setup_ui()

        if default_country:
            self.country_combo.setCurrentText(default_country)
            self.on_country_changed()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

    def load_countries(self):
        """Load the country list from the Radio-Browser API, alphabetically sorted, with Brazil first"""
        try:
            countries_data = self.api_get_json("/json/countries")
            save_disk_cache("countries", countries_data)
        except Exception as e:
            countries_data = load_disk_cache("countries")
            if countries_data is None:
                QMessageBox.critical(self, "Error", f"Could not fetch the country list: {e}")
                self.log(f"Could not fetch the country list: {e}")
                return []
            self.log(f"Could not fetch the country list ({e}); using local cache")

        countries = []
        for country in countries_data:
            name = (country.get("name") or "").strip()
            code = (country.get("iso_3166_1") or "").strip()
            if not name or not code:
                continue
            countries.append((name, code))

        countries.sort(key=lambda item: item[0])

        brazil_index = next(
            (i for i, (name, code) in enumerate(countries) if code == "BR"), None
        )
        if brazil_index is not None:
            brazil = countries.pop(brazil_index)
            countries.insert(0, brazil)

        return countries

    def load_my_radios(self):
        """Load manually-added radios from the local persistent JSON file"""
        try:
            with open(MY_RADIOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def load_favorites(self):
        """Load favorite radios from the local persistent JSON file"""
        try:
            with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_favorites(self):
        """Persist favorite radios to the local JSON file"""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.favorites, f, ensure_ascii=False, indent=2)

    def current_country_code(self):
        return self.country_code_by_name.get(self.country_combo.currentText())

    def get_all_favorites_flat(self):
        """Return all favorite stations across every country as {name: station}, migrating legacy entries"""
        flat = {}
        migrated = False
        for country_code in list(self.favorites.keys()):
            entries = self.favorites[country_code]
            if isinstance(entries, list):
                country_radios = self.load_radios(country_code)
                entries = {name: country_radios[name] for name in entries if name in country_radios}
                self.favorites[country_code] = entries
                migrated = True
            flat.update(entries)
        if migrated:
            self.save_favorites()
        return flat

    def is_favorite(self, radio_name):
        return radio_name in self.get_all_favorites_flat()

    def toggle_favorite(self):
        """Add or remove the currently playing radio from the favorites list"""
        if not self.current_radio:
            return

        station = getattr(self, "combo_stations", {}).get(self.current_radio) or self.radios.get(self.current_radio)
        if not station:
            return

        origin_country = station.get("country_code") or self.current_country_code()
        favorites_for_origin = self.favorites.setdefault(origin_country, {})
        if not isinstance(favorites_for_origin, dict):
            favorites_for_origin = {}
            self.favorites[origin_country] = favorites_for_origin

        if self.current_radio in favorites_for_origin:
            del favorites_for_origin[self.current_radio]
            if not favorites_for_origin:
                del self.favorites[origin_country]
        else:
            favorites_for_origin[self.current_radio] = station

        self.save_favorites()
        self.update_favorite_button()
        self.apply_filters()

    def update_favorite_button(self):
        """Reflect the favorite status of the currently selected radio on the button icon and combo text"""
        is_fav = self.is_favorite(self.current_radio)
        self.favorite_btn.setIcon(self.favorite_icon_filled if is_fav else self.favorite_icon_empty)

        for widget in (self.radio_combo, self.favorite_btn):
            widget.setProperty("favorite", is_fav)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def load_radios(self, country_code):
        """Load radios from the Radio-Browser API, filtered by country (with cache)"""
        cached = self.radios_cache.get(country_code)
        if cached is not None:
            radios, cached_at = cached
            if time.time() - cached_at < CACHE_TTL_SECONDS:
                return radios

        path = "/json/stations/search?order=clickcount&reverse=true&limit=500&hidebroken=true"
        if country_code:
            path += f"&countrycode={country_code}"
        cache_name = f"stations_{country_code or 'all'}"
        try:
            stations = self.api_get_json(path)
            save_disk_cache(cache_name, stations)
        except Exception as e:
            stations = load_disk_cache(cache_name)
            if stations is None:
                QMessageBox.critical(self, "Error", f"Could not fetch the radio API: {e}")
                self.log(f"Could not fetch the radio API: {e}")
                return {}
            self.log(f"Could not fetch the radio API ({e}); using local cache")

        radios = {}
        for station in stations:
            name = (station.get("name") or "").strip()
            stream_url = station.get("url_resolved") or station.get("url") or ""
            stream_url = stream_url.strip()
            if not name or not stream_url:
                continue
            if "quran" in name.lower():
                continue
            if name in radios:
                name = f"{name} ({station.get('countrycode', '')})"
            tags_raw = (station.get("tags") or "").strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            station_country_code = (station.get("countrycode") or country_code or "").strip()
            radios[name] = {
                "url": stream_url,
                "uuid": station.get("stationuuid"),
                "tags": tags,
                "country_code": station_country_code,
            }

        my_radios = self.load_my_radios().get(country_code, {})
        for extra_station in my_radios.values():
            extra_station.setdefault("country_code", country_code)
        radios.update(my_radios)

        radios = dict(sorted(radios.items()))
        self.radios_cache[country_code] = (radios, time.time())
        return radios

    def register_click(self, uuid):
        """Notify the API that the station was played (Radio-Browser click tracking)"""
        if not uuid:
            return
        try:
            self.api_get_json(f"/json/url/{uuid}", attempts_per_server=1, log_failures=False)
        except Exception:
            pass

    def api_get_json(self, path, attempts_per_server=API_ATTEMPTS_PER_SERVER, log_failures=True):
        """GET a Radio-Browser endpoint, retrying and falling back across servers"""
        last_error = None
        for server in list(self.api_servers):
            for attempt in range(attempts_per_server):
                if attempt:
                    time.sleep(API_RETRY_DELAY_SECONDS)
                request = urllib.request.Request(
                    f"https://{server}{path}", headers={"User-Agent": USER_AGENT}
                )
                try:
                    with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                        data = json.load(response)
                except Exception as e:
                    last_error = e
                    if log_failures:
                        self.log(f"{server}{path.split('?')[0]} failed (attempt {attempt + 1}): {e}")
                    continue
                if self.api_servers[0] != server:
                    self.api_servers.remove(server)
                    self.api_servers.insert(0, server)
                return data
        raise last_error or RuntimeError("No Radio-Browser server available")

    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        # ===== COUNTRY FILTER =====
        country_row = QHBoxLayout()
        country_label = QLabel("Country:")
        country_label.setFixedWidth(LABEL_WIDTH)
        country_label.mouseDoubleClickEvent = self.show_log_window
        country_row.addWidget(country_label)

        self.country_combo = TopAlignedComboBox(_make_emoji_icon("🗺️"))
        self.country_combo.setFixedWidth(COMBO_WIDTH)
        self.country_combo.addItems([name for name, _ in self.countries])
        self.country_combo.currentIndexChanged.connect(self.on_country_changed)
        country_row.addWidget(self.country_combo)
        layout.addLayout(country_row)

        # ===== CATEGORY FILTER =====
        category_row = QHBoxLayout()
        category_label = QLabel("Genre:")
        category_label.setFixedWidth(LABEL_WIDTH)
        category_row.addWidget(category_label)

        self.category_combo = TopAlignedComboBox(_make_emoji_icon("🎨"))
        self.category_combo.setFixedWidth(COMBO_WIDTH)
        self.category_combo.currentIndexChanged.connect(self.apply_filters)
        category_row.addWidget(self.category_combo)
        layout.addLayout(category_row)

        # ===== SEARCH FILTER =====
        search_row = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setFixedWidth(LABEL_WIDTH)
        search_row.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(COMBO_WIDTH)
        self.search_input.textChanged.connect(self.apply_filters)
        search_row.addWidget(self.search_input)
        layout.addLayout(search_row)

        # ===== RADIO SELECTION =====
        radio_row = QHBoxLayout()
        radio_label = QLabel("Radio:")
        radio_label.setFixedWidth(LABEL_WIDTH)
        radio_row.addWidget(radio_label)

        self.radio_combo = TopAlignedComboBox(_make_emoji_icon("📡"))
        self.radio_combo.setObjectName("radioCombo")
        self.radio_combo.setItemDelegate(ComboItemDelegate(self.radio_combo))
        self.radio_combo.setFixedWidth(COMBO_WIDTH)
        self.radio_combo.view().installEventFilter(self)
        self.radio_combo.currentIndexChanged.connect(self.on_radio_selected)
        radio_row.addWidget(self.radio_combo)
        layout.addLayout(radio_row)

        # ===== CONTROL BUTTONS =====
        button_row = QHBoxLayout()

        self.play_btn = QPushButton()
        self.play_btn.setIcon(_make_control_icon("play", ICON_SIZE))
        self.play_btn.setIconSize(ICON_SIZE)
        self.play_btn.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.play_btn.clicked.connect(self.play)
        button_row.addWidget(self.play_btn)

        self.pause_btn = QPushButton()
        self.pause_btn.setIcon(_make_control_icon("pause", ICON_SIZE))
        self.pause_btn.setIconSize(ICON_SIZE)
        self.pause_btn.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.pause_btn.clicked.connect(self.pause)
        self.pause_btn.setEnabled(False)
        button_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(_make_control_icon("stop", ICON_SIZE))
        self.stop_btn.setIconSize(ICON_SIZE)
        self.stop_btn.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        button_row.addWidget(self.stop_btn)

        self.favorite_icon_empty = _make_star_icon(ICON_SIZE, ICON_LIGHT, filled=False)
        self.favorite_icon_filled = _make_star_icon(ICON_SIZE, FAVORITE_GREEN)

        self.favorite_btn = QPushButton()
        self.favorite_btn.setObjectName("favoriteButton")
        self.favorite_btn.setIcon(self.favorite_icon_empty)
        self.favorite_btn.setIconSize(ICON_SIZE)
        self.favorite_btn.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        button_row.addWidget(self.favorite_btn)

        layout.addLayout(button_row)

        # ===== VOLUME =====
        volume_row = QHBoxLayout()
        volume_label = QLabel("Volume:")
        volume_label.setFixedWidth(LABEL_WIDTH)
        volume_row.addWidget(volume_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.set_volume)
        volume_row.addWidget(self.volume_slider)

        self.volume_label = QLabel("70%")
        self.volume_label.setFixedWidth(VOLUME_VALUE_WIDTH)
        self.volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        volume_row.addWidget(self.volume_label)
        layout.addLayout(volume_row)

        # ===== STATUS =====
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(16, 16)
        status_row.addWidget(self.status_icon, 0, Qt.AlignTop)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setFixedWidth(LABEL_WIDTH + COMBO_WIDTH)
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        layout.addLayout(status_row)
        self._set_status("stopped", "Stopped")

    def _set_status(self, state, text, radio_name=None):
        """Show the status line: colored waveform + colored state text + (white) radio name"""
        color = STATUS_COLORS[state]
        self.status_icon.setPixmap(_make_wave_pixmap(color))
        html = f'<span style="color:{color};">Status: {text}</span>'
        if radio_name:
            html += f' <span style="color:#e6e7e9;">- {radio_name.replace("<", "&lt;")}</span>'
        self.status_label.setText(html)

    def on_country_changed(self, index=None):
        """Reload the radio list when the selected country changes"""
        country_code = self.country_code_by_name.get(self.country_combo.currentText())
        self.radios = self.load_radios(country_code)

        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)

        self.update_categories()
        favorite_names, regular_names = self.apply_filters()

        autoplay_target = regular_names[0] if regular_names else (favorite_names[0] if favorite_names else None)
        if autoplay_target:
            self.radio_combo.blockSignals(True)
            self.radio_combo.setCurrentText(autoplay_target)
            self.radio_combo.blockSignals(False)
            self.on_radio_selected(self.radio_combo.currentIndex())

    def update_categories(self):
        """Rebuild the category combo box from the musical genre tags of the currently loaded radios"""
        tags = set()
        for station in self.radios.values():
            for tag in station.get("tags", []):
                if tag.lower() in GENRE_TAGS:
                    tags.add(tag)
        categories = ["All"] + sorted(tags)

        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItems(categories)
        self.category_combo.blockSignals(False)

    def apply_filters(self, *args):
        """Filter the radio list based on the search text and selected category.

        Favorites (from every country) are pinned at the top, separated from the
        regular (current country) list by a native combo box separator.
        """
        search_text = self.search_input.text().strip().lower()
        category = self.category_combo.currentText()

        def matches(station, name, ignore_category=False):
            if search_text and search_text not in name.lower():
                return False
            if not ignore_category and category and category != "All" and category not in station.get("tags", []):
                return False
            return True

        all_favorites = self.get_all_favorites_flat()
        favorite_names = sorted(
            name for name, station in all_favorites.items()
            if matches(station, name, ignore_category=True)
        )
        favorite_set = set(favorite_names)

        regular_names = sorted(
            name for name, station in self.radios.items()
            if name not in favorite_set and matches(station, name)
        )

        self.combo_stations = {}
        for name in favorite_names:
            self.combo_stations[name] = all_favorites[name]
        for name in regular_names:
            self.combo_stations[name] = self.radios[name]

        self.radio_combo.blockSignals(True)
        self.radio_combo.clear()
        if favorite_names:
            self.radio_combo.addItems(favorite_names)
            for i in range(len(favorite_names)):
                self.radio_combo.setItemData(i, FAVORITE_GREEN, Qt.ForegroundRole)
            if regular_names:
                self.radio_combo.insertSeparator(self.radio_combo.count())
        self.radio_combo.addItems(regular_names)

        all_names = favorite_names + regular_names
        if self.current_radio in all_names:
            self.radio_combo.setCurrentText(self.current_radio)
        self.radio_combo.blockSignals(False)

        if len(all_names) == 1 and all_names[0] != self.current_radio:
            self.on_radio_selected(0)

        typing_search = self.search_input.hasFocus() or self.radio_combo.view().isVisible()
        if search_text and typing_search:
            if all_names:
                self.radio_combo.showPopup()
            else:
                self.radio_combo.hidePopup()
                self.search_input.setFocus()

        return favorite_names, regular_names

    def on_radio_selected(self, index=None):
        """When a new radio is selected in the combo box, switch and play automatically"""
        radio_name = self.radio_combo.currentText()
        if not radio_name:
            return

        if radio_name == self.current_radio and self.is_playing:
            return

        if self.is_playing:
            try:
                self.player.stop()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
            self.is_playing = False

        self.play(radio_name)
        self.search_input.clear()

    def play(self, radio_name=None):
        """Play the selected radio"""
        if not self.is_playing:
            if not radio_name or isinstance(radio_name, bool):
                radio_name = self.radio_combo.currentText()
                if not radio_name:
                    return

            station = getattr(self, "combo_stations", {}).get(radio_name) or self.radios.get(radio_name)

            if not station:
                QMessageBox.critical(self, "Error", "Stream URL not found")
                return

            self.current_stream = station["url"]
            self.current_radio = radio_name
            self.update_favorite_button()

            thread = threading.Thread(target=self._play_stream, daemon=True)
            thread.start()
            threading.Thread(target=self.register_click, args=(station["uuid"],), daemon=True).start()

    def _play_stream(self):
        """Thread that plays the stream"""
        try:
            media = self.vlc_instance.media_new(self.current_stream)
            self.player.set_media(media)
            self.player.audio_set_volume(self.volume_value)
            self.player.play()
            self.is_playing = True

            self.playback_started.emit()

        except Exception as e:
            self.is_playing = False
            self.playback_error.emit(str(e))

    def _on_playback_error(self, message):
        QMessageBox.critical(self, "Playback Error", message)
        self._update_ui_stopped()

    def pause(self):
        """Pause playback"""
        if self.is_playing:
            try:
                self.player.set_pause(1)
                self.is_playing = False
                self._update_ui_paused()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def stop(self):
        """Stop playback"""
        state = self.player.get_state()
        if state not in (vlc.State.NothingSpecial, vlc.State.Stopped, vlc.State.Ended):
            try:
                self.player.stop()
                self.is_playing = False
                self._update_ui_stopped()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def set_volume(self, value):
        """Adjust volume"""
        self.volume_value = int(value)
        self.volume_label.setText(f"{self.volume_value}%")

        try:
            self.player.audio_set_volume(self.volume_value)
        except Exception as e:
            print(f"Error adjusting volume: {e}")

    def _update_ui_playing(self):
        """Update UI when playing"""
        self.log(f"Playing radio: {self.current_radio} ({self.current_stream})")
        self.play_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self._set_status("playing", "Playing", self.current_radio)

    def _update_ui_paused(self):
        """Update UI when paused"""
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status("paused", "Paused", self.current_radio)

    def _update_ui_stopped(self, message="Stopped"):
        """Update UI when stopped"""
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.country_combo.setEnabled(True)
        self._set_status("stopped", message)

    def update_status(self):
        """Periodically check playback status"""
        state = self.player.get_state()
        if self.is_playing and state in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped):
            self.is_playing = False
            if state in (vlc.State.Ended, vlc.State.Error):
                self.log(f"Erro de conexão/TLS: {self.current_radio}")
                self._update_ui_stopped("Erro de conexão/TLS")
            else:
                self.log(f"Channel not available: {self.current_radio} ({state})")
                self._update_ui_stopped()

    def eventFilter(self, obj, event):
        """While the radio popup is open, keep forwarding typed text to the search field"""
        if obj is self.radio_combo.view() and event.type() == QEvent.KeyPress:
            editing_keys = (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End)
            if event.key() in editing_keys or (event.text() and event.text().isprintable()):
                QApplication.sendEvent(self.search_input, event)
                return True
        return super().eventFilter(obj, event)

    def log(self, message):
        """Record a message in the log buffer, print it to the terminal and, if the log window is open, show it there"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.log_messages.append(entry)
        print(entry)

        if self.log_window is not None:
            self.log_window.append_message(entry)

    def show_log_window(self, event=None):
        """Open (or focus) a window showing the log messages collected so far"""
        if self.log_window is not None:
            self.log_window.raise_()
            self.log_window.activateWindow()
            return

        self.log_window = LogWindow(self, self.log_messages)
        self.log_window.finished.connect(self._on_log_window_closed)
        self.log_window.show()

    def _on_log_window_closed(self):
        self.log_window = None


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    window = RadioApp()
    window.show()

    screen_geometry = app.primaryScreen().availableGeometry()
    window_geometry = window.frameGeometry()
    window.move(
        screen_geometry.x() + (screen_geometry.width() - window_geometry.width()) // 2,
        screen_geometry.y() + (screen_geometry.height() - window_geometry.height()) // 2,
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

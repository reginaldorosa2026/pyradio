import os
import sys
import json
import math
import time
import datetime
import threading
import urllib.request

import vlc
from PySide6.QtCore import Qt, QPoint, QPointF, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSlider, QMessageBox, QLayout,
    QDialog, QTextEdit, QLineEdit
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_SIZE = QSize(24, 24)
FAVORITE_GREEN = QColor(46, 204, 113)

API_BASE = "https://de1.api.radio-browser.info"
USER_AGENT = "pyradio-qt/1.0"
CACHE_TTL_SECONDS = 2 * 60 * 60
MY_RADIOS_FILE = os.path.join(BASE_DIR, "my_radios.json")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pyradio")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")

WINDOW_MIN_WIDTH = 440
LABEL_WIDTH = 75
VOLUME_VALUE_WIDTH = 40
COMBO_WIDTH = 300
BUTTON_WIDTH = 100

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


def _make_filled_star_icon(size, color):
    """Draw a filled 5-point star of the given color, matching an outline icon's size"""
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)

    cx, cy = size.width() / 2, size.height() / 2
    outer_r = min(size.width(), size.height()) / 2 * 0.95
    inner_r = outer_r * 0.5

    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        points.append(QPointF(cx - r * math.cos(angle), cy - r * math.sin(angle)))

    painter.drawPolygon(QPolygonF(points))
    painter.end()
    return QIcon(pixmap)


class TopAlignedComboBox(QComboBox):
    """A QComboBox whose popup always opens right below the box, scrolled to the top of the list"""

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
        request = urllib.request.Request(
            f"{API_BASE}/json/countries", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                countries_data = json.load(response)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch the country list: {e}")
            self.log(f"Could not fetch the country list: {e}")
            return []

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

        color = FAVORITE_GREEN if is_fav else self._default_radio_text_color
        palette = self.radio_combo.palette()
        palette.setColor(QPalette.Text, color)
        palette.setColor(QPalette.ButtonText, color)
        self.radio_combo.setPalette(palette)

    def load_radios(self, country_code):
        """Load radios from the Radio-Browser API, filtered by country (with cache)"""
        cached = self.radios_cache.get(country_code)
        if cached is not None:
            radios, cached_at = cached
            if time.time() - cached_at < CACHE_TTL_SECONDS:
                return radios

        url = (
            f"{API_BASE}/json/stations/search?order=clickcount&reverse=true"
            f"&limit=500&hidebroken=true"
        )
        if country_code:
            url += f"&countrycode={country_code}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                stations = json.load(response)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch the radio API: {e}")
            self.log(f"Could not fetch the radio API: {e}")
            return {}

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
        request = urllib.request.Request(
            f"{API_BASE}/json/url/{uuid}",
            headers={"User-Agent": USER_AGENT}
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except Exception:
            pass

    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        # ===== COUNTRY FILTER =====
        country_row = QHBoxLayout()
        country_label = QLabel("Country:")
        country_label.setFixedWidth(LABEL_WIDTH)
        country_label.mouseDoubleClickEvent = self.show_log_window
        country_row.addWidget(country_label)

        self.country_combo = TopAlignedComboBox()
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

        self.category_combo = TopAlignedComboBox()
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

        self.radio_combo = TopAlignedComboBox()
        self.radio_combo.setFixedWidth(COMBO_WIDTH)
        self._default_radio_text_color = self.radio_combo.palette().color(QPalette.Text)
        self.radio_combo.currentIndexChanged.connect(self.on_radio_selected)
        radio_row.addWidget(self.radio_combo)
        layout.addLayout(radio_row)

        # ===== CONTROL BUTTONS =====
        button_row = QHBoxLayout()

        self.play_btn = QPushButton()
        self.play_btn.setIcon(QIcon(os.path.join(ASSETS_DIR, "play.png")))
        self.play_btn.setIconSize(ICON_SIZE)
        self.play_btn.setFixedWidth(BUTTON_WIDTH)
        self.play_btn.clicked.connect(self.play)
        button_row.addWidget(self.play_btn)

        self.pause_btn = QPushButton()
        self.pause_btn.setIcon(QIcon(os.path.join(ASSETS_DIR, "pause.png")))
        self.pause_btn.setIconSize(ICON_SIZE)
        self.pause_btn.setFixedWidth(BUTTON_WIDTH)
        self.pause_btn.clicked.connect(self.pause)
        self.pause_btn.setEnabled(False)
        button_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(QIcon(os.path.join(ASSETS_DIR, "stop.png")))
        self.stop_btn.setIconSize(ICON_SIZE)
        self.stop_btn.setFixedWidth(BUTTON_WIDTH)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        button_row.addWidget(self.stop_btn)

        favorite_outline_path = os.path.join(ASSETS_DIR, "add_favorite.png")
        self.favorite_icon_empty = QIcon(favorite_outline_path)
        self.favorite_icon_filled = _make_filled_star_icon(ICON_SIZE, FAVORITE_GREEN)

        self.favorite_btn = QPushButton()
        self.favorite_btn.setIcon(self.favorite_icon_empty)
        self.favorite_btn.setIconSize(ICON_SIZE)
        self.favorite_btn.setFixedWidth(BUTTON_WIDTH)
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
        volume_row.addWidget(self.volume_label)
        layout.addLayout(volume_row)

        # ===== STATUS =====
        self.status_label = QLabel("Status: Stopped")
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setWordWrap(True)
        self.status_label.setFixedWidth(LABEL_WIDTH + COMBO_WIDTH)
        layout.addWidget(self.status_label)

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

        if search_text and all_names and self.search_input.hasFocus():
            self.radio_combo.showPopup()

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
        self.status_label.setText(f"Status: Playing - {self.current_radio}")
        self.status_label.setStyleSheet("color: green;")

    def _update_ui_paused(self):
        """Update UI when paused"""
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(f"Status: Paused - {self.current_radio}")
        self.status_label.setStyleSheet("color: orange;")

    def _update_ui_stopped(self, message="Stopped"):
        """Update UI when stopped"""
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.country_combo.setEnabled(True)
        self.status_label.setText(f"Status: {message}")
        self.status_label.setStyleSheet("color: gray;")

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

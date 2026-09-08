import sys
import json
import datetime
import threading
import urllib.request

import vlc
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSlider, QMessageBox, QLayout,
    QDialog, QTextEdit, QLineEdit
)

API_BASE = "https://de1.api.radio-browser.info"
USER_AGENT = "pyradio-qt/1.0"

WINDOW_MIN_WIDTH = 420
LABEL_WIDTH = 60
VOLUME_VALUE_WIDTH = 40
COMBO_WIDTH = 300
BUTTON_WIDTH = 100


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
            self.vlc_instance = vlc.Instance("--no-video")
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

    def load_radios(self, country_code):
        """Load radios from the Radio-Browser API, filtered by country"""
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
            if name in radios:
                name = f"{name} ({station.get('countrycode', '')})"
            radios[name] = {"url": stream_url, "uuid": station.get("stationuuid")}
        return dict(sorted(radios.items()))

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

        self.country_combo = QComboBox()
        self.country_combo.setFixedWidth(COMBO_WIDTH)
        self.country_combo.addItems([name for name, _ in self.countries])
        self.country_combo.currentIndexChanged.connect(self.on_country_changed)
        country_row.addWidget(self.country_combo)
        layout.addLayout(country_row)

        # ===== SEARCH FILTER =====
        search_row = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setFixedWidth(LABEL_WIDTH)
        search_row.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(COMBO_WIDTH)
        self.search_input.textChanged.connect(self.filter_radios)
        search_row.addWidget(self.search_input)
        layout.addLayout(search_row)

        # ===== RADIO SELECTION =====
        radio_row = QHBoxLayout()
        radio_label = QLabel("Radio:")
        radio_label.setFixedWidth(LABEL_WIDTH)
        radio_row.addWidget(radio_label)

        self.radio_combo = QComboBox()
        self.radio_combo.setFixedWidth(COMBO_WIDTH)
        self.radio_combo.currentIndexChanged.connect(self.on_radio_selected)
        radio_row.addWidget(self.radio_combo)
        layout.addLayout(radio_row)

        # ===== CONTROL BUTTONS =====
        button_row = QHBoxLayout()

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(BUTTON_WIDTH)
        self.play_btn.clicked.connect(self.play)
        button_row.addWidget(self.play_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setFixedWidth(BUTTON_WIDTH)
        self.pause_btn.clicked.connect(self.pause)
        self.pause_btn.setEnabled(False)
        button_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedWidth(BUTTON_WIDTH)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        button_row.addWidget(self.stop_btn)

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
        layout.addWidget(self.status_label)

    def on_country_changed(self, index=None):
        """Reload the radio list when the selected country changes"""
        country_code = self.country_code_by_name.get(self.country_combo.currentText())
        self.radios = self.load_radios(country_code)

        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)

        radio_names = list(self.radios.keys())

        self.radio_combo.blockSignals(True)
        self.radio_combo.clear()
        self.radio_combo.addItems(radio_names)
        self.radio_combo.blockSignals(False)

        if radio_names:
            self.on_radio_selected(0)

    def filter_radios(self, text):
        """Filter the radio list in the combo box based on the search text"""
        search_text = text.strip().lower()
        radio_names = [name for name in self.radios.keys() if search_text in name.lower()]

        self.radio_combo.blockSignals(True)
        self.radio_combo.clear()
        self.radio_combo.addItems(radio_names)
        self.radio_combo.blockSignals(False)

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

    def play(self, radio_name=None):
        """Play the selected radio"""
        if not self.is_playing:
            if not radio_name or isinstance(radio_name, bool):
                radio_name = self.radio_combo.currentText()
                if not radio_name:
                    return

            station = self.radios.get(radio_name)

            if not station:
                QMessageBox.critical(self, "Error", "Stream URL not found")
                return

            self.current_stream = station["url"]
            self.current_radio = radio_name

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

    def _update_ui_stopped(self):
        """Update UI when stopped"""
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.country_combo.setEnabled(True)
        self.status_label.setText("Status: Stopped")
        self.status_label.setStyleSheet("color: gray;")

    def update_status(self):
        """Periodically check playback status"""
        state = self.player.get_state()
        if self.is_playing and state in (vlc.State.Ended, vlc.State.Error, vlc.State.Stopped):
            self.is_playing = False
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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""
ui/screens/settings_screen.py
==============================
BLE device management and app configuration screen.

Features:
  - BLE device scanner with signal strength display
  - Connect / disconnect controls
  - Alert threshold sliders (temp, smoke, water)
  - Callsign editor
  - Export chat log to CSV
  - Export telemetry log to CSV
  - Save thresholds to dashboard
"""

import os
import csv
import time
from kivy.uix.screenmanager import Screen
from kivy.properties import (
    StringProperty, ListProperty, BooleanProperty, NumericProperty
)
from kivy.clock import Clock
from kivy.factory import Factory


class SettingsScreen(Screen):
    """BLE device management and configuration."""

    ble_status      = StringProperty("DISCONNECTED")
    scanned_devices = ListProperty([])        # list of dicts
    scanning        = BooleanProperty(False)
    scanned         = BooleanProperty(False)
    connected_addr  = StringProperty("")
    selected_addr   = StringProperty("")
    selected_name   = StringProperty("")

    # Thresholds (editable)
    temp_threshold  = NumericProperty(40.0)
    smoke_threshold = NumericProperty(2000)
    water_threshold = NumericProperty(3000)

    status_msg = StringProperty("")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_enter(self):
        if self.app:
            # Mirror current BLE status
            self.ble_status = self.app.ble_status
            # Hook status callback so UI updates live
            _orig_status = self.app.ble_manager._on_status
            def _patched_status(s):
                _orig_status(s)
                Clock.schedule_once(lambda dt: setattr(self, 'ble_status', s), 0)
            self.app.ble_manager._on_status = _patched_status

    # ── BLE actions ───────────────────────────────────────────────────────────

    def start_scan(self):
        if not self.app:
            return
        self.scanning = True
        self.scanned  = False
        self.scanned_devices = []
        self._clear_device_list()
        self.status_msg = "Scanning…"
        self.app.scan_ble(self._on_scan_result)

    def _on_scan_result(self, devices: list):
        Clock.schedule_once(lambda dt: self._update_devices(devices), 0)

    def _update_devices(self, devices: list):
        self.scanned_devices = devices
        self.scanning = False
        self.scanned  = True
        self.status_msg = f"Found {len(devices)} device(s)"
        self._build_device_list(devices)

    def _clear_device_list(self):
        if hasattr(self.ids, 'device_list'):
            # keep first child (status label)
            children = list(self.ids.device_list.children)
            for c in children[:-1]:   # remove all except last (label)
                self.ids.device_list.remove_widget(c)

    def _build_device_list(self, devices: list):
        if not hasattr(self.ids, 'device_list'):
            return
        self._clear_device_list()
        for d in devices:
            addr = d.get('address', '')
            name = d.get('name', '(Unknown)')
            rssi = d.get('rssi', -99)
            row  = Factory.DeviceRow(addr=addr, name=name, rssi=rssi)
            row.bind(on_touch_down=lambda inst, touch, a=addr, n=name:
                     self.select_device(a, n) if inst.collide_point(*touch.pos) else None)
            # Add a tap-to-select button inside the row
            from kivy.uix.button import Button
            btn = Button(
                text='SELECT',
                size_hint_x=0.18,
                font_size='9sp',
                bold=True,
                background_color=(0, 0, 0, 0),
                background_normal='',
                color=(0.1, 0.9, 0.5, 1),
            )
            btn.bind(on_press=lambda inst, a=addr, n=name: self.select_device(a, n))
            row.add_widget(btn)
            self.ids.device_list.add_widget(row)

    def select_device(self, addr: str, name: str):
        self.selected_addr = addr
        self.selected_name = name
        self.status_msg = f"Selected: {name}"

    def connect(self):
        if not self.selected_addr:
            self.status_msg = "Select a device first"
            return
        if self.app:
            self.status_msg = f"Connecting to {self.selected_name}…"
            self.app.connect_ble(self.selected_addr)

    def disconnect(self):
        if self.app:
            self.app.disconnect_ble()
            self.connected_addr = ""
            self.ble_status = "DISCONNECTED"
            self.status_msg = "Disconnected"

    # ── Data export ───────────────────────────────────────────────────────────

    def export_chat_csv(self):
        if not self.app:
            return
        msgs = self.app.message_store.get_messages(limit=10000)
        path = self._export_path('chat')
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=['id', 'sender', 'text', 'direction', 'ts', 'read'])
                w.writeheader()
                w.writerows(msgs)
            self.status_msg = f"✓ Chat exported → {os.path.basename(path)}"
        except Exception as exc:
            self.status_msg = f"Export failed: {exc}"

    def export_telemetry_csv(self):
        if not self.app:
            return
        rows = self.app.message_store.get_telemetry(limit=10000)
        path = self._export_path('telemetry')
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    w = csv.DictWriter(f, fieldnames=rows[0].keys())
                    w.writeheader()
                    w.writerows(rows)
            self.status_msg = f"✓ Telemetry exported → {os.path.basename(path)}"
        except Exception as exc:
            self.status_msg = f"Export failed: {exc}"

    def _export_path(self, prefix: str) -> str:
        """Return a writable export path (works on Android too)."""
        try:
            from android.storage import primary_external_storage_path
            base = os.path.join(primary_external_storage_path(), 'TacticalMesh')
        except ImportError:
            base = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'data'
            )
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f'{prefix}_{int(time.time())}.csv')

    # ── Threshold save ────────────────────────────────────────────────────────

    def save_thresholds(self):
        if self.app:
            dash = self.app.sm.get_screen('dashboard')
            dash.TEMP_ALERT  = self.temp_threshold
            dash.SMOKE_ALERT = self.smoke_threshold
            dash.WATER_ALERT = self.water_threshold
        self.status_msg = "✓ Thresholds saved"

    # ── Navigation ────────────────────────────────────────────────────────────

    def goto(self, screen_name: str):
        if self.app:
            self.app.sm.current = screen_name

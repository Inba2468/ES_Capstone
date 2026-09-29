"""
ui/screens/dashboard_screen.py
================================
Tactical telemetry dashboard.

Displays:
  - Animated circular gauges for Temperature, Humidity, Smoke, Water level
  - GPS coordinates and fix quality indicator
  - Node online/offline status list
  - BLE RSSI signal bar
  - Toast notification overlay
  - Live timestamp
  - Telemetry history sparklines (last 20 readings)
"""

import time
import math
from kivy.uix.screenmanager import Screen
from kivy.properties import (
    NumericProperty, StringProperty, ListProperty, BooleanProperty
)
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.utils import get_color_from_hex


class DashboardScreen(Screen):
    """Main telemetry overview screen."""

    # Telemetry properties (bound to KV widgets)
    temp        = NumericProperty(0.0)
    hum         = NumericProperty(0.0)
    smoke       = NumericProperty(0)
    water       = NumericProperty(0)
    lat         = NumericProperty(0.0)
    lng         = NumericProperty(0.0)
    gps_fix     = BooleanProperty(False)
    node_count  = NumericProperty(0)
    ble_status  = StringProperty("DISCONNECTED")
    ble_color   = ListProperty([1, 0.3, 0.3, 1])   # red
    timestamp   = StringProperty("--:--:--")
    toast_text  = StringProperty("")
    toast_alpha = NumericProperty(0)
    selected_node = StringProperty("GATEWAY")
    node_list     = ListProperty(["GATEWAY"])
    last_update   = StringProperty("No data yet")

    # Alert thresholds
    TEMP_ALERT  = 40.0
    SMOKE_ALERT = 2000
    WATER_ALERT = 3000

    def on_enter(self):
        Clock.schedule_interval(self._tick, 1.0)

    def on_leave(self):
        Clock.unschedule(self._tick)

    def _tick(self, dt):
        self.timestamp = time.strftime("%H:%M:%S")
        if hasattr(self, 'app') and self.app:
            nodes = list(self.app.node_tracker.nodes.keys())
            if set(nodes) != set(self.node_list):
                self.node_list = nodes
            self.node_count = len(nodes)
            
            # Auto-update if data changes silently
            if self.selected_node in self.app.node_tracker.nodes:
                n = self.app.node_tracker.get(self.selected_node)
                self.lat = n.lat
                self.lng = n.lng

    def select_node(self, node_id: str):
        self.selected_node = node_id
        if hasattr(self, 'app') and self.app:
            n = self.app.node_tracker.get(node_id)
            if n:
                self.temp = n.temp
                self.hum = n.hum
                self.smoke = n.smoke
                self.water = n.water
                self.lat = n.lat
                self.lng = n.lng
                self.gps_fix = (n.lat != 0.0 or n.lng != 0.0)

    # ── Telemetry update (called from main.py) ────────────────────────────────

    def update_telemetry(self, event: dict):
        """Animate gauge values to new readings."""
        event_node = event.get('node_id', 'GATEWAY')
        if event_node != self.selected_node:
            return

        target_temp  = event.get('temp',  self.temp)
        target_hum   = event.get('hum',   self.hum)
        target_smoke = event.get('smoke', self.smoke)
        target_water = event.get('water', self.water)

        Animation(temp=target_temp,   duration=0.8, t='out_cubic').start(self)
        Animation(hum=target_hum,     duration=0.8, t='out_cubic').start(self)
        Animation(smoke=target_smoke, duration=0.8, t='out_cubic').start(self)
        Animation(water=target_water, duration=0.8, t='out_cubic').start(self)

        self.lat     = event.get('lat', self.lat)
        self.lng     = event.get('lng', self.lng)
        self.gps_fix = (self.lat != 0.0 or self.lng != 0.0)
        self.last_update = time.strftime("%H:%M:%S")

        # Trigger alerts
        self._check_alerts(target_temp, target_smoke, target_water)

    def _check_alerts(self, temp, smoke, water):
        alerts = []
        if temp > self.TEMP_ALERT:
            alerts.append(f"⚠ HIGH TEMP: {temp:.1f}°C")
        if smoke > self.SMOKE_ALERT:
            alerts.append("🔥 SMOKE DETECTED")
        if water > self.WATER_ALERT:
            alerts.append("💧 HIGH WATER LEVEL")
        if alerts:
            self.show_toast("  |  ".join(alerts), duration=4.0)

    # ── BLE status update ─────────────────────────────────────────────────────

    def set_ble_status(self, status: str):
        self.ble_status = status
        if "CONNECTED" in status and "DIS" not in status:
            self.ble_color = [0.2, 1.0, 0.4, 1]   # green
        elif "SCAN" in status:
            self.ble_color = [1.0, 0.8, 0.0, 1]   # yellow
        else:
            self.ble_color = [1.0, 0.3, 0.3, 1]   # red

    # ── Toast ─────────────────────────────────────────────────────────────────

    def show_toast(self, text: str, duration: float = 2.5):
        self.toast_text = text
        anim = Animation(toast_alpha=1, duration=0.3) + \
               Animation(toast_alpha=1, duration=duration) + \
               Animation(toast_alpha=0, duration=0.5)
        anim.start(self)

    # ── Navigation helpers ────────────────────────────────────────────────────

    def goto(self, screen_name: str):
        if self.app:
            self.app.sm.current = screen_name

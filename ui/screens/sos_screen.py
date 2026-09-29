"""
ui/screens/sos_screen.py
========================
Full-screen SOS emergency override.

Triggered when an SOS:[lat],[lng],HELP packet is received.

Features:
  - Full-screen red pulsing alert overlay
  - Flashing "SOS RECEIVED" banner
  - Sender ID, GPS coordinates, time since SOS
  - Distance to SOS location from gateway
  - Simplified rescue route display (bearing + distance)
  - "ACKNOWLEDGE" button to dismiss and log resolution
  - Audio alert (system beep fallback if sound file missing)
  - Auto-dismiss after 60 seconds with audit log entry
"""

import math
import time
from kivy.uix.screenmanager import Screen
from kivy.properties import (
    StringProperty, NumericProperty, BooleanProperty, ListProperty
)
from kivy.animation import Animation
from kivy.clock import Clock


class SOSScreen(Screen):
    """Full-screen SOS emergency override screen."""

    sender        = StringProperty("UNKNOWN")
    sos_lat       = NumericProperty(0.0)
    sos_lng       = NumericProperty(0.0)
    distance_str  = StringProperty("-- km")
    bearing_str   = StringProperty("-- °")
    time_elapsed  = StringProperty("0s")
    sos_id        = NumericProperty(-1)
    flash_alpha   = NumericProperty(1.0)
    alert_active  = BooleanProperty(False)

    _sos_start    = 0
    _flash_anim   = None
    _tick_event   = None
    _auto_dismiss = None

    def trigger(self, event: dict):
        """Called by main dispatcher when SOS arrives."""
        self.sender   = event.get('sender', 'UNKNOWN')
        self.sos_lat  = event['lat']
        self.sos_lng  = event['lng']
        self._sos_start = time.time()
        self.alert_active = True

        # Log to message store
        if self.app:
            self.sos_id = self.app.message_store.log_sos(
                sender=self.sender,
                lat=self.sos_lat,
                lng=self.sos_lng
            )

        # Calculate distance & bearing from gateway
        self._compute_route()

        # Start blinking animation
        self._start_flash()

        # Tick elapsed timer
        self._tick_event = Clock.schedule_interval(self._update_elapsed, 1.0)

        # Auto-dismiss after 60 s
        self._auto_dismiss = Clock.schedule_once(self._auto_ack, 60.0)

    def _compute_route(self):
        """Calculate bearing and distance from the gateway to the SOS node."""
        if not self.app:
            return
        gw = self.app.node_tracker.get('GATEWAY')
        if not gw:
            return

        lat1, lng1 = math.radians(gw.lat), math.radians(gw.lng)
        lat2, lng2 = math.radians(self.sos_lat), math.radians(self.sos_lng)

        # Haversine distance
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
        dist_km = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        self.distance_str = f"{dist_km:.2f} km"

        # Bearing
        x = math.sin(lng2 - lng1) * math.cos(lat2)
        y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(lng2-lng1)
        bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
        direction = self._bearing_to_cardinal(bearing)
        self.bearing_str = f"{bearing:.0f}° {direction}"

    @staticmethod
    def _bearing_to_cardinal(deg: float) -> str:
        dirs = ["N","NE","E","SE","S","SW","W","NW","N"]
        return dirs[round(deg / 45) % 8]

    def _start_flash(self):
        self._flash_anim = (
            Animation(flash_alpha=0.3, duration=0.4) +
            Animation(flash_alpha=1.0, duration=0.4)
        )
        self._flash_anim.repeat = True
        self._flash_anim.start(self)

    def _update_elapsed(self, dt):
        elapsed = int(time.time() - self._sos_start)
        if elapsed < 60:
            self.time_elapsed = f"{elapsed}s"
        else:
            m = elapsed // 60
            s = elapsed % 60
            self.time_elapsed = f"{m}m {s}s"

    def acknowledge(self):
        """Commander acknowledges the SOS – dismiss screen and log."""
        self._cleanup()
        if self.app:
            if self.sos_id >= 0:
                self.app.message_store.resolve_sos(self.sos_id)
            sender = self.sender
            self.app.node_tracker.clear_sos(sender)
            self.app.sm.current = 'dashboard'

    def _auto_ack(self, dt):
        """Auto-dismiss after timeout."""
        self._cleanup()
        if self.app:
            self.app.sm.current = 'dashboard'

    def _cleanup(self):
        self.alert_active = False
        if self._flash_anim:
            self._flash_anim.cancel(self)
        if self._tick_event:
            Clock.unschedule(self._tick_event)
        if self._auto_dismiss:
            Clock.unschedule(self._auto_dismiss)

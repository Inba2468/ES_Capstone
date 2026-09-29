"""
tests/mock_ble_device.py
========================
Simulates an ESP32 BLE gateway feeding data to the app.

Usage (two modes):
  1.  Direct injection into the running app (import and call inject())
  2.  Standalone mode: python tests/mock_ble_device.py
       → prints sample BLE strings to stdout

Scenarios simulated:
  - Periodic SYS telemetry (every 2 s)
  - Chat messages (every 8 s)
  - SOS event (triggered once after 20 s)
  - Node position drift (GPS wander simulation)
"""

import time
import random
import math
import threading
from typing import Callable, Optional

# Chennai coordinates
BASE_LAT = 13.0827
BASE_LNG = 80.2707


class MockBLEDevice:
    """
    Produces realistic ESP32 BLE output strings for development testing.

    Parameters
    ----------
    callback : Callable[[str], None]
        The same callback as BLEManager expects – receives raw string payloads.
    """

    CHAT_MESSAGES = [
        "NODE-2:Sector 4 clear, moving north.",
        "NODE-2:Copy that. Heading to extraction point.",
        "NODE-3:We have movement on the east flank.",
        "NODE-2:Requesting status update.",
        "NODE-3:All sensors nominal. Water level rising.",
        "NODE-2:Temperature spike detected at junction.",
        "NODE-3:Route to waypoint A is compromised.",
        "NODE-2:Acknowledged. Using alternate path.",
    ]

    def __init__(self, callback: Callable[[str], None]):
        self._cb = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._t = 0.0
        self._sos_fired = False
        self._chat_idx = 0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[MOCK] Mock BLE device started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            self._t += 2.0

            # ── SYS telemetry ─────────────────────────────────────────────
            lat = BASE_LAT + 0.001 * math.sin(self._t / 10)
            lng = BASE_LNG + 0.001 * math.cos(self._t / 10)
            temp  = 28.0 + 6 * math.sin(self._t / 20) + random.gauss(0, 0.3)
            hum   = 65.0 + 10 * math.cos(self._t / 30) + random.gauss(0, 1)
            smoke = int(200 + 100 * abs(math.sin(self._t / 15)) + random.randint(0, 50))
            water = int(500 + 200 * abs(math.cos(self._t / 25)) + random.randint(0, 80))

            sys_str = f"SYS:{lat:.5f},{lng:.5f},{temp:.1f},{hum:.1f},{smoke},{water}"
            self._cb(sys_str)
            print(f"[MOCK -> SYS] {sys_str}")

            # ── Chat (every 4 ticks = 8 s) ────────────────────────────────
            if int(self._t) % 8 == 0:
                msg = self.CHAT_MESSAGES[self._chat_idx % len(self.CHAT_MESSAGES)]
                chat_str = f"CHAT:{msg}"
                self._cb(chat_str)
                print(f"[MOCK -> CHAT] {chat_str}")
                self._chat_idx += 1

            # ── SOS (single event after 20 s) ─────────────────────────────
            if self._t >= 20 and not self._sos_fired:
                self._sos_fired = True
                sos_lat = BASE_LAT + random.uniform(-0.005, 0.005)
                sos_lng = BASE_LNG + random.uniform(-0.005, 0.005)
                sos_str = f"SOS:{sos_lat:.5f},{sos_lng:.5f},HELP:NODE-3"
                self._cb(sos_str)
                print(f"[MOCK -> SOS] {sos_str}")

            # ── Smoke spike alert (after 40 s) ────────────────────────────
            if int(self._t) == 40:
                spike = f"SYS:{lat:.5f},{lng:.5f},{temp:.1f},{hum:.1f},3500,800"
                self._cb(spike)
                print(f"[MOCK -> SPIKE] {spike}")

            time.sleep(2.0)

    def inject(self, raw: str):
        """Manually inject a raw BLE string."""
        self._cb(raw)
        print(f"[MOCK -> INJECT] {raw}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    def print_cb(s):
        pass  # already printed inside loop

    dev = MockBLEDevice(callback=print_cb)
    dev.start()

    print("Mock BLE device running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dev.stop()
        print("Stopped.")

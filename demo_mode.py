"""
demo_mode.py
============
Run the app in DEMO MODE with a simulated ESP32 BLE device.
No real Bluetooth hardware required.

Usage:
    python demo_mode.py

This patches main.py's BLEManager with MockBLEDevice so you can
test all features (gauges, chat, SOS, map) with synthetic data.
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.mock_ble_device import MockBLEDevice

# Monkey-patch BLEManager before the app starts
import core.ble_manager as _ble_mod

class DemoBLEManager:
    """Drop-in replacement that uses MockBLEDevice instead of real BLE."""

    def __init__(self, on_data, on_status=None):
        self._mock = MockBLEDevice(callback=on_data)
        self._on_status = on_status or (lambda s: None)
        self.is_connected = True

    async def connect(self, address):
        self._on_status("✅  DEMO MODE – SIMULATED CONNECTION")
        self._mock.start()

    async def disconnect(self):
        self._mock.stop()
        self.is_connected = False

    async def scan(self, callback, duration=5.0):
        import asyncio
        self._on_status("SCANNING (demo)…")
        await asyncio.sleep(1.5)
        callback([
            {'name': 'ESP32-MESH-GW', 'address': 'AA:BB:CC:DD:EE:FF', 'rssi': -52},
            {'name': 'NODE-2',        'address': 'AA:BB:CC:DD:EE:01', 'rssi': -68},
            {'name': 'NODE-3',        'address': 'AA:BB:CC:DD:EE:02', 'rssi': -74},
        ])

    async def send(self, text):
        print(f"[DEMO TX → ESP32] {text}")


_ble_mod.BLEManager = DemoBLEManager

# Now import and run the app
if __name__ == '__main__':
    import asyncio
    from main import TacticalApp

    app = TacticalApp()

    # Auto-start the mock device after app boots
    from kivy.clock import Clock

    def _auto_connect(dt):
        app.connect_ble('AA:BB:CC:DD:EE:FF')

    Clock.schedule_once(_auto_connect, 4.0)

    app.run()

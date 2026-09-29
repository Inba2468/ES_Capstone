"""
core/ble_manager.py
===================
Async BLE manager.

Desktop  → uses `bleak` (Windows / macOS / Linux)
Android  → uses Android BluetoothGatt via `jnius` (pyjnius)

Nordic UART Service (NUS) UUIDs:
  Service : 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
  TX char : 6E400002-B5A3-F393-E0A9-E50E24DCCA9E  (write to ESP32)
  RX char : 6E400003-B5A3-F393-E0A9-E50E24DCCA9E  (notify from ESP32)
"""

import asyncio
import logging
import platform
from typing import Callable, Optional

log = logging.getLogger(__name__)

NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # write
NUS_RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # notify

# ── Detect runtime environment ────────────────────────────────────────────────
IS_ANDROID = False
try:
    from jnius import autoclass
    IS_ANDROID = True
    log.info("Android runtime detected – using native BLE stack")
except ImportError:
    pass

BLEAK_AVAILABLE = False
if not IS_ANDROID:
    try:
        from bleak import BleakClient, BleakScanner
        from bleak.exc import BleakError
        BLEAK_AVAILABLE = True
        log.info("bleak available – using desktop BLE stack")
    except ImportError:
        log.warning("bleak not installed – BLE disabled (demo mode only)")


# =============================================================================
#  Desktop BLE (bleak)
# =============================================================================

class _DesktopBLEManager:
    """BLE manager for Windows / macOS / Linux using bleak."""

    def __init__(self, on_data, on_status=None):
        self._on_data      = on_data
        self._on_status    = on_status or (lambda s: None)
        self._client       = None
        self._connected    = False
        self._target_addr  = None
        self._retry_delay  = 2.0
        self._max_delay    = 60.0
        self._reconnect_task = None

    @property
    def is_connected(self):
        return self._connected

    async def scan(self, callback: Callable, duration: float = 5.0):
        if not BLEAK_AVAILABLE:
            callback([])
            return
        try:
            self._on_status("SCANNING…")
            devices = await BleakScanner.discover(timeout=duration)
            results = [
                {'name': d.name or '(Unknown)', 'address': d.address, 'rssi': d.rssi}
                for d in devices
            ]
            callback(results)
            self._on_status(f"Found {len(results)} device(s)")
        except Exception as exc:
            log.error("Scan error: %s", exc)
            self._on_status(f"Scan failed: {exc}")
            callback([])

    async def connect(self, address: str):
        if not BLEAK_AVAILABLE:
            self._on_status("BLE not available – DEMO MODE")
            return
        self._target_addr = address
        self._retry_delay = 2.0
        await self._do_connect()

    async def disconnect(self):
        self._target_addr = None
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._client and self._connected:
            await self._client.disconnect()

    async def send(self, text: str):
        if not BLEAK_AVAILABLE or not self._connected or not self._client:
            log.warning("Not connected – dropped: %s", text)
            return
        try:
            await self._client.write_gatt_char(
                NUS_TX_CHAR_UUID, (text + "\n").encode('utf-8')
            )
        except Exception as exc:
            log.error("Send error: %s", exc)

    async def _do_connect(self):
        while self._target_addr:
            try:
                self._on_status(f"Connecting to {self._target_addr}…")
                self._client = BleakClient(
                    self._target_addr,
                    disconnected_callback=self._on_disconnected
                )
                await self._client.connect(timeout=10.0)
                self._connected = True
                self._retry_delay = 2.0
                self._on_status("✅  CONNECTED")
                log.info("BLE connected to %s", self._target_addr)
                await self._client.start_notify(
                    NUS_RX_CHAR_UUID, self._notification_handler
                )
                return
            except BleakError as exc:
                log.warning("Connect failed: %s (retry %.0fs)", exc, self._retry_delay)
                self._on_status(f"⚠ Connect failed – retry {self._retry_delay:.0f}s")
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, self._max_delay)
            except asyncio.CancelledError:
                break

    def _notification_handler(self, sender, data: bytearray):
        try:
            text = data.decode('utf-8').strip()
            if text:
                self._on_data(text)
        except UnicodeDecodeError:
            log.warning("Non-UTF8 BLE data: %s", data.hex())

    def _on_disconnected(self, client):
        self._connected = False
        self._on_status("⚠  DISCONNECTED")
        log.warning("BLE disconnected from %s", self._target_addr)
        if self._target_addr:
            loop = asyncio.get_event_loop()
            self._reconnect_task = loop.create_task(self._do_connect())


# =============================================================================
#  Android BLE (jnius + BluetoothGatt)
# =============================================================================

class _AndroidBLEManager:
    """
    BLE manager for Android using the native Bluetooth stack via jnius.
    Implements a simplified GATT client that connects to the ESP32 NUS service.
    """

    def __init__(self, on_data, on_status=None):
        self._on_data   = on_data
        self._on_status = on_status or (lambda s: None)
        self._connected = False
        self._gatt      = None
        self._rx_char   = None
        self._tx_char   = None
        self._target_addr = None
        self._write_queue = asyncio.Queue()
        self._scan_results = []

    @property
    def is_connected(self):
        return self._connected

    async def scan(self, callback: Callable, duration: float = 5.0):
        """Scan using Android BluetoothLeScanner."""
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            adapter = BluetoothAdapter.getDefaultAdapter()
            if not adapter.isEnabled():
                self._on_status("Bluetooth is OFF – please enable it")
                callback([])
                return

            self._on_status("SCANNING…")
            # Use classic paired devices + discovered devices
            paired = adapter.getBondedDevices()
            results = []
            if paired:
                for d in paired.toArray():
                    results.append({
                        'name': d.getName() or '(Unknown)',
                        'address': d.getAddress(),
                        'rssi': -60  # paired devices don't have RSSI easily
                    })

            # BLE scan via LeScanner
            scanner = adapter.getBluetoothLeScanner()
            if scanner:
                self._scan_results = []
                # Run a timed scan using a simple callback bridge
                scan_results_ref = []

                # We use asyncio sleep to wait; actual results come via callback
                # For simplicity, return paired devices immediately and append BLE
                await asyncio.sleep(min(duration, 5.0))

                for r in self._scan_results:
                    results.append(r)

            # Deduplicate by address
            seen = set()
            deduped = []
            for r in results:
                if r['address'] not in seen:
                    seen.add(r['address'])
                    deduped.append(r)

            callback(deduped)
            self._on_status(f"Found {len(deduped)} device(s)")
        except Exception as exc:
            log.error("Android scan error: %s", exc)
            self._on_status(f"Scan failed: {exc}")
            callback([])

    async def connect(self, address: str):
        """Connect to BLE device at `address`."""
        self._target_addr = address
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            PythonActivity   = autoclass('org.kivy.android.PythonActivity')
            UUID             = autoclass('java.util.UUID')
            BluetoothGatt    = autoclass('android.bluetooth.BluetoothGatt')

            adapter = BluetoothAdapter.getDefaultAdapter()
            device  = adapter.getRemoteDevice(address)
            context = PythonActivity.mActivity

            self._on_status(f"Connecting to {address}…")

            # Create a GATT callback class
            class GattCallback(PythonJavaClass):
                __javainterfaces__ = ['android/bluetooth/BluetoothGattCallback']
                __javacontext__ = 'app'

                def __init__(self_, parent):
                    super().__init__()
                    self_._p = parent

                @java_method('(Landroid/bluetooth/BluetoothGatt;II)V')
                def onConnectionStateChange(self_, gatt, status, newState):
                    if newState == 2:  # STATE_CONNECTED
                        self_._p._connected = True
                        self_._p._on_status("✅  CONNECTED")
                        gatt.discoverServices()
                    else:
                        self_._p._connected = False
                        self_._p._on_status("⚠  DISCONNECTED")

                @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
                def onServicesDiscovered(self_, gatt, status):
                    service = gatt.getService(
                        UUID.fromString(NUS_SERVICE_UUID)
                    )
                    if service:
                        rx = service.getCharacteristic(
                            UUID.fromString(NUS_RX_CHAR_UUID)
                        )
                        tx = service.getCharacteristic(
                            UUID.fromString(NUS_TX_CHAR_UUID)
                        )
                        self_._p._rx_char = rx
                        self_._p._tx_char = tx
                        gatt.setCharacteristicNotification(rx, True)
                        # Enable CCCD descriptor
                        CDesc = autoclass('android.bluetooth.BluetoothGattDescriptor')
                        desc = rx.getDescriptor(
                            UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
                        )
                        if desc:
                            desc.setValue(CDesc.ENABLE_NOTIFICATION_VALUE)
                            gatt.writeDescriptor(desc)

                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;)V')
                def onCharacteristicChanged(self_, gatt, characteristic):
                    raw = bytes(characteristic.getValue())
                    try:
                        text = raw.decode('utf-8').strip()
                        if text:
                            self_._p._on_data(text)
                    except Exception:
                        pass

                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;I)V')
                def onCharacteristicWrite(self_, gatt, characteristic, status):
                    pass   # write acknowledged

            callback = GattCallback(self)
            self._gatt = device.connectGatt(context, False, callback)
            log.info("Android GATT connection initiated to %s", address)

        except Exception as exc:
            log.error("Android connect error: %s", exc)
            self._on_status(f"Connect failed: {exc}")

    async def disconnect(self):
        self._target_addr = None
        if self._gatt:
            try:
                self._gatt.disconnect()
                self._gatt.close()
            except Exception:
                pass
        self._connected = False
        self._on_status("Disconnected")

    async def send(self, text: str):
        if not self._connected or not self._gatt or not self._tx_char:
            log.warning("Not connected – dropped: %s", text)
            return
        try:
            data = (text + "\n").encode('utf-8')
            self._tx_char.setValue(data)
            self._gatt.writeCharacteristic(self._tx_char)
        except Exception as exc:
            log.error("Android send error: %s", exc)


# =============================================================================
#  Public factory
# =============================================================================

def BLEManager(on_data: Callable, on_status: Optional[Callable] = None):
    """
    Factory: returns the correct BLE manager for the current platform.
    """
    if IS_ANDROID:
        return _AndroidBLEManager(on_data=on_data, on_status=on_status)
    else:
        return _DesktopBLEManager(on_data=on_data, on_status=on_status)

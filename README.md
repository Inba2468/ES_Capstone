# Tactical Off-Grid Mesh Network
### LoRa 433MHz + BLE Gateway  //  Python Kivy App

> **100% offline** · **ESP32 gateway** · **NEO-6M GPS** · **DHT22 · MQ Smoke · Water sensor**

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run in DEMO MODE (no hardware needed)
python demo_mode.py

# 3. Run with real ESP32 hardware
python main.py
```

---

## Project Structure

```
ES CAPSTONE/
├── main.py                   # App entry point
├── demo_mode.py              # Hardware-free demo launcher
├── requirements.txt
│
├── core/
│   ├── ble_manager.py        # Async BLE (bleak, Nordic UART)
│   ├── protocol_parser.py    # CHAT/SYS/SOS/PING parser
│   ├── message_store.py      # SQLite persistence
│   └── node_tracker.py       # Live node registry
│
├── ui/
│   ├── screens/
│   │   ├── boot_screen.py    # Animated splash
│   │   ├── dashboard_screen.py  # Telemetry gauges
│   │   ├── chat_screen.py    # Tactical messaging
│   │   ├── map_screen.py     # Offline MapView
│   │   ├── sos_screen.py     # SOS override
│   │   └── settings_screen.py   # BLE + config
│   └── kv/                   # Kivy layout files
│
├── data/
│   ├── maps/                 # Place .mbtiles here
│   └── mesh.db               # Auto-created SQLite DB
│
└── tests/
    ├── mock_ble_device.py    # ESP32 simulator
    └── test_parser.py        # Protocol unit tests
```

---

## Wire Protocol

| Prefix | Format | Description |
|--------|--------|-------------|
| `CHAT:` | `CHAT:[sender]:[msg]` | Routes to messaging UI |
| `SYS:` | `SYS:[lat],[lng],[°C],[%RH],[smoke],[water]` | Telemetry update |
| `SOS:` | `SOS:[lat],[lng],HELP[:sender]` | Full-screen emergency override |
| `PING:` | `PING:[node_id]` | Heartbeat |
| `ACK:` | `ACK:[msg_id]` | Delivery confirmation |
| `NODE:` | `NODE:[id],[lat],[lng]` | Position-only report |

---

## Hardware Wiring

| Component | ESP32 Pin |
|-----------|-----------|
| Ra-02 LoRa SCK | GPIO 18 |
| Ra-02 LoRa MISO | GPIO 19 |
| Ra-02 LoRa MOSI | GPIO 23 |
| Ra-02 LoRa CS | GPIO 5 |
| Ra-02 LoRa RST | GPIO 14 |
| Ra-02 LoRa IRQ | GPIO 2 |
| NEO-6M GPS TX | GPIO 16 (Serial2 RX) |
| NEO-6M GPS RX | GPIO 17 (Serial2 TX) |
| DHT22 | GPIO 27 |
| Water Sensor | GPIO 32 (ADC) |
| MQ Smoke | GPIO 33 (ADC) |

---

## Offline Maps

1. Download `.mbtiles` for your region from [maptiler.com](https://maptiler.com) or OpenMapTiles
2. Place the file in `data/maps/`
3. Set the tile source in Settings → Map Source

---

## BLE UUIDs (Nordic UART Service)

```
Service : 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
TX Char : 6E400002-B5A3-F393-E0A9-E50E24DCCA9E  (write to ESP32)
RX Char : 6E400003-B5A3-F393-E0A9-E50E24DCCA9E  (notify from ESP32)
```

---

## Run Tests

```bash
python tests/test_parser.py
```

---

## Features

- ✅ Full-screen SOS override with bearing + distance calculation
- ✅ Animated circular telemetry gauges (Temp/Hum/Smoke/Water)
- ✅ Tactical dark theme with military-grade UI
- ✅ BLE auto-reconnect with exponential back-off
- ✅ SQLite message + SOS + telemetry history
- ✅ Quick-reply tactical phrases
- ✅ Offline map with live node pins (kivy-garden.mapview)
- ✅ Alert threshold sliders (configurable)
- ✅ CSV export for chat and telemetry logs
- ✅ Demo mode (no ESP32 required)
- ✅ Protocol parser unit tests

"""
web/server.py
=============
FastAPI + WebSocket backend for the Tactical Mesh Web Dashboard.

- Supports DEMO MODE (MockBLEDevice) & REAL HARDWARE MODE (Bleak BLE / ESP32)
- BLE Device Scanning and Live Pairing to Nordic UART ESP32 nodes
- Pushes all parsed events to connected browser clients via WebSocket
- Handles Decentralized Chat, Tactical SOS strobe alerts, and Shelter broadcasts
- Persists data to SQLite3 database via MessageStore
- Serves the single-page Stitch HUD frontend at /
"""

import sys
import os
import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Optional

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.protocol_parser import ProtocolParser
from core.message_store import MessageStore
from core.node_tracker import NodeTracker
from tests.mock_ble_device import MockBLEDevice

# Optional Bleak import for physical ESP32 BLE
BLEAK_AVAILABLE = False
try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    pass

# Nordic UART Service (NUS) UUIDs for ESP32
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # Write to ESP32
NUS_RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"   # Notify from ESP32

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Tactical Mesh Web Dashboard & Hardware Gateway")

parser = ProtocolParser()
message_store = MessageStore()
node_tracker = NodeTracker()

# All connected WebSocket clients
clients: list[WebSocket] = []
clients_lock = asyncio.Lock()

# Hardware & Demo state
mode = "DEMO"  # "DEMO" or "HARDWARE_BLE"
mock_device: Optional[MockBLEDevice] = None
ble_client: Optional[object] = None
ble_connected_device: Optional[str] = None
ble_scanning: bool = False
event_loop: Optional[asyncio.AbstractEventLoop] = None

# Global state sent to newly connected clients
state = {
    "type": "state",
    "mode": "DEMO",
    "ble_status": "DEMO ACTIVE",
    "ble_device_name": None,
    "ble_device_address": None,
    "bleak_available": BLEAK_AVAILABLE,
    "gps_fix": True,
    "callsign": "OPERATOR-1",
    "telemetry": {
        "lat": 13.0827,
        "lng": 80.2707,
        "temp": 28.0,
        "hum": 65.0,
        "smoke": 240,
        "water": 520,
    },
    "nodes": {},
    "waypoints": [
        {"name": "HQ COMMAND", "lat": 13.0827, "lng": 80.2707, "type": "BASE"},
        {"name": "ALPHA OUTPOST", "lat": 13.0850, "lng": 80.2730, "type": "OUTPOST"},
    ],
    "messages": [],
    "rssi": -82,
    "snr": 9.4,
    "pkt_count": 0,
}


# ── WebSocket broadcast ───────────────────────────────────────────────────────

async def _broadcast(payload: dict):
    """Send JSON to all connected clients."""
    data = json.dumps(payload)
    async with clients_lock:
        dead = []
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in clients:
                clients.remove(ws)


def broadcast_sync(payload: dict):
    """Thread-safe bridge: called from threads or BLE callbacks."""
    if event_loop and not event_loop.is_closed():
        asyncio.run_coroutine_threadsafe(_broadcast(payload), event_loop)


# ── Packet & Event Pipeline ───────────────────────────────────────────────────

def on_incoming_packet(raw: str):
    """Called for every incoming packet from either MockBLE or real ESP32 BLE."""
    raw = raw.strip()
    if not raw:
        return
    
    event = parser.parse(raw)
    if not event:
        return

    etype = event.get("type")
    state["pkt_count"] += 1

    if etype == "SYS":
        message_store.log_telemetry(event)
        node_tracker.update(event)
        state["telemetry"] = {
            "lat": event.get("lat", 13.0827),
            "lng": event.get("lng", 80.2707),
            "temp": event.get("temp", 28.0),
            "hum": event.get("hum", 65.0),
            "smoke": event.get("smoke", 0),
            "water": event.get("water", 0),
        }
        state["gps_fix"] = True
        state["nodes"] = {k: v.__dict__ if hasattr(v, '__dict__') else v
                          for k, v in node_tracker.nodes.items()}
        
        if mode == "DEMO":
            import random, math
            state["rssi"] = int(-82 + 8 * math.sin(time.time() / 15) + random.randint(-3, 3))
            state["snr"] = round(9.4 + 2 * math.cos(time.time() / 20) + random.uniform(-0.5, 0.5), 1)

        broadcast_sync({
            "type": "sys",
            "telemetry": state["telemetry"],
            "nodes": state["nodes"],
            "pkt_count": state["pkt_count"],
            "rssi": state["rssi"],
            "snr": state["snr"],
            "raw": raw,
        })

    elif etype == "CHAT":
        sender = event.get("sender", "NODE")
        text = event.get("text", "")
        message_store.add_message(sender=sender, text=text, direction="in")
        msg = {
            "sender": sender,
            "text": text,
            "direction": "in",
            "ts": time.strftime("%H:%M:%S"),
        }
        state["messages"].append(msg)
        if len(state["messages"]) > 200:
            state["messages"] = state["messages"][-200:]
        broadcast_sync({"type": "chat", "message": msg, "raw": raw})

    elif etype == "SOS":
        node_tracker.update_sos(event)
        sos_payload = {
            "type": "sos",
            "sender": event.get("sender", "UNKNOWN"),
            "lat": event.get("lat", state["telemetry"].get("lat", 0.0)),
            "lng": event.get("lng", state["telemetry"].get("lng", 0.0)),
            "raw": raw,
        }
        broadcast_sync(sos_payload)

    elif etype in ("PING", "NODE"):
        node_tracker.update(event)
        state["nodes"] = {k: v.__dict__ if hasattr(v, '__dict__') else v
                          for k, v in node_tracker.nodes.items()}
        broadcast_sync({"type": "node_update", "nodes": state["nodes"], "raw": raw})

    elif etype == "WAYPOINT":
        wp = {
            "name": event.get("name", "WAYPOINT"),
            "lat": event.get("lat", state["telemetry"].get("lat", 0.0)),
            "lng": event.get("lng", state["telemetry"].get("lng", 0.0)),
            "type": event.get("wp_type", "SHELTER"),
        }
        state["waypoints"].append(wp)
        broadcast_sync({"type": "waypoint", "waypoint": wp, "waypoints": state["waypoints"], "raw": raw})


# ── Real ESP32 BLE Hardware Management ────────────────────────────────────────

def _ble_notification_handler(sender, data: bytearray):
    """Callback when ESP32 sends a packet over BLE notify characteristic."""
    try:
        text = data.decode("utf-8", errors="ignore")
        print(f"[BLE RX <- ESP32] {text}")
        on_incoming_packet(text)
    except Exception as e:
        print(f"[BLE RX ERROR] {e}")


async def transmit_to_hardware(raw_proto: str):
    """Send a raw protocol string to the ESP32 (via BLE or console if in demo)."""
    global ble_client
    if mode == "HARDWARE_BLE" and ble_client and getattr(ble_client, 'is_connected', False):
        try:
            data = (raw_proto + "\n").encode("utf-8")
            await ble_client.write_gatt_char(NUS_TX_CHAR_UUID, data, response=False)
            print(f"[BLE TX -> ESP32] {raw_proto}")
        except Exception as e:
            print(f"[BLE TX ERROR] {e}")
    else:
        print(f"[{mode} TX] {raw_proto}")


def start_demo_mode():
    """Start mock BLE background thread."""
    global mock_device, mode
    mode = "DEMO"
    state["mode"] = "DEMO"
    state["ble_status"] = "DEMO ACTIVE"
    if mock_device is None or not mock_device._running:
        mock_device = MockBLEDevice(callback=on_incoming_packet)
        mock_device.start()
    broadcast_sync({
        "type": "mode_change",
        "mode": "DEMO",
        "ble_status": "DEMO ACTIVE",
    })
    print("[SERVER] Demo Mode Started")


def stop_demo_mode():
    """Stop mock BLE background thread."""
    global mock_device
    if mock_device and mock_device._running:
        mock_device.stop()
        mock_device = None
    state["ble_status"] = "DEMO STOPPED"
    broadcast_sync({
        "type": "mode_change",
        "mode": mode,
        "ble_status": "DEMO STOPPED",
    })
    print("[SERVER] Demo Mode Stopped")


async def connect_ble_device(address: str, name: str = "ESP32"):
    """Connect to a physical ESP32 BLE device using Bleak."""
    global ble_client, ble_connected_device, mode
    if not BLEAK_AVAILABLE:
        return {"success": False, "error": "Bleak library not installed"}

    stop_demo_mode()
    mode = "HARDWARE_BLE"
    state["mode"] = "HARDWARE_BLE"
    state["ble_status"] = f"CONNECTING TO {name}…"
    broadcast_sync({"type": "ble_status", "status": state["ble_status"]})

    try:
        def on_disconnect(client):
            print(f"[BLE] Disconnected from {address}")
            state["ble_status"] = "DISCONNECTED"
            state["ble_device_name"] = None
            broadcast_sync({
                "type": "ble_status",
                "status": "DISCONNECTED",
                "connected": False
            })

        client = BleakClient(address, disconnected_callback=on_disconnect)
        await client.connect(timeout=10.0)
        
        # Start notification on RX characteristic
        try:
            await client.start_notify(NUS_RX_CHAR_UUID, _ble_notification_handler)
        except Exception as ex:
            print(f"[BLE] NUS characteristic notify warning: {ex}")

        ble_client = client
        ble_connected_device = address
        state["ble_status"] = f"CONNECTED: {name}"
        state["ble_device_name"] = name
        state["ble_device_address"] = address
        
        broadcast_sync({
            "type": "ble_status",
            "status": state["ble_status"],
            "connected": True,
            "device": {"name": name, "address": address}
        })
        print(f"[BLE] Successfully connected to ESP32: {name} ({address})")
        return {"success": True, "name": name, "address": address}

    except Exception as e:
        print(f"[BLE CONNECTION ERROR] {e}")
        state["ble_status"] = f"FAILED: {e}"
        broadcast_sync({"type": "ble_status", "status": state["ble_status"], "connected": False})
        return {"success": False, "error": str(e)}


# ── Server Lifespan ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global event_loop
    event_loop = asyncio.get_event_loop()
    start_demo_mode()
    print("[SERVER] Tactical Mesh Web Server started")
    print("[SERVER] Access UI at: http://localhost:8765")


@app.on_event("shutdown")
async def shutdown():
    stop_demo_mode()
    if ble_client and getattr(ble_client, 'is_connected', False):
        try:
            await ble_client.disconnect()
        except Exception:
            pass
    message_store.close()


# ── REST API Endpoints ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/state")
async def get_state():
    """Return full current state."""
    msgs = message_store.get_messages(limit=100)
    return {**state, "messages": msgs}


@app.post("/api/mode/demo/start")
async def api_start_demo():
    start_demo_mode()
    return {"status": "ok", "mode": "DEMO"}


@app.post("/api/mode/demo/stop")
async def api_stop_demo():
    stop_demo_mode()
    return {"status": "ok", "mode": mode}


@app.get("/api/ble/scan")
async def api_scan_ble():
    """Scan for nearby BLE devices."""
    if not BLEAK_AVAILABLE:
        return JSONResponse(
            status_code=501,
            content={"error": "Bleak is not installed on the system."}
        )
    try:
        devices = await BleakScanner.discover(timeout=5.0)
        results = [
            {
                "name": d.name or "(Unknown BLE Device)",
                "address": d.address,
                "rssi": getattr(d, 'rssi', None)
            }
            for d in devices
        ]
        return {"devices": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/ble/connect")
async def api_connect_ble(payload: dict):
    address = payload.get("address")
    name = payload.get("name", "ESP32-LoRa-Node")
    if not address:
        return JSONResponse(status_code=400, content={"error": "Address required"})
    res = await connect_ble_device(address, name)
    return res


@app.post("/api/ble/disconnect")
async def api_disconnect_ble():
    global ble_client, ble_connected_device
    if ble_client and getattr(ble_client, 'is_connected', False):
        await ble_client.disconnect()
        ble_client = None
        ble_connected_device = None
    state["ble_status"] = "DISCONNECTED"
    state["ble_device_name"] = None
    broadcast_sync({"type": "ble_status", "status": "DISCONNECTED", "connected": False})
    return {"status": "ok"}


# ── WebSocket Handler ─────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with clients_lock:
        clients.append(ws)

    # Send full current state on connect
    try:
        msgs = message_store.get_messages(limit=100)
        await ws.send_text(json.dumps({**state, "messages": msgs}))
    except Exception:
        pass

    try:
        while True:
            raw_text = await ws.receive_text()
            data = json.loads(raw_text)
            action = data.get("action")

            if action == "send_chat":
                text = data.get("text", "").strip()
                if text:
                    sender = state["callsign"]
                    message_store.add_message(sender=sender, text=text, direction="out")
                    msg = {
                        "sender": sender,
                        "text": text,
                        "direction": "out",
                        "ts": time.strftime("%H:%M:%S"),
                    }
                    state["messages"].append(msg)
                    raw_proto = f"CHAT:{sender}:{text}"
                    await _broadcast({"type": "chat", "message": msg, "raw": raw_proto})
                    await transmit_to_hardware(raw_proto)

            elif action == "send_sos":
                # Current GPS location or sensor lat/lng
                lat = float(data.get("lat") or state["telemetry"].get("lat", 13.0827))
                lng = float(data.get("lng") or state["telemetry"].get("lng", 80.2707))
                callsign = state["callsign"]
                raw_proto = f"SOS:{lat:.5f},{lng:.5f},HELP:{callsign}"
                
                # Broadcast SOS alert with strobe triggers
                sos_evt = {
                    "type": "sos",
                    "sender": callsign,
                    "lat": lat,
                    "lng": lng,
                    "ts": time.strftime("%H:%M:%S"),
                    "raw": raw_proto,
                }
                await _broadcast(sos_evt)
                await transmit_to_hardware(raw_proto)

            elif action == "dismiss_sos":
                await _broadcast({"type": "sos_dismiss"})

            elif action == "broadcast_shelter":
                lat = float(data.get("lat") or state["telemetry"].get("lat", 13.0827))
                lng = float(data.get("lng") or state["telemetry"].get("lng", 80.2707))
                shelter_name = data.get("name") or f"SHELTER-{int(time.time()) % 1000}"
                raw_proto = f"WAYPOINT:{lat:.5f},{lng:.5f},SHELTER:{shelter_name}"
                
                wp = {
                    "name": shelter_name,
                    "lat": lat,
                    "lng": lng,
                    "type": "SHELTER",
                    "ts": time.strftime("%H:%M:%S"),
                }
                state["waypoints"].append(wp)
                
                # Also log as a system message in chat
                sys_msg = {
                    "sender": "MESH-BROADCAST",
                    "text": f"🛡️ SHELTER DEPLOYED: {shelter_name} at ({lat:.4f}, {lng:.4f})",
                    "direction": "in",
                    "ts": time.strftime("%H:%M:%S"),
                }
                state["messages"].append(sys_msg)
                
                await _broadcast({
                    "type": "waypoint",
                    "waypoint": wp,
                    "waypoints": state["waypoints"],
                    "chat_message": sys_msg,
                    "raw": raw_proto,
                })
                await transmit_to_hardware(raw_proto)

            elif action == "set_callsign":
                state["callsign"] = data.get("callsign", state["callsign"]).upper()

            elif action == "start_demo":
                start_demo_mode()

            elif action == "stop_demo":
                stop_demo_mode()

            elif action == "scan_ble":
                if BLEAK_AVAILABLE:
                    try:
                        devices = await BleakScanner.discover(timeout=4.0)
                        res = [{"name": d.name or "(Unknown)", "address": d.address, "rssi": getattr(d, 'rssi', -90)}
                               for d in devices]
                        await ws.send_text(json.dumps({"type": "ble_scan_results", "devices": res}))
                    except Exception as e:
                        await ws.send_text(json.dumps({"type": "ble_scan_error", "error": str(e)}))
                else:
                    await ws.send_text(json.dumps({"type": "ble_scan_error", "error": "Bleak is not installed"}))

            elif action == "connect_ble":
                addr = data.get("address")
                name = data.get("name", "ESP32")
                if addr:
                    await connect_ble_device(addr, name)

            elif action == "disconnect_ble":
                if ble_client and getattr(ble_client, 'is_connected', False):
                    await ble_client.disconnect()
                state["ble_status"] = "DISCONNECTED"
                state["ble_device_name"] = None
                await _broadcast({"type": "ble_status", "status": "DISCONNECTED", "connected": False})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS ERROR] {e}")
    finally:
        async with clients_lock:
            if ws in clients:
                clients.remove(ws)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "web.server:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="warning",
    )

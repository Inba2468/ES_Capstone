"""
core/protocol_parser.py
=======================
Parses incoming Bluetooth strings from the ESP32 mesh gateway.

Supported protocols
───────────────────
  CHAT:[sender]:[msg]
      or
  CHAT:[msg]                  ← legacy single-field form

  SYS:[lat],[lng],[temp],[hum],[smoke],[water]
      where:
        lat   – float degrees
        lng   – float degrees
        temp  – float °C
        hum   – float %RH
        smoke – int ADC (0–4095)
        water – int ADC (0–4095)

  SOS:[lat],[lng],HELP
  SOS:[lat],[lng],HELP:[sender]   ← optional sender tag

Extra supported extensions (for future firmware):
  PING:[node_id]              ← heartbeat
  ACK:[msg_id]                ← delivery acknowledgement
  NODE:[node_id],[lat],[lng]  ← pure position report (no telemetry)
"""

import re
import time
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────────

_CHAT_RE  = re.compile(r'^CHAT:(?:([^:]+):)?(.+)$', re.IGNORECASE)
_SYS_RE   = re.compile(
    r'^SYS:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+)$',
    re.IGNORECASE
)
_SOS_RE   = re.compile(
    r'^SOS:(-?\d+\.?\d*),(-?\d+\.?\d*),HELP(?::(.+))?$',
    re.IGNORECASE
)
_PING_RE  = re.compile(r'^PING:(.+)$', re.IGNORECASE)
_ACK_RE   = re.compile(r'^ACK:(.+)$', re.IGNORECASE)
_NODE_RE  = re.compile(r'^NODE:([^,]+),(-?\d+\.?\d*),(-?\d+\.?\d*)$', re.IGNORECASE)


class ProtocolParser:
    """
    Stateless parser for the mesh network wire protocol.

    Returns a dict on success, None on unrecognised input.

    Return shapes
    ─────────────
    CHAT  → { type, sender, text, ts }
    SYS   → { type, node_id, lat, lng, temp, hum, smoke, water, ts }
    SOS   → { type, sender, lat, lng, ts }
    PING  → { type, node_id, ts }
    ACK   → { type, msg_id, ts }
    NODE  → { type, node_id, lat, lng, ts }
    """

    def parse(self, raw: str) -> Optional[Dict[str, Any]]:
        raw = raw.strip()
        if not raw:
            return None

        ts = time.time()

        m = _CHAT_RE.match(raw)
        if m:
            sender = m.group(1) or 'NODE'
            text   = m.group(2)
            log.debug("CHAT from %s: %s", sender, text)
            return {'type': 'CHAT', 'sender': sender, 'text': text, 'ts': ts}

        m = _SYS_RE.match(raw)
        if m:
            lat, lng, temp, hum, smoke, water = (
                float(m.group(1)), float(m.group(2)),
                float(m.group(3)), float(m.group(4)),
                int(m.group(5)),   int(m.group(6))
            )
            log.debug("SYS: lat=%.5f lng=%.5f t=%.1f h=%.1f s=%d w=%d",
                      lat, lng, temp, hum, smoke, water)
            return {
                'type':    'SYS',
                'node_id': 'NODE-1',
                'lat':     lat,
                'lng':     lng,
                'temp':    temp,
                'hum':     hum,
                'smoke':   smoke,
                'water':   water,
                'ts':      ts,
            }

        m = _SOS_RE.match(raw)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            sender   = m.group(3) or 'UNKNOWN'
            log.warning("SOS! sender=%s lat=%.5f lng=%.5f", sender, lat, lng)
            return {'type': 'SOS', 'sender': sender, 'lat': lat, 'lng': lng, 'ts': ts}

        m = _PING_RE.match(raw)
        if m:
            return {'type': 'PING', 'node_id': m.group(1), 'ts': ts}

        m = _ACK_RE.match(raw)
        if m:
            return {'type': 'ACK', 'msg_id': m.group(1), 'ts': ts}

        m = _NODE_RE.match(raw)
        if m:
            return {
                'type': 'NODE',
                'node_id': m.group(1),
                'lat': float(m.group(2)),
                'lng': float(m.group(3)),
                'ts': ts,
            }

        log.warning("Unrecognised BLE string: %r", raw)
        return None

    # ── Convenience builders (for sending) ────────────────────────────────────

    @staticmethod
    def build_chat(text: str, sender: str = 'CMD') -> str:
        return f"CHAT:{sender}:{text}"

    @staticmethod
    def build_sos_ack(lat: float, lng: float) -> str:
        return f"ACK:SOS:{lat:.5f},{lng:.5f}"

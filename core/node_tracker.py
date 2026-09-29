"""
core/node_tracker.py
====================
In-memory registry of all mesh nodes seen in the current session.
Each node entry holds latest GPS, telemetry, SOS state, and signal info.
"""

import time
import logging
from typing import Dict, Any, Optional, List

log = logging.getLogger(__name__)

# Default position (Chennai city centre)
DEFAULT_LAT = 13.0827
DEFAULT_LNG = 80.2707


class NodeEntry:
    """Represents one ESP32 node in the mesh network."""

    def __init__(self, node_id: str):
        self.node_id    = node_id
        self.lat        = DEFAULT_LAT
        self.lng        = DEFAULT_LNG
        self.temp       = 0.0
        self.hum        = 0.0
        self.smoke      = 0
        self.water      = 0
        self.sos        = False
        self.sos_lat    = None
        self.sos_lng    = None
        self.last_seen  = time.time()
        self.rssi       = -70          # placeholder RSSI
        self.online     = True
        self.msg_count  = 0
        self.sos_count  = 0
    @property
    def urgency(self) -> int:
        """
        Returns Urgency Degree:
        1: Priority 1 - FIRE/GAS
        2: Priority 2 - FLOOD
        3: Priority 3 - MANUAL SOS
        4: Normal - SAFE
        """
        # We'll use app-level configurable thresholds ideally, but defaults here match prompt
        if self.smoke > 2000 or (self.temp > 45.0 and self.hum < 20.0):
            return 1
        if self.water > 1000:
            return 2
        if self.sos:
            return 3
        return 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            'node_id':   self.node_id,
            'lat':       self.lat,
            'lng':       self.lng,
            'temp':      self.temp,
            'hum':       self.hum,
            'smoke':     self.smoke,
            'water':     self.water,
            'sos':       self.sos,
            'urgency':   self.urgency,
            'sos_lat':   self.sos_lat,
            'sos_lng':   self.sos_lng,
            'last_seen': self.last_seen,
            'rssi':      self.rssi,
            'online':    self.online,
            'msg_count': self.msg_count,
            'sos_count': self.sos_count,
        }


class NodeTracker:
    """
    Tracks all nodes seen over the BLE connection.
    Updates node state from parsed SYS / SOS / PING / NODE events.
    """

    # Nodes silent for longer than this are considered offline
    OFFLINE_THRESHOLD = 120.0    # seconds

    def __init__(self):
        self._nodes: Dict[str, NodeEntry] = {}
        # Gateway node is always present
        self._nodes['GATEWAY'] = NodeEntry('GATEWAY')

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def nodes(self) -> Dict[str, NodeEntry]:
        self._sweep_offline()
        return dict(self._nodes)

    def get(self, node_id: str) -> Optional[NodeEntry]:
        return self._nodes.get(node_id)

    def all_dicts(self) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in self._nodes.values()]

    def update(self, event: Dict[str, Any]):
        """Handle SYS / PING / NODE events."""
        nid  = event.get('node_id', 'NODE-1')
        node = self._get_or_create(nid)
        node.last_seen = event.get('ts', time.time())
        node.online    = True

        etype = event.get('type')
        if etype == 'SYS':
            node.lat   = event['lat']
            node.lng   = event['lng']
            node.temp  = event['temp']
            node.hum   = event['hum']
            node.smoke = event['smoke']
            node.water = event['water']
            node.sos   = False          # SYS packet clears SOS
            log.debug("NodeTracker updated %s via SYS", nid)

        elif etype in ('NODE', 'PING'):
            if 'lat' in event:
                node.lat = event['lat']
            if 'lng' in event:
                node.lng = event['lng']

    def update_sos(self, event: Dict[str, Any]):
        """Handle SOS events."""
        nid  = event.get('sender', 'UNKNOWN')
        node = self._get_or_create(nid)
        node.sos       = True
        node.sos_lat   = event['lat']
        node.sos_lng   = event['lng']
        node.sos_count += 1
        node.last_seen = event.get('ts', time.time())
        node.online    = True
        log.warning("NodeTracker: SOS from %s at (%.5f, %.5f)", nid, event['lat'], event['lng'])

    def clear_sos(self, node_id: str):
        if node_id in self._nodes:
            self._nodes[node_id].sos = False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _get_or_create(self, node_id: str) -> NodeEntry:
        if node_id not in self._nodes:
            self._nodes[node_id] = NodeEntry(node_id)
            log.info("NodeTracker: new node %s", node_id)
        return self._nodes[node_id]

    def _sweep_offline(self):
        now = time.time()
        for node in self._nodes.values():
            if now - node.last_seen > self.OFFLINE_THRESHOLD:
                node.online = False

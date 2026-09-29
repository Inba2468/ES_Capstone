"""
ui/screens/map_screen.py
========================
Offline tactical map screen.

Features:
  - MapView (kivy-garden.mapview) with offline MBTiles tile source
  - Node markers with callout labels (lat/lng, temp, SOS status)
  - Real-time node position updates
  - Tap-to-inspect node info panel
  - Distance calculator between two nodes
  - "Center on node" button
  - GPS track line overlay
  - MBTiles fallback to online OpenStreetMap if local tiles missing
"""

import os
import math
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, NumericProperty, ListProperty, BooleanProperty
from kivy.clock import Clock

try:
    from kivy_garden.mapview import MapView, MapMarker, MapMarkerPopup
    from kivy.uix.button import ButtonBehavior
    MAPVIEW_AVAILABLE = True

    class NodeMarker(MapMarkerPopup):
        node_id = StringProperty("")
        urgency = NumericProperty(4)
        
        def on_release(self):
            app = self.parent.parent.parent.parent.parent.app # Get to MapScreen app
            if hasattr(app, 'sm'):
                app.sm.get_screen('map').select_node(self.node_id)
            return True
            
except ImportError:
    MAPVIEW_AVAILABLE = False

# Default map centre (Chennai)
DEFAULT_LAT = 13.0827
DEFAULT_LNG = 80.2707

MBTILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'data', 'maps'
)


class MapScreen(Screen):
    """Tactical offline map with live node pins."""

    selected_node  = StringProperty("")
    node_info      = StringProperty("Tap a node to inspect")
    node_count     = NumericProperty(0)
    map_mode       = StringProperty("TACTICAL")   # TACTICAL / SATELLITE / TERRAIN
    center_lat     = NumericProperty(DEFAULT_LAT)
    center_lng     = NumericProperty(DEFAULT_LNG)
    sos_active     = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._markers = {}          # node_id → MapMarker
        self._map_widget = None

    def on_enter(self):
        self._inject_mapview()
        Clock.schedule_interval(self._refresh_nodes, 5.0)

    def _inject_mapview(self):
        """Programmatically add MapView to the container (KV can't instantiate garden widgets)."""
        if not MAPVIEW_AVAILABLE:
            return
        if hasattr(self.ids, 'map_container') and not self._map_widget:
            from kivy_garden.mapview import MapView
            mv = MapView(
                lat=self.center_lat,
                lon=self.center_lng,
                zoom=14,
                map_source='osm',   # fallback; override with mbtiles below
            )
            mv.size_hint = (1, 1)
            mv.bind(on_map_relocated=lambda inst, zoom, coord: None)
            self.ids.map_container.add_widget(mv)
            self._map_widget = mv
            # Bind map_container id to map_view id for marker access
            self.ids['map_view'] = mv

    def on_leave(self):
        Clock.unschedule(self._refresh_nodes)

    def _refresh_nodes(self, dt=None):
        if not self.app:
            return
        nodes = self.app.node_tracker.nodes
        self.node_count = len(nodes)
        for nid, node in nodes.items():
            self._update_marker(node)

    def _update_marker(self, node):
        """Add or move a map marker for a node."""
        if not MAPVIEW_AVAILABLE or not hasattr(self.ids, 'map_view'):
            return
        mv = self.ids.map_view

        if node.node_id not in self._markers:
            marker = NodeMarker(
                lat=node.lat, lon=node.lng,
                node_id=node.node_id,
                urgency=node.urgency
            )
            self._markers[node.node_id] = marker
            mv.add_widget(marker)
        else:
            marker = self._markers[node.node_id]
            marker.lat = node.lat
            marker.lon = node.lng
            marker.urgency = node.urgency

    def update_node(self, event: dict):
        """Called from main dispatcher when SYS event arrives."""
        self._refresh_nodes()
        # Centre on node if first data
        if self.center_lat == DEFAULT_LAT:
            self.center_lat = event.get('lat', DEFAULT_LAT)
            self.center_lng = event.get('lng', DEFAULT_LNG)

    def select_node(self, node_id: str):
        self.selected_node = node_id
        if self.app:
            node = self.app.node_tracker.get(node_id)
            gateway = self.app.node_tracker.get('GATEWAY')
            if node:
                dist_str = ""
                if gateway and node_id != 'GATEWAY':
                    dist_km = self._haversine(gateway.lat, gateway.lng, node.lat, node.lng)
                    if dist_km < 1.0:
                        dist_str = f"📏 DIST: {dist_km*1000:.0f}m\n"
                    else:
                        dist_str = f"📏 DIST: {dist_km:.2f}km\n"
                
                urg_str = {1: '[color=#ff3333]🔥 PRIORITY 1[/color]', 2: '[color=#3388ff]🌊 PRIORITY 2[/color]', 3: '[color=#ff8800]🚨 SOS[/color]'}.get(node.urgency, '[color=#1AE580]✅ SAFE[/color]')
                self.node_info = (
                    f"[b]{node_id}[/b]  -  {urg_str}\n"
                    f"📍 {node.lat:.5f}, {node.lng:.5f}\n"
                    f"{dist_str}"
                    f"🌡 {node.temp:.1f}°C  💧{node.hum:.0f}%\n"
                    f"🔥 Smoke:{node.smoke}  Water:{node.water}"
                )

    def center_on_node(self, node_id: str = None):
        target = node_id or self.selected_node
        if self.app and target:
            node = self.app.node_tracker.get(target)
            if node and hasattr(self.ids, 'map_view'):
                self.ids.map_view.center_on(node.lat, node.lng)

    def _haversine(self, lat1, lng1, lat2, lng2) -> float:
        """Return distance in km between two coordinates."""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def goto(self, screen_name: str):
        if self.app:
            self.app.sm.current = screen_name

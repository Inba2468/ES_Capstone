"""
Tactical Off-Grid Mesh Network
================================
Main application entry point – Android + Desktop compatible.
Boots the Kivy app, registers all screens, and initialises the BLE manager.
"""

import asyncio
import threading
import os
import sys
import platform

# ── Android permission bootstrap (must run before kivy) ───────────────────────
IS_ANDROID = False
try:
    from android.permissions import request_permissions, Permission
    IS_ANDROID = True
except ImportError:
    pass

# Kivy environment setup (must be before any kivy import)
if not IS_ANDROID:
    os.environ.setdefault('KIVY_GL_BACKEND', 'angle_sdl2')
    os.environ.setdefault('KIVY_AUDIO', 'sdl2')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.properties import StringProperty, BooleanProperty

from core.ble_manager import BLEManager
from core.protocol_parser import ProtocolParser
from core.message_store import MessageStore
from core.node_tracker import NodeTracker

from ui.screens.boot_screen import BootScreen
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.chat_screen import ChatScreen
from ui.screens.map_screen import MapScreen
from ui.screens.sos_screen import SOSScreen
from ui.screens.settings_screen import SettingsScreen

# ── Window defaults (desktop only) ───────────────────────────────────────────
if not IS_ANDROID:
    Window.size = (420, 860)
Window.clearcolor = get_color_from_hex('#0A0E1A')

# ── Load KV files ─────────────────────────────────────────────────────────────
KV_DIR = os.path.join(os.path.dirname(__file__), 'ui', 'kv')
for kv_file in ['boot.kv', 'dashboard.kv', 'chat.kv', 'map.kv', 'sos.kv', 'settings.kv']:
    kv_path = os.path.join(KV_DIR, kv_file)
    if os.path.exists(kv_path):
        Builder.load_file(kv_path)

# ── Register fonts ────────────────────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'fonts')
orbitron_path = os.path.join(FONT_DIR, 'Orbitron-Bold.ttf')
if os.path.exists(orbitron_path):
    LabelBase.register(name='Orbitron', fn_regular=orbitron_path)

# ─────────────────────────────────────────────────────────────────────────────

ROOT_KV = '''
<RootLayout@FloatLayout>:
    ScreenManager:
        id: sm
    # Global Status Bar
    BoxLayout:
        size_hint_y: None
        height: 24
        y: root.height - 24
        padding: [10, 0]
        canvas.before:
            Color:
                rgba: 0.02, 0.02, 0.04, 0.9
            Rectangle:
                pos: self.pos
                size: self.size
            Color:
                rgba: 0, 1, 1, 0.5
            Line:
                points: [self.x, self.y, self.right, self.y]
                width: 1
        Label:
            text: app.ble_status
            color: (0, 1, 1, 1) if 'CONNECTED' in app.ble_status else (1, 0.2, 0.2, 1)
            font_size: '9sp'
            bold: True
        Label:
            text: 'GPS: ' + ('LOCK' if app.gps_fix else 'NO FIX')
            color: (0, 1, 1, 1) if app.gps_fix else (1, 0.6, 0, 1)
            font_size: '9sp'
            bold: True
        Label:
            text: 'ID: ' + app.callsign
            color: 0, 1, 1, 1
            font_size: '9sp'
            bold: True

    # Floating SOS Button
    Button:
        text: 'SOS'
        size_hint: None, None
        size: 60, 60
        pos: root.width - 70, 70
        background_color: 0, 0, 0, 0
        background_normal: ''
        color: 1, 0.9, 0.9, 1
        font_size: '14sp'
        bold: True
        on_release: app.confirm_sos()
        canvas.before:
            Color:
                rgba: 0.8, 0.1, 0.1, 0.7
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [30]
            Color:
                rgba: 1, 0.3, 0.3, 1
            Line:
                rounded_rectangle: (self.x, self.y, self.width, self.height, 30)
                width: 1.5
'''
Builder.load_string(ROOT_KV)


class TacticalApp(App):
    """
    Root application class.
    """
    ble_status = StringProperty("DISCONNECTED")
    gps_fix    = BooleanProperty(False)
    callsign   = StringProperty("OPERATOR-1")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "TACTICAL MESH  //  OFFLINE NET"

        # Shared data layer
        self.message_store = MessageStore()
        self.node_tracker  = NodeTracker()
        self.parser        = ProtocolParser()

        # BLE manager
        self.ble_manager   = BLEManager(
            on_data=self._on_ble_data,
            on_status=self._on_ble_status
        )

        # Background event loop for BLE
        self._ble_loop   = asyncio.new_event_loop()
        self._ble_thread = threading.Thread(
            target=self._run_ble_loop, daemon=True, name="BLE-Thread"
        )

    # ── Kivy lifecycle ────────────────────────────────────────────────────────

    def build(self):
        # Request Android permissions
        if IS_ANDROID:
            request_permissions([
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_ADMIN,
                Permission.BLUETOOTH_SCAN,
                Permission.BLUETOOTH_CONNECT,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.VIBRATE,
            ])

        from kivy.factory import Factory
        self.root_layout = Factory.RootLayout()
        self.sm = self.root_layout.ids.sm
        self.sm.transition = FadeTransition(duration=0.25)

        screens = [
            BootScreen(name='boot'),
            DashboardScreen(name='dashboard'),
            ChatScreen(name='chat'),
            MapScreen(name='map'),
            SOSScreen(name='sos'),
            SettingsScreen(name='settings'),
        ]
        for screen in screens:
            screen.app = self          # back-reference
            self.sm.add_widget(screen)

        self.sm.current = 'boot'
        return self.root_layout

    def on_start(self):
        self._ble_thread.start()
        # Move to dashboard after boot animation
        Clock.schedule_once(lambda dt: self._goto('dashboard'), 3.5)

    def on_stop(self):
        self._ble_loop.call_soon_threadsafe(self._ble_loop.stop)
        self.message_store.close()

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _goto(self, screen_name):
        self.sm.current = screen_name

    # ── BLE thread ────────────────────────────────────────────────────────────

    def _run_ble_loop(self):
        asyncio.set_event_loop(self._ble_loop)
        self._ble_loop.run_forever()

    # ── Data pipeline ─────────────────────────────────────────────────────────

    def _on_ble_status(self, status: str):
        Clock.schedule_once(lambda dt: setattr(self, 'ble_status', status), 0)

    def _on_ble_data(self, raw: str):
        """Called from BLE thread; dispatch to parser."""
        event = self.parser.parse(raw)
        if event:
            Clock.schedule_once(lambda dt, e=event: self._dispatch(e), 0)

    @mainthread
    def _dispatch(self, event):
        """Route parsed events to the correct screen (main thread)."""
        etype = event.get('type')

        if etype == 'CHAT':
            self.message_store.add_message(
                sender=event.get('sender', 'NODE'),
                text=event['text'],
                direction='in'
            )
            chat = self.sm.get_screen('chat')
            chat.refresh_messages()
            self._show_notification("📡 New message from " + event.get('sender', 'NODE'))

        elif etype == 'SYS':
            # Log telemetry
            self.message_store.log_telemetry(event)
            self.node_tracker.update(event)
            dash = self.sm.get_screen('dashboard')
            dash.update_telemetry(event)
            map_screen = self.sm.get_screen('map')
            map_screen.update_node(event)
            # Update GPS fix on app level
            lat = event.get('lat', 0.0)
            lng = event.get('lng', 0.0)
            self.gps_fix = (lat != 0.0 or lng != 0.0)

        elif etype == 'SOS':
            self.node_tracker.update_sos(event)
            sos = self.sm.get_screen('sos')
            sos.trigger(event)
            self.sm.current = 'sos'
            # Vibrate on Android
            if IS_ANDROID:
                try:
                    from android.runnable import run_on_ui_thread
                    from jnius import autoclass
                    Context = autoclass('android.content.Context')
                    Vibrator = autoclass('android.os.Vibrator')
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    vibrator = PythonActivity.mActivity.getSystemService(Context.VIBRATOR_SERVICE)
                    vibrator.vibrate(1000)
                except Exception:
                    pass

        elif etype == 'PING':
            self.node_tracker.update(event)

        elif etype == 'NODE':
            self.node_tracker.update(event)
            map_screen = self.sm.get_screen('map')
            map_screen.update_node(event)

    def _show_notification(self, text: str):
        """Toast-style notification overlay."""
        if self.sm.current == 'dashboard':
            dash = self.sm.get_screen('dashboard')
            if hasattr(dash, 'show_toast'):
                dash.show_toast(text)
        elif self.sm.current != 'chat':
            dash = self.sm.get_screen('dashboard')
            if hasattr(dash, 'show_toast'):
                dash.show_toast(text)

    # ── BLE control (called from settings screen) ─────────────────────────────

    def connect_ble(self, address: str):
        asyncio.run_coroutine_threadsafe(
            self.ble_manager.connect(address), self._ble_loop
        )

    def disconnect_ble(self):
        asyncio.run_coroutine_threadsafe(
            self.ble_manager.disconnect(), self._ble_loop
        )

    def scan_ble(self, callback):
        asyncio.run_coroutine_threadsafe(
            self.ble_manager.scan(callback), self._ble_loop
        )

    def send_message(self, text: str):
        """Send a chat message through the BLE gateway."""
        raw = self.parser.build_chat(text, sender=self.callsign)
        asyncio.run_coroutine_threadsafe(
            self.ble_manager.send(raw), self._ble_loop
        )
        self.message_store.add_message(
            sender=self.callsign, text=text, direction='out'
        )
        chat = self.sm.get_screen('chat')
        chat.refresh_messages()

    def confirm_sos(self):
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label

        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        content.add_widget(Label(
            text="CONFIRM SOS BROADCAST?",
            color=(1, 0.2, 0.2, 1), bold=True
        ))

        btn_box = BoxLayout(
            orientation='horizontal', spacing=10,
            size_hint_y=None, height=50
        )
        btn_cancel  = Button(text="CANCEL",    background_color=(0.2, 0.2, 0.2, 1))
        btn_confirm = Button(text="BROADCAST", background_color=(1, 0, 0, 1))

        btn_box.add_widget(btn_cancel)
        btn_box.add_widget(btn_confirm)
        content.add_widget(btn_box)

        popup = Popup(
            title='EMERGENCY', content=content,
            size_hint=(0.8, 0.4), auto_dismiss=False,
            title_color=(1, 0, 0, 1), separator_color=(1, 0, 0, 1)
        )

        def do_broadcast(instance):
            popup.dismiss()
            # Best-effort GPS from dashboard
            try:
                dash = self.sm.get_screen('dashboard')
                lat  = getattr(dash, 'lat', 0.0)
                lng  = getattr(dash, 'lng', 0.0)
            except Exception:
                lat, lng = 0.0, 0.0
            raw = f"SOS:{lat:.5f},{lng:.5f},HELP:{self.callsign}"
            asyncio.run_coroutine_threadsafe(
                self.ble_manager.send(raw), self._ble_loop
            )
            # Show local SOS screen too
            sos = self.sm.get_screen('sos')
            sos.trigger({'type': 'SOS', 'sender': self.callsign,
                         'lat': lat, 'lng': lng})
            self.sm.current = 'sos'

        btn_cancel.bind(on_release=popup.dismiss)
        btn_confirm.bind(on_release=do_broadcast)
        popup.open()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    TacticalApp().run()

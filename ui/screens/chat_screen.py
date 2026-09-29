"""
ui/screens/chat_screen.py
==========================
Tactical encrypted-style messaging interface.

Features:
  - Scrollable chat history loaded from MessageStore
  - Dynamic bubble rendering via on_messages callback
  - Incoming (left) / outgoing (right) bubble layout
  - Timestamp per message
  - Encrypted send animation (simulates AES-style encoding)
  - Auto-scroll to latest message
  - Pre-set quick-reply tactical phrases
  - Character counter
  - Node selector (choose which mesh node to address)
"""

import time
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, ListProperty, NumericProperty
from kivy.clock import Clock
from kivy.animation import Animation


QUICK_REPLIES = [
    "COPY THAT",
    "MOVING TO POSITION",
    "HOLD POSITION",
    "NEED EVAC",
    "ALL CLEAR",
    "SOS ACKNOWLEDGED",
    "ROUTE COMPROMISED",
    "CHECK IN",
]


class ChatScreen(Screen):
    """Tactical chat interface with message history and quick replies."""

    input_text   = StringProperty("")
    messages     = ListProperty([])        # list of dicts
    char_count   = NumericProperty(0)
    send_status  = StringProperty("")
    node_label   = StringProperty("BROADCAST")

    def on_messages(self, instance, messages):
        """Rebuild the chat bubble stack whenever messages list changes."""
        if not hasattr(self.ids, 'msg_stack'):
            return
        from kivy.uix.label import Label
        from kivy.uix.boxlayout import BoxLayout
        from kivy.graphics import Color, RoundedRectangle
        import time as _time

        stack = self.ids.msg_stack
        stack.clear_widgets()

        for msg in messages:
            direction = msg.get('direction', 'in')
            sender    = msg.get('sender', 'NODE')
            text      = msg.get('text', '')
            ts        = msg.get('ts', 0)
            ts_str    = _time.strftime('%H:%M', _time.localtime(ts)) if ts else ''

            bubble = BoxLayout(
                orientation='vertical',
                size_hint_y=None,
                padding=[10, 4, 10, 4],
                spacing=2,
            )

            # Sender label
            sender_color = '#1AE580' if direction == 'in' else '#4A90F0'
            slabel = Label(
                text=f'[b][color={sender_color}]{sender}[/color][/b]  [color=#445544]{ts_str}[/color]',
                markup=True,
                font_size='9sp',
                size_hint_y=None,
                height=18,
                halign='left',
                text_size=(self.width * 0.75, None),
            )

            # Message text label
            mlabel = Label(
                text=text,
                font_size='12sp',
                color=(0.9, 0.95, 0.9, 1),
                size_hint_y=None,
                halign='left',
                text_size=(self.width * 0.75, None),
            )
            mlabel.bind(texture_size=lambda lbl, sz: setattr(lbl, 'height', sz[1] + 8))

            bubble.add_widget(slabel)
            bubble.add_widget(mlabel)
            bubble.height = 18 + 8 + 8 + 8   # approximate; updated by bind

            # Full-width row with spacer for alignment
            row = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                height=50,
            )
            if direction == 'out':
                row.add_widget(Label(size_hint_x=0.15))
            row.add_widget(bubble)
            if direction == 'in':
                row.add_widget(Label(size_hint_x=0.15))

            stack.add_widget(row)

    def on_enter(self):
        self.refresh_messages()

    def refresh_messages(self):
        """Reload messages from the store and update the list."""
        if self.app:
            raw = self.app.message_store.get_messages(limit=100)
            self.messages = raw
            # Auto-scroll (triggered in KV via on_messages)
            Clock.schedule_once(self._scroll_bottom, 0.1)

    def _scroll_bottom(self, dt):
        """Scroll the RecycleView to the bottom."""
        if hasattr(self.ids, 'chat_scroll'):
            self.ids.chat_scroll.scroll_y = 0

    def on_input_text(self, instance, value):
        self.char_count = len(value)

    def send_message(self):
        text = self.input_text.strip()
        if not text or not self.app:
            return
        self.input_text = ""
        self.char_count = 0

        # Visual send feedback
        self.send_status = "ENCRYPTING…"
        
        import time
        ts = time.strftime("[%H:%M]")
        formatted_text = f"{ts} {self.app.callsign}: {text}"
        
        Clock.schedule_once(lambda dt: self._do_send(formatted_text), 0.3)

    def _do_send(self, text: str):
        self.send_status = "TRANSMITTING…"
        self.app.send_message(text)
        Clock.schedule_once(lambda dt: setattr(self, 'send_status', "✓ SENT"), 0.5)
        Clock.schedule_once(lambda dt: setattr(self, 'send_status', ""), 2.0)

    def send_quick_reply(self, text: str):
        self.input_text = text
        self.send_message()

    def clear_history(self):
        if self.app:
            self.app.message_store.clear_messages()
            self.messages = []

    def goto(self, screen_name: str):
        if self.app:
            self.app.sm.current = screen_name

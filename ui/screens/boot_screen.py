"""
ui/screens/boot_screen.py
Boot / splash screen shown at startup.
"""

from kivy.uix.screenmanager import Screen
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.properties import NumericProperty, StringProperty


class BootScreen(Screen):
    """
    Animated startup splash.
    Shows a pulsing tactical logo, version, and a loading progress bar.
    """

    progress     = NumericProperty(0)
    status_text  = StringProperty("INITIALISING MESH…")
    alpha        = NumericProperty(0)

    _STATUS_STEPS = [
        (0.5,  "LOADING CRYPTO LAYER…"),
        (1.0,  "INITIALISING BLE STACK…"),
        (1.5,  "MOUNTING OFFLINE MAPS…"),
        (2.0,  "SYNCING NODE REGISTRY…"),
        (2.8,  "TACTICAL NET READY  ✓"),
    ]

    def on_enter(self):
        # Fade in
        Animation(alpha=1, duration=0.6).start(self)
        # Animate progress bar
        Animation(progress=100, duration=3.0, t='out_quad').start(self)
        # Step through status messages
        for delay, text in self._STATUS_STEPS:
            Clock.schedule_once(lambda dt, t=text: setattr(self, 'status_text', t), delay)

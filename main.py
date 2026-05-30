"""
main.py
-------
RetroCam — retro-styled camera app with real-time eye-tracking AR overlays.

Entry point for both desktop (development) and Android (production).

Architecture
------------
  main.py
  ├── screens/camera_screen.py   — live viewfinder, overlay selector, capture
  ├── screens/preview_screen.py  — photo preview + save
  ├── camera_processor.py        — background thread: capture + pipeline
  │   ├── eye_tracker.py         — MediaPipe Face Mesh eye detection
  │   ├── retro_filter.py        — CRT / vintage post-processing
  │   └── overlay_renderer.py    — AR overlay compositing
  └── assets/
      ├── overlay_teal.png       — teal/green spirit fish (user-supplied 1.png)
      └── overlay_red.png        — red/pink phantom fish  (user-supplied 2.png)
"""

# ── suppress noisy environment warnings before kivy import ────────────────
import os
os.environ.setdefault('KIVY_NO_ENV_CONFIG', '1')
os.environ.setdefault('KIVY_LOG_LEVEL', 'warning')

# ── desktop dev: narrow window to approximate mobile aspect ratio ─────────
from kivy.config import Config
Config.set('graphics', 'width',  '390')
Config.set('graphics', 'height', '844')
Config.set('graphics', 'resizable', '1')

# ── kivy / kivymd imports ─────────────────────────────────────────────────
from kivymd.app                 import MDApp
from kivy.uix.screenmanager    import ScreenManager, FadeTransition
from kivy.core.window          import Window

from screens.camera_screen     import CameraScreen
from screens.preview_screen    import PreviewScreen


class RetroCamApp(MDApp):

    # ── app metadata ──────────────────────────────────────────────────────

    title = 'RetroCam'
    icon  = os.path.join(os.path.dirname(__file__), 'assets', 'overlay_teal.png')

    # ── build ─────────────────────────────────────────────────────────────

    def build(self):
        # KivyMD theme
        self.theme_cls.theme_style       = 'Dark'
        self.theme_cls.primary_palette   = 'Teal'
        self.theme_cls.accent_palette    = 'Red'

        # Black window background (important for the viewfinder aesthetic)
        Window.clearcolor = (0, 0, 0, 1)

        self.sm = ScreenManager(transition=FadeTransition(duration=0.15))
        self.sm.add_widget(CameraScreen(name='camera'))
        self.sm.add_widget(PreviewScreen(name='preview'))
        return self.sm

    # ── lifecycle ─────────────────────────────────────────────────────────

    def on_stop(self):
        """Ensure the capture thread is stopped cleanly."""
        try:
            cam = self.sm.get_screen('camera')
            if cam.processor:
                cam.processor.stop()
        except Exception:
            pass


if __name__ == '__main__':
    RetroCamApp().run()

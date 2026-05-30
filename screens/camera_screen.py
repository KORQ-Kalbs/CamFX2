"""
screens/camera_screen.py
-------------------------
Main screen: live viewfinder + retro filter + AR eye-overlay controls.

Layout
------
  ┌───────────────────────────────┐
  │  [status bar: overlay name]   │  ← top label
  │                               │
  │      LIVE VIEWFINDER          │  ← KivyImage fed by CameraProcessor
  │                               │
  │  [🐟 teal] [● capture] [🐟 red] │  ← bottom controls bar
  └───────────────────────────────┘

Kivy texture update runs on the main thread (@mainthread decorator).
CameraProcessor lives on a background daemon thread.
"""

import os
import numpy as np

from kivy.uix.screenmanager  import Screen
from kivy.uix.floatlayout    import FloatLayout
from kivy.uix.boxlayout      import BoxLayout
from kivy.uix.widget         import Widget
from kivy.uix.image          import Image as KivyImage
from kivy.clock              import Clock, mainthread
from kivy.graphics.texture   import Texture
from kivy.graphics           import Color, Rectangle, RoundedRectangle
from kivy.properties         import NumericProperty, BooleanProperty

from kivymd.uix.button       import MDIconButton, MDFloatingActionButton
from kivymd.uix.label        import MDLabel

from camera_processor import CameraProcessor


ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')

OVERLAY_LABELS  = ['✦  TEAL SPIRIT', '✦  RED PHANTOM', '✦  NO OVERLAY']
OVERLAY_COLOURS = [
    (0.35, 0.95, 0.82, 1),
    (0.95, 0.30, 0.35, 1),
    (0.65, 0.65, 0.65, 1),
]


class CameraScreen(Screen):

    overlay_index = NumericProperty(0)
    retro_on      = BooleanProperty(True)

    # ── construction ──────────────────────────────────────────────────────

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.processor    = None
        self._last_frame  = None
        self._build_ui()

    def _build_ui(self):
        root = FloatLayout()

        # ── Viewfinder ────────────────────────────────────────────────
        self.viewfinder = KivyImage(
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )
        root.add_widget(self.viewfinder)

        # ── Top status bar ────────────────────────────────────────────
        top_bar = BoxLayout(
            orientation='horizontal',
            size_hint=(1, None),
            height=48,
            pos_hint={'x': 0, 'top': 1},
            padding=(16, 6),
        )
        with top_bar.canvas.before:
            Color(0, 0, 0, 0.50)
            self._top_bg = Rectangle(size=top_bar.size, pos=top_bar.pos)
        top_bar.bind(
            size=lambda _, v: setattr(self._top_bg, 'size', v),
            pos =lambda _, v: setattr(self._top_bg, 'pos',  v),
        )

        self.overlay_label = MDLabel(
            text=OVERLAY_LABELS[0],
            theme_text_color='Custom',
            text_color=OVERLAY_COLOURS[0],
            halign='center',
            font_style='Caption',
            bold=True,
        )
        top_bar.add_widget(self.overlay_label)

        # Retro toggle (top-right)
        self.btn_retro = MDIconButton(
            icon='television-vintage',
            theme_icon_color='Custom',
            icon_color=(0.35, 0.95, 0.82, 1),
            size_hint=(None, None),
            size=(40, 40),
            on_release=lambda *_: self.toggle_retro(),
        )
        top_bar.add_widget(self.btn_retro)

        root.add_widget(top_bar)

        # ── Bottom controls bar ───────────────────────────────────────
        ctrl_bar = BoxLayout(
            orientation='horizontal',
            size_hint=(1, None),
            height=112,
            pos_hint={'x': 0, 'y': 0},
            padding=(24, 16),
            spacing=8,
        )
        with ctrl_bar.canvas.before:
            Color(0, 0, 0, 0.58)
            self._ctrl_bg = Rectangle(size=ctrl_bar.size, pos=ctrl_bar.pos)
        ctrl_bar.bind(
            size=lambda _, v: setattr(self._ctrl_bg, 'size', v),
            pos =lambda _, v: setattr(self._ctrl_bg, 'pos',  v),
        )

        self.btn_teal = MDIconButton(
            icon='fish',
            theme_icon_color='Custom',
            icon_color=OVERLAY_COLOURS[0],
            size_hint=(None, None),
            size=(56, 56),
            on_release=lambda *_: self.set_overlay(0),
        )

        self.btn_capture = MDFloatingActionButton(
            icon='camera',
            md_bg_color=(1, 1, 1, 1),
            icon_color=(0.05, 0.05, 0.05, 1),
            size_hint=(None, None),
            size=(72, 72),
            on_release=lambda *_: self.capture(),
        )

        self.btn_red = MDIconButton(
            icon='fish',
            theme_icon_color='Custom',
            icon_color=OVERLAY_COLOURS[1],
            size_hint=(None, None),
            size=(56, 56),
            on_release=lambda *_: self.set_overlay(1),
        )

        # "No overlay" button
        self.btn_none = MDIconButton(
            icon='eye-off-outline',
            theme_icon_color='Custom',
            icon_color=OVERLAY_COLOURS[2],
            size_hint=(None, None),
            size=(44, 44),
            on_release=lambda *_: self.set_overlay(-1),
        )

        ctrl_bar.add_widget(self.btn_teal)
        ctrl_bar.add_widget(Widget())
        ctrl_bar.add_widget(self.btn_capture)
        ctrl_bar.add_widget(Widget())
        ctrl_bar.add_widget(self.btn_red)
        ctrl_bar.add_widget(self.btn_none)
        root.add_widget(ctrl_bar)

        self.add_widget(root)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def on_enter(self, *_):
        overlay_paths = [
            os.path.join(ASSETS_DIR, 'overlay_teal_nobg.png'),
            os.path.join(ASSETS_DIR, 'overlay_red_nobg.png'),
        ]
        self.processor = CameraProcessor(
            frame_callback=self._on_frame,
            overlay_assets=overlay_paths,
        )
        self.processor.set_overlay(self.overlay_index)
        self.processor.set_retro(self.retro_on)
        self.processor.start()

    def on_leave(self, *_):
        if self.processor:
            self.processor.stop()
            self.processor = None

    # ── UI callbacks ──────────────────────────────────────────────────────

    def set_overlay(self, index: int):
        self.overlay_index = index
        if self.processor:
            self.processor.set_overlay(index)

        if index < 0:
            self.overlay_label.text       = OVERLAY_LABELS[2]
            self.overlay_label.text_color = OVERLAY_COLOURS[2]
        else:
            self.overlay_label.text       = OVERLAY_LABELS[index]
            self.overlay_label.text_color = OVERLAY_COLOURS[index]

    def toggle_retro(self):
        self.retro_on = not self.retro_on
        if self.processor:
            self.processor.set_retro(self.retro_on)
        self.btn_retro.icon_color = (
            (0.35, 0.95, 0.82, 1) if self.retro_on else (0.4, 0.4, 0.4, 1)
        )

    def capture(self):
        if self.processor:
            self.processor.request_capture()
            Clock.schedule_once(self._poll_capture, 0.12)

    def _poll_capture(self, dt):
        """Poll for the captured frame (may need a few ticks)."""
        if self.processor and self.processor.captured_frame is not None:
            frame = self.processor.captured_frame.copy()
            self.processor.captured_frame = None
            preview = self.manager.get_screen('preview')
            preview.load_frame(frame)
            self.manager.current = 'preview'
        else:
            Clock.schedule_once(self._poll_capture, 0.08)

    # ── texture update (called from background thread) ────────────────────

    @mainthread
    def _on_frame(self, rgb_frame: np.ndarray):
        """Update the viewfinder texture. Must run on the Kivy main thread."""
        h, w = rgb_frame.shape[:2]
        texture = Texture.create(size=(w, h), colorfmt='rgb')
        # Kivy's texture origin is bottom-left → flip vertically
        buf = np.ascontiguousarray(np.flipud(rgb_frame))
        texture.blit_buffer(buf.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
        self.viewfinder.texture = texture

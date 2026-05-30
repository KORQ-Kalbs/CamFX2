"""
screens/preview_screen.py
--------------------------
Photo preview screen: displays the captured + retro-filtered + overlay-baked
photo and lets the user save it to the gallery or discard and retake.

On Android the photo is written to the app's external storage (Pictures/RetroCam).
On desktop it goes to ~/Pictures/RetroCam.
"""

import os
import numpy as np
import cv2
from datetime     import datetime

from kivy.uix.screenmanager  import Screen
from kivy.uix.floatlayout    import FloatLayout
from kivy.uix.boxlayout      import BoxLayout
from kivy.uix.widget         import Widget
from kivy.uix.image          import Image as KivyImage
from kivy.graphics.texture   import Texture
from kivy.graphics           import Color, Rectangle
from kivy.clock              import Clock

from kivymd.uix.button       import MDIconButton, MDRaisedButton, MDFlatButton
from kivymd.uix.label        import MDLabel


def _save_dir() -> str:
    """Return platform-appropriate save directory, creating it if needed."""
    try:
        # Android — write to external storage / Pictures
        from android.storage import primary_external_storage_path  # type: ignore
        base = primary_external_storage_path()
    except Exception:
        base = os.path.expanduser('~')

    path = os.path.join(base, 'Pictures', 'RetroCam')
    os.makedirs(path, exist_ok=True)
    return path


class PreviewScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._frame: np.ndarray | None = None   # BGR
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        root = FloatLayout()

        # ── Full-screen preview image ─────────────────────────────────
        self.preview_img = KivyImage(
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(1, 1),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )
        root.add_widget(self.preview_img)

        # ── Top bar: "PREVIEW" label ──────────────────────────────────
        top_bar = BoxLayout(
            orientation='horizontal',
            size_hint=(1, None),
            height=48,
            pos_hint={'x': 0, 'top': 1},
            padding=(16, 6),
        )
        with top_bar.canvas.before:
            Color(0, 0, 0, 0.55)
            self._top_bg = Rectangle(size=top_bar.size, pos=top_bar.pos)
        top_bar.bind(
            size=lambda _, v: setattr(self._top_bg, 'size', v),
            pos =lambda _, v: setattr(self._top_bg, 'pos',  v),
        )
        top_bar.add_widget(MDLabel(
            text='PREVIEW',
            theme_text_color='Custom',
            text_color=(1, 1, 1, 0.8),
            halign='center',
            bold=True,
            font_style='Caption',
        ))
        root.add_widget(top_bar)

        # ── Bottom bar: back / status / save ──────────────────────────
        ctrl_bar = BoxLayout(
            orientation='horizontal',
            size_hint=(1, None),
            height=96,
            pos_hint={'x': 0, 'y': 0},
            padding=(20, 12),
            spacing=12,
        )
        with ctrl_bar.canvas.before:
            Color(0, 0, 0, 0.65)
            self._ctrl_bg = Rectangle(size=ctrl_bar.size, pos=ctrl_bar.pos)
        ctrl_bar.bind(
            size=lambda _, v: setattr(self._ctrl_bg, 'size', v),
            pos =lambda _, v: setattr(self._ctrl_bg, 'pos',  v),
        )

        btn_back = MDIconButton(
            icon='close',
            theme_icon_color='Custom',
            icon_color=(1, 1, 1, 0.85),
            size_hint=(None, None),
            size=(52, 52),
            on_release=lambda *_: self._go_back(),
        )

        self.status_lbl = MDLabel(
            text='',
            theme_text_color='Custom',
            text_color=(0.35, 0.95, 0.82, 1),
            halign='center',
            font_style='Caption',
        )

        self.btn_save = MDRaisedButton(
            text='SAVE',
            md_bg_color=(0.35, 0.95, 0.82, 1),
            text_color=(0, 0, 0, 1),
            size_hint=(None, None),
            size=(100, 44),
            on_release=lambda *_: self._save(),
        )

        ctrl_bar.add_widget(btn_back)
        ctrl_bar.add_widget(Widget())
        ctrl_bar.add_widget(self.status_lbl)
        ctrl_bar.add_widget(Widget())
        ctrl_bar.add_widget(self.btn_save)
        root.add_widget(ctrl_bar)

        self.add_widget(root)

    # ── public API (called by CameraScreen) ───────────────────────────────

    def load_frame(self, bgr_frame: np.ndarray):
        """Display a BGR frame in the preview widget."""
        self._frame = bgr_frame
        self.status_lbl.text = ''
        self.btn_save.disabled = False
        self._show(bgr_frame)

    # ── internal helpers ──────────────────────────────────────────────────

    def _show(self, bgr: np.ndarray):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        texture = Texture.create(size=(w, h), colorfmt='rgb')
        buf = np.ascontiguousarray(np.flipud(rgb))
        texture.blit_buffer(buf.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
        self.preview_img.texture = texture

    def _save(self):
        if self._frame is None:
            return

        self.btn_save.disabled = True
        try:
            save_path = _save_dir()
            fname = 'retrocam_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.jpg'
            full_path = os.path.join(save_path, fname)
            cv2.imwrite(full_path, self._frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.status_lbl.text       = f'Saved  ✓'
            self.status_lbl.text_color = (0.35, 0.95, 0.82, 1)

            # Optionally trigger Media Scanner on Android
            try:
                from jnius import autoclass           # type: ignore
                Intent  = autoclass('android.content.Intent')
                Uri     = autoclass('android.net.Uri')
                File    = autoclass('java.io.File')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                intent  = Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
                intent.setData(Uri.fromFile(File(full_path)))
                context.sendBroadcast(intent)
            except Exception:
                pass   # not on Android — no-op

        except Exception as e:
            self.status_lbl.text       = f'Error: {e}'
            self.status_lbl.text_color = (0.95, 0.30, 0.35, 1)
            self.btn_save.disabled = False

    def _go_back(self):
        self.manager.current = 'camera'

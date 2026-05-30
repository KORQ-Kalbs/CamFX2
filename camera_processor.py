"""
camera_processor.py
--------------------
Background thread that:
  1. Grabs frames from the device camera via OpenCV VideoCapture
  2. Pipes each frame through: EyeTracker → OverlayRenderer → RetroFilter
  3. Posts the processed RGB frame to the Kivy main thread via a callback

The Kivy UI calls set_overlay() / set_retro() to update state atomically.
Photo capture is requested via request_capture(); the result frame is
placed in self.captured_frame (BGR) and can be polled from the UI thread.
"""

import threading
import time
import cv2
import numpy as np

from eye_tracker       import EyeTracker
from retro_filter      import RetroFilter
from overlay_renderer  import OverlayRenderer


# ── platform camera index heuristics ──────────────────────────────────────
#
#  Desktop  : 0 = first webcam (usually back-facing on laptops = selfie mode)
#  Android  : 1 = front-facing camera  (0 = rear)
#  We expose `camera_index` in start() so the UI can pass the right value.

DEFAULT_CAMERA_INDEX = 0
TARGET_FPS           = 30
FRAME_DELAY          = 1.0 / TARGET_FPS


class CameraProcessor:
    """
    Owns the capture loop, processing pipeline, and frame callback.

    Parameters
    ----------
    frame_callback  : callable(np.ndarray)
        Called with each processed RGB frame (Kivy-ready, Y-flipped).
    overlay_assets  : list[str]
        Ordered list of paths to overlay PNG files.
    """

    def __init__(self, frame_callback, overlay_assets: list):
        self._callback  = frame_callback
        self._running   = False
        self._thread    = None

        # Processing pipeline
        self._eye_tracker       = EyeTracker()
        self._retro_filter      = RetroFilter()
        self._overlay_renderer  = OverlayRenderer(overlay_assets)

        # Mutable state (written from UI thread, read from capture thread)
        self._active_overlay    = 0        # 0 = teal, 1 = red, -1 = none
        self._retro_enabled     = True
        self._state_lock        = threading.Lock()

        # Capture request / result (thread-safe hand-off)
        self._capture_event  = threading.Event()
        self.captured_frame  = None       # BGR np.ndarray, set after capture

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self, camera_index: int = DEFAULT_CAMERA_INDEX):
        self._cap = cv2.VideoCapture(camera_index)
        # Request a reasonable resolution (device may cap it)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if hasattr(self, '_cap') and self._cap.isOpened():
            self._cap.release()
        self._eye_tracker.close()

    # ── controls (called from UI / Kivy main thread) ───────────────────

    def set_overlay(self, index: int):
        with self._state_lock:
            self._active_overlay = index

    def set_retro(self, enabled: bool):
        with self._state_lock:
            self._retro_enabled = enabled

    def request_capture(self):
        """Signal the capture thread to snapshot the next frame."""
        self.captured_frame = None
        self._capture_event.set()

    # ── capture loop (runs on background thread) ───────────────────────

    def _loop(self):
        while self._running:
            t0 = time.perf_counter()

            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            # Front-camera mirror flip
            frame = cv2.flip(frame, 1)

            # Read state atomically
            with self._state_lock:
                overlay_idx  = self._active_overlay
                retro_on     = self._retro_enabled

            # ── pipeline ────────────────────────────────────────────────
            # 1. Eye detection
            eye_data = self._eye_tracker.detect(frame)

            # 2. AR overlay
            if overlay_idx >= 0 and eye_data.detected:
                frame = self._overlay_renderer.render(frame, eye_data, overlay_idx)

            # 3. Retro filter (applied after overlay so the filter covers both)
            if retro_on:
                frame = self._retro_filter.apply(frame)

            # ── capture snapshot if requested ───────────────────────────
            if self._capture_event.is_set():
                self.captured_frame = frame.copy()
                self._capture_event.clear()

            # ── send to Kivy (BGR → RGB, vertical flip for texture origin) ──
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._callback(rgb)

            # Pace the loop to ~TARGET_FPS
            elapsed = time.perf_counter() - t0
            sleep   = max(0.0, FRAME_DELAY - elapsed)
            if sleep:
                time.sleep(sleep)

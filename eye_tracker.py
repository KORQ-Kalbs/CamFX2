"""
eye_tracker.py
--------------
Real-time eye landmark detection using MediaPipe Face Mesh.

Provides EyeData (centers, widths, heights, head tilt) for each frame.
Iris landmarks (468/473) are used when available for sub-pixel accuracy.
"""

import math
import os
import urllib.request

import numpy as np
import mediapipe as mp


# ── MediaPipe landmark indices ─────────────────────────────────────────────

# Eye corners
LEFT_EYE_INNER  = 133   # inner (nose-side) corner
LEFT_EYE_OUTER  = 33    # outer corner
RIGHT_EYE_INNER = 362
RIGHT_EYE_OUTER = 263

# Eye top/bottom for height measurement
LEFT_EYE_TOP    = 159
LEFT_EYE_BOTTOM = 145
RIGHT_EYE_TOP   = 386
RIGHT_EYE_BOTTOM = 374

# Iris centres (enabled with refine_landmarks=True)
LEFT_IRIS_CENTER  = 468
RIGHT_IRIS_CENTER = 473

MODEL_URL = (
    'https://storage.googleapis.com/mediapipe-models/'
    'face_landmarker/face_landmarker/float16/1/face_landmarker.task'
)
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'face_landmarker.task')


def _ensure_model_file() -> str:
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except Exception as exc:
        raise RuntimeError(
            'Unable to download the MediaPipe face landmarker model.'
        ) from exc

    return MODEL_PATH


class EyeData:
    """
    Processed eye detection result for a single frame.
    All coordinates are in pixel space.
    """
    __slots__ = (
        'detected',
        'left_center', 'right_center',
        'left_width',  'right_width',
        'left_height', 'right_height',
        'head_tilt_angle',
    )

    def __init__(self):
        self.detected          = False
        self.left_center       = None   # (x, y) int pixels
        self.right_center      = None
        self.left_width        = 0      # horizontal span in pixels
        self.right_width       = 0
        self.left_height       = 0
        self.right_height      = 0
        self.head_tilt_angle   = 0.0    # degrees; 0 = perfectly level


class EyeTracker:
    """
    Wraps MediaPipe FaceMesh for frame-by-frame eye tracking.

    Usage
    -----
    tracker = EyeTracker()
    eye_data = tracker.detect(bgr_frame)  # call each frame
    """

    def __init__(self):
        model_path = _ensure_model_file()

        self._face_landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(
            mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )

    # ── public API ────────────────────────────────────────────────────────

    def detect(self, frame_bgr: np.ndarray) -> EyeData:
        """
        Run Face Mesh on a BGR frame. Returns EyeData.
        Thread-safe — owns its own FaceMesh instance.
        """
        import cv2

        data = EyeData()
        h, w = frame_bgr.shape[:2]

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self._face_landmarker.detect(mp_image)

        if not results.face_landmarks:
            return data

        lm = results.face_landmarks[0]

        def pxf(idx):
            """Return landmark as float pixel coords."""
            return lm[idx].x * w, lm[idx].y * h

        def pxi(idx):
            x, y = pxf(idx)
            return int(x), int(y)

        # ── iris centres ───────────────────────────────────────────────
        try:
            lx, ly = pxf(LEFT_IRIS_CENTER)
            rx, ry = pxf(RIGHT_IRIS_CENTER)
        except IndexError:
            # Fallback if iris landmarks unavailable
            li, lo = pxf(LEFT_EYE_INNER),  pxf(LEFT_EYE_OUTER)
            ri, ro = pxf(RIGHT_EYE_INNER), pxf(RIGHT_EYE_OUTER)
            lx, ly = (li[0] + lo[0]) / 2, (li[1] + lo[1]) / 2
            rx, ry = (ri[0] + ro[0]) / 2, (ri[1] + ro[1]) / 2

        data.left_center  = (int(lx), int(ly))
        data.right_center = (int(rx), int(ry))

        # ── eye widths (corner-to-corner) ──────────────────────────────
        li, lo = pxf(LEFT_EYE_INNER),  pxf(LEFT_EYE_OUTER)
        ri, ro = pxf(RIGHT_EYE_INNER), pxf(RIGHT_EYE_OUTER)

        data.left_width  = int(abs(li[0] - lo[0]))
        data.right_width = int(abs(ri[0] - ro[0]))

        # ── eye heights ────────────────────────────────────────────────
        lt, lb = pxf(LEFT_EYE_TOP),   pxf(LEFT_EYE_BOTTOM)
        rt, rb = pxf(RIGHT_EYE_TOP),  pxf(RIGHT_EYE_BOTTOM)

        data.left_height  = int(abs(lt[1] - lb[1]))
        data.right_height = int(abs(rt[1] - rb[1]))

        # ── head tilt (angle between eye centres) ──────────────────────
        dx = rx - lx
        dy = ry - ly
        data.head_tilt_angle = math.degrees(math.atan2(dy, dx))

        data.detected = True
        return data

    def close(self):
        self._face_landmarker.close()

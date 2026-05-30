"""
retro_filter.py
---------------
Stack of real-time retro / CRT post-processing effects applied to every frame.

Effects (applied in order):
  1. Chromatic aberration  — RGB channel horizontal fringing
  2. Scanlines             — horizontal dark bands (CRT phosphor rows)
  3. Vignette              — radial darkening toward edges
  4. Film grain            — per-frame Gaussian noise
  5. Sepia tint            — partial warm colour wash

All operations are numpy / OpenCV and cache size-dependent masks to avoid
recomputing them every frame.
"""

import cv2
import numpy as np


class RetroFilter:
    """
    Apply the full retro/CRT effect stack to a BGR uint8 frame.

    Usage
    -----
    filt = RetroFilter()
    processed = filt.apply(bgr_frame)
    """

    def __init__(
        self,
        chroma_strength: int   = 3,
        scanline_gap: int      = 3,
        scanline_alpha: float  = 0.35,
        vignette_strength: float = 0.60,
        grain_intensity: int   = 14,
        sepia_amount: float    = 0.22,
    ):
        self.chroma_strength   = chroma_strength
        self.scanline_gap      = scanline_gap
        self.scanline_alpha    = scanline_alpha
        self.vignette_strength = vignette_strength
        self.grain_intensity   = grain_intensity
        self.sepia_amount      = sepia_amount

        # Pre-computed masks keyed by (h, w) to avoid per-frame realloc
        self._scanline_cache: dict = {}
        self._vignette_cache: dict = {}

    # ── main entry point ──────────────────────────────────────────────────

    def apply(self, frame: np.ndarray) -> np.ndarray:
        frame = self._chromatic_aberration(frame)
        frame = self._scanlines(frame)
        frame = self._vignette(frame)
        frame = self._grain(frame)
        frame = self._sepia_tint(frame)
        return frame

    # ── individual effects ────────────────────────────────────────────────

    def _chromatic_aberration(self, frame: np.ndarray) -> np.ndarray:
        """
        Shift the R channel right and the B channel left by `strength` pixels.
        Produces the classic VHS colour-fringing artefact.
        """
        s = self.chroma_strength
        b, g, r = cv2.split(frame)
        h, w = frame.shape[:2]

        M_r = np.float32([[1, 0,  s], [0, 1, 0]])
        M_b = np.float32([[1, 0, -s], [0, 1, 0]])

        r = cv2.warpAffine(r, M_r, (w, h))
        b = cv2.warpAffine(b, M_b, (w, h))

        return cv2.merge([b, g, r])

    def _scanlines(self, frame: np.ndarray) -> np.ndarray:
        """
        Darken every `gap`-th row to simulate CRT phosphor lines.
        Result is cached for the frame size.
        """
        h, w = frame.shape[:2]
        key = (h, w, self.scanline_gap, self.scanline_alpha)

        if key not in self._scanline_cache:
            mask = np.ones((h, w, 3), dtype=np.float32)
            mask[:: self.scanline_gap, :, :] = 1.0 - self.scanline_alpha
            self._scanline_cache[key] = mask

        out = frame.astype(np.float32) * self._scanline_cache[key]
        return np.clip(out, 0, 255).astype(np.uint8)

    def _vignette(self, frame: np.ndarray) -> np.ndarray:
        """
        Radially darken the image toward its edges.
        The mask is cached per (h, w).
        """
        h, w = frame.shape[:2]
        key = (h, w, self.vignette_strength)

        if key not in self._vignette_cache:
            # Normalised distance from centre: 0 at centre, 1 at corners
            X = np.linspace(-1.0, 1.0, w, dtype=np.float32)
            Y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
            Xg, Yg = np.meshgrid(X, Y)
            dist = np.hypot(Xg, Yg)
            vign = 1.0 - np.clip(dist * self.vignette_strength, 0.0, 1.0)
            self._vignette_cache[key] = vign[:, :, np.newaxis]

        out = frame.astype(np.float32) * self._vignette_cache[key]
        return np.clip(out, 0, 255).astype(np.uint8)

    def _grain(self, frame: np.ndarray) -> np.ndarray:
        """
        Add per-frame uniform noise simulating analogue film grain.
        Using a fast integer approach avoids float conversion overhead.
        """
        g = self.grain_intensity
        noise = np.random.randint(-g, g + 1, frame.shape, dtype=np.int16)
        noisy = frame.astype(np.int16) + noise
        return np.clip(noisy, 0, 255).astype(np.uint8)

    def _sepia_tint(self, frame: np.ndarray) -> np.ndarray:
        """
        Blend the original frame with its sepia version.
        `sepia_amount` = 0.0 → original colour; 1.0 → full sepia.
        """
        # Classic sepia matrix (applied to BGR channel order)
        # Output channels: B'  G'  R'
        sepia = np.array([
            [0.131, 0.534, 0.272],   # B'
            [0.168, 0.686, 0.349],   # G'
            [0.189, 0.769, 0.393],   # R'
        ], dtype=np.float32)

        f32 = frame.astype(np.float32)
        sepia_frame = np.clip(f32 @ sepia.T, 0, 255)

        blended = cv2.addWeighted(
            f32,          1.0 - self.sepia_amount,
            sepia_frame,  self.sepia_amount,
            0,
        )
        return blended.astype(np.uint8)

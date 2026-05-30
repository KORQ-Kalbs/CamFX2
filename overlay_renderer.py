"""
overlay_renderer.py
--------------------
Maps decorative eye-overlay artwork onto detected eye positions in real-time.

Overlay placement logic
-----------------------
Each overlay PNG has a natural "eye opening" — the transparent window where
the real eye is meant to show through.  We derive the anchor from the centre
of the largest transparent hole in the image, then fit the overlay so that
the hole width roughly matches the detected eye width.

When rendering, the anchor is aligned to the detected iris centre, then the
overlay is:
    • Scaled  so the eye window width ~= measured eye width
  • Rotated to match the head tilt angle (so it stays aligned even when the
    person tilts their head)
  • Alpha-composited onto the frame using the PNG's own alpha channel

The renderer composites the PNG alpha channel onto the frame, so the no-bg
variants are preferred when available.
"""

import cv2
import numpy as np
import math
import os


DEFAULT_HOLE_FIT = 2.80


class OverlayRenderer:
    """
    Loads overlay PNGs once and composites them onto frames at runtime.

    Parameters
    ----------
    overlay_paths : list[str]
        Paths to RGBA PNG overlay images in order [teal, red].
    """

    def __init__(self, overlay_paths: list):
        # _overlays: list of dicts with keys 'right' and 'left' (np.ndarray BGRA)
        # _configs: list of dicts with keys 'right' and 'left' (anchor + eye_scale)
        self._overlays = []
        self._configs = []
        for path in overlay_paths:
            right_img = cv2.imread(path, cv2.IMREAD_UNCHANGED)   # BGRA or BGR
            if right_img is None:
                right_img = self._make_placeholder(400, 240, path)
            if right_img.shape[2] == 3:
                alpha = np.full((*right_img.shape[:2], 1), 255, dtype=np.uint8)
                right_img = np.concatenate([right_img, alpha], axis=2)
            right_img = right_img.astype(np.uint8)

            # Try to find an explicit left-side asset with suffix '_reverse'
            base, ext = os.path.splitext(path)
            left_path = f"{base}_reverse{ext}"
            left_img = None
            if os.path.exists(left_path):
                left_img = cv2.imread(left_path, cv2.IMREAD_UNCHANGED)
                if left_img is None:
                    left_img = self._make_placeholder(400, 240, left_path)
                if left_img.shape[2] == 3:
                    alpha = np.full((*left_img.shape[:2], 1), 255, dtype=np.uint8)
                    left_img = np.concatenate([left_img, alpha], axis=2)
                left_img = left_img.astype(np.uint8)
            else:
                # No explicit left asset; we'll create one by flipping the right image
                left_img = cv2.flip(right_img, 1)

            self._overlays.append({
                'right': right_img,
                'left': left_img,
            })

            cfg_right = self._derive_config(right_img, path)
            if os.path.exists(left_path):
                cfg_left = self._derive_config(left_img, left_path)
            else:
                # Mirror the anchor x for the generated left image
                ax, ay = cfg_right['anchor']
                cfg_left = {
                    'anchor': (1.0 - ax, ay),
                    'eye_scale': cfg_right['eye_scale'],
                }
            # Add optional per-overlay vertical shift (fraction of overlay height)
            # Use a small downward shift for 'red' assets so it sits lower.
            cfg_right.setdefault('vshift', 0.0)
            cfg_left.setdefault('vshift', 0.0)
            if 'red' in path.lower():
                cfg_right['vshift'] = 0.01
                cfg_left['vshift'] = 0.01

            self._configs.append({
                'right': cfg_right,
                'left': cfg_left,
            })

    # ── public API ────────────────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        eye_data,
        overlay_index: int,
    ) -> np.ndarray:
        """
        Composite the selected overlay onto both eyes in `frame`.
        `frame` is BGR uint8 and is modified in-place (copy externally if needed).
        """
        if overlay_index >= len(self._overlays):
            return frame

        overlay_pair = self._overlays[overlay_index]
        cfg_pair = self._configs[overlay_index]

        # Prepare stamps (resized images + top-left positions) but don't
        # composite yet — this lets us detect overlap and add a gap.
        left_stamp = None
        right_stamp = None

        if eye_data.left_center and eye_data.left_width > 4:
            overlay_img = overlay_pair['right']
            cfg = cfg_pair['right']
            left_stamp = self._prepare_stamp(
                overlay_img, cfg['anchor'], cfg['eye_scale'],
                eye_data.left_center, eye_data.left_width, eye_data.head_tilt_angle,
                vshift=cfg.get('vshift', 0.0),
                side='left',
            )

        if eye_data.right_center and eye_data.right_width > 4:
            overlay_img = overlay_pair['left']
            cfg = cfg_pair['left']
            right_stamp = self._prepare_stamp(
                overlay_img, cfg['anchor'], cfg['eye_scale'],
                eye_data.right_center, eye_data.right_width, eye_data.head_tilt_angle,
                vshift=cfg.get('vshift', 0.0),
                side='right',
            )

        # If both stamps exist, ensure they don't horizontally overlap.
        if left_stamp is not None and right_stamp is not None:
            l_img, l_x, l_y = left_stamp
            r_img, r_x, r_y = right_stamp
            l_w = l_img.shape[1]
            r_w = r_img.shape[1]

            # compute current overlap (positive if overlapping)
            overlap = (l_x + l_w) - r_x
            if overlap >= 0:
                # push them apart equally with a small extra gap
                extra = max(int(min(l_w, r_w) * 0.03), 3)  # 4% or at least 4px
                shift = (overlap // 2) + extra
                l_x -= shift
                r_x += shift
                left_stamp = (l_img, l_x, l_y)
                right_stamp = (r_img, r_x, r_y)

        # Composite in back-to-front order (left then right)
        if left_stamp is not None:
            img, x, y = left_stamp
            frame = self._alpha_blend(frame, img, x, y)
        if right_stamp is not None:
            img, x, y = right_stamp
            frame = self._alpha_blend(frame, img, x, y)

        return frame

    # ── internal helpers ──────────────────────────────────────────────────

    def _stamp(
        self,
        frame: np.ndarray,
        overlay: np.ndarray,
        anchor: tuple,
        eye_scale: float,
        eye_center: tuple,
        eye_width: int,
        tilt_deg: float,
        side: str = 'right',
    ) -> np.ndarray:
        """Resize → rotate → alpha-blend a single overlay stamp."""

        target_w = int(eye_width * eye_scale)
        if target_w < 30:
            return frame

        oh, ow = overlay.shape[:2]
        target_h = int(oh * target_w / ow)

        # 1. Resize
        resized = cv2.resize(
            overlay, (target_w, target_h),
            interpolation=cv2.INTER_LINEAR,
        )

        # 2. Rotate (if head is tilted)
        if abs(tilt_deg) > 0.5:
            resized = self._rotate_bgra(resized, tilt_deg)

        rh, rw = resized.shape[:2]

        # 3. Compute top-left so that anchor maps to eye_center
        ax, ay = anchor

        # Apply a small symmetric horizontal nudge per-eye so the artwork sits
        # slightly outside the iris on each side. Use small equal magnitudes
        # to avoid one side consistently appearing better than the other.
        if side == 'left':
            HORIZONTAL_SHIFT_FRAC = -0.03
        else:
            HORIZONTAL_SHIFT_FRAC = 0.03
        delta_x = int(rw * HORIZONTAL_SHIFT_FRAC)

        tlx = int(eye_center[0] - ax * rw + delta_x)
        tly = int(eye_center[1] - ay * rh)

        # 4. Alpha-composite
        return self._alpha_blend(frame, resized, tlx, tly)

    def _prepare_stamp(
        self,
        overlay: np.ndarray,
        anchor: tuple,
        eye_scale: float,
        eye_center: tuple,
        eye_width: int,
        tilt_deg: float,
        vshift: float = 0.0,
        side: str = 'right',
    ):
        """Return (resized_img, tlx, tly) without compositing."""
        target_w = int(eye_width * eye_scale)
        if target_w < 30:
            return None

        oh, ow = overlay.shape[:2]
        target_h = int(oh * target_w / ow)

        resized = cv2.resize(overlay, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        if abs(tilt_deg) > 0.5:
            resized = self._rotate_bgra(resized, tilt_deg)

        rh, rw = resized.shape[:2]
        ax, ay = anchor
        if side == 'left' and False:
            # kept for historical context; explicit left assets are used
            resized = cv2.flip(resized, 1)
            ax = 1.0 - ax

        # per-side base horizontal shift (will be adjusted if overlap detected)
        if side == 'left':
            HORIZONTAL_SHIFT_FRAC = -0.03
        else:
            HORIZONTAL_SHIFT_FRAC = 0.03
        delta_x = int(rw * HORIZONTAL_SHIFT_FRAC)

        # Apply a small vertical lift so overlays sit slightly higher than
        # the detected iris center. This is a fraction of the overlay
        # height; negative moves the stamp upward. Base lift is -2% and
        # we add any per-overlay vshift (positive moves stamp down).
        BASE_VERTICAL_SHIFT_FRAC = -0.02
        total_vshift = BASE_VERTICAL_SHIFT_FRAC + float(vshift)
        delta_y = int(rh * total_vshift)

        tlx = int(eye_center[0] - ax * rw + delta_x)
        tly = int(eye_center[1] - ay * rh + delta_y)
        return (resized, tlx, tly)

    @staticmethod
    def _rotate_bgra(img: np.ndarray, angle_deg: float) -> np.ndarray:
        """
        Rotate a BGRA image around its centre.
        The output canvas expands to fit the rotated content.
        """
        h, w = img.shape[:2]
        cx, cy = w / 2, h / 2

        M = cv2.getRotationMatrix2D((cx, cy), -angle_deg, 1.0)

        cos_a = abs(M[0, 0])
        sin_a = abs(M[0, 1])
        new_w = int(h * sin_a + w * cos_a)
        new_h = int(h * cos_a + w * sin_a)

        M[0, 2] += new_w / 2 - cx
        M[1, 2] += new_h / 2 - cy

        return cv2.warpAffine(
            img, M, (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )

    @staticmethod
    def _alpha_blend(
        bg: np.ndarray,
        overlay_bgra: np.ndarray,
        x: int,
        y: int,
    ) -> np.ndarray:
        """
        Alpha-composite overlay_bgra onto bg (BGR) at pixel (x, y).
        Clips gracefully at frame boundaries.
        """
        bg_h, bg_w = bg.shape[:2]
        ov_h, ov_w = overlay_bgra.shape[:2]

        # Compute source crop (handles cases where overlay extends off-screen)
        src_x1 = max(0, -x)
        src_y1 = max(0, -y)
        src_x2 = ov_w - max(0, (x + ov_w) - bg_w)
        src_y2 = ov_h - max(0, (y + ov_h) - bg_h)

        dst_x1 = max(0, x)
        dst_y1 = max(0, y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        if src_x2 <= src_x1 or src_y2 <= src_y1:
            return bg
        if dst_x2 <= dst_x1 or dst_y2 <= dst_y1:
            return bg

        roi_ov = overlay_bgra[src_y1:src_y2, src_x1:src_x2]
        roi_bg = bg[dst_y1:dst_y2, dst_x1:dst_x2]

        # Per-pixel alpha blend
        a = roi_ov[:, :, 3:4].astype(np.float32) / 255.0
        fg = roi_ov[:, :, :3].astype(np.float32)
        bg_roi = roi_bg.astype(np.float32)

        blended = bg_roi * (1.0 - a) + fg * a
        bg[dst_y1:dst_y2, dst_x1:dst_x2] = np.clip(blended, 0, 255).astype(np.uint8)

        return bg

    @staticmethod
    def _derive_config(img: np.ndarray, path: str) -> dict:
        """
        Estimate the eye-window anchor and a fit scale from the overlay alpha.

        The largest internal transparent region is treated as the eye opening.
        """
        alpha = img[:, :, 3]
        height, width = alpha.shape

        flood = alpha.copy()
        mask = np.zeros((height + 2, width + 2), np.uint8)
        cv2.floodFill(flood, mask, (0, 0), 255)
        holes = cv2.bitwise_not(flood)

        component_mask = (holes > 0).astype(np.uint8)
        num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(
            component_mask,
            connectivity=8,
        )

        best_component = None
        for label in range(1, num_labels):
            x, y, comp_width, comp_height, area = stats[label]
            if area < 1000:
                continue
            if x == 0 or y == 0 or x + comp_width == width or y + comp_height == height:
                continue
            if best_component is None or area > best_component[0]:
                best_component = (area, x, y, comp_width, comp_height, centroids[label])

        if best_component is not None:
            _, _, _, comp_width, _, centroid = best_component
            hole_fraction = max(comp_width / float(width), 1e-3)
            return {
                "anchor": (float(centroid[0] / width), float(centroid[1] / height)),
                "eye_scale": float(DEFAULT_HOLE_FIT / hole_fraction),
            }

        # Fallback if the alpha mask cannot be analyzed.
        fallback = (0.5, 0.5) if 'teal' in path else (0.5, 0.5)
        return {
            "anchor": fallback,
            "eye_scale": DEFAULT_HOLE_FIT,
        }

    @staticmethod
    def _make_placeholder(w: int, h: int, path: str) -> np.ndarray:
        """Return a placeholder BGRA image when an asset file is missing."""
        img = np.zeros((h, w, 4), dtype=np.uint8)
        colour = (80, 200, 180, 200) if 'teal' in path else (60, 60, 180, 200)
        # Draw a simple eye almond outline
        cv2.ellipse(img, (w // 2, h // 2), (w // 3, h // 5),
                    0, 0, 360, colour, 3, cv2.LINE_AA)
        cv2.line(img, (w // 4, h // 2), (3 * w // 4, h // 2),
                 colour, 2, cv2.LINE_AA)
        return img

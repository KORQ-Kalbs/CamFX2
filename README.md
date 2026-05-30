# RetroCam 🐟✨

**A retro-styled mobile camera app with real-time eye-tracking AR overlays.**

Inspired by the chalk-fish eye illustrations in `ahay.jpeg` and `ahayrevert.jpeg`.

---

## Overview

RetroCam overlays decorative fish-spirit artwork onto both eyes in the live camera feed, aligned and scaled in real time via MediaPipe face tracking. A full vintage/CRT post-processing stack is applied to every frame for an atmospheric, hand-drawn look.

---

## Screenshots (reference)

| Teal Spirit             | Red Phantom            |
| ----------------------- | ---------------------- |
| `overlay_teal_nobg.png` | `overlay_red_nobg.png` |

The overlays replicate the aesthetic of `ahay.jpeg` — the fish art anchors to each iris, rotates with head tilt, and the retro filter unifies the composited result.

---

## Architecture

```
main.py                      ← KivyMD app entry, ScreenManager
│
├── screens/
│   ├── camera_screen.py     ← Live viewfinder UI + controls
│   └── preview_screen.py    ← Photo preview + save to gallery
│
├── camera_processor.py      ← Background thread: frame capture + pipeline
│   │
│   ├── eye_tracker.py       ← MediaPipe Face Landmarker (iris centres, eye dims, tilt)
│   ├── retro_filter.py      ← CRT effects: chroma aberr. / scanlines / vignette / grain / sepia
│   └── overlay_renderer.py  ← AR compositing: resize → rotate → alpha-blend
│
└── assets/
    ├── face_landmarker.task  ← MediaPipe face model (downloaded/cached for desktop)
  ├── overlay_teal_nobg.png ← Teal spirit fish without background
  └── overlay_red_nobg.png  ← Red phantom fish without background
```

### Processing pipeline (per frame, ~30 fps)

```
Camera → flip(mirror) → EyeTracker.detect()
                               │
                    ┌──────────┴──────────┐
                    │  EyeData            │
                    │  left/right centre  │
                    │  widths / heights   │
                    │  head_tilt_angle    │
                    └──────────┬──────────┘
                               │
                    OverlayRenderer.render()
                      • anchor → iris centre
                      • scale  = eye_width × 5.5–5.8
                      • rotate = head_tilt_angle
                      • alpha-composite BGRA → BGR
                               │
                    RetroFilter.apply()
                      1. chromatic_aberration  (±3 px R/B shift)
                      2. scanlines             (every 3rd row, 35 % dark)
                      3. vignette              (radial, 60 % strength)
                      4. film grain            (±14 intensity)
                      5. sepia_tint            (22 % wash)
                               │
                    BGR → RGB → Kivy Texture → viewfinder
```

### Eye landmark mapping

MediaPipe Face Mesh returns 468 + 10 iris landmarks per face.  
Key indices used:

| Purpose               | Left eye | Right eye |
| --------------------- | -------- | --------- |
| Iris centre (primary) | 468      | 473       |
| Inner corner          | 133      | 362       |
| Outer corner          | 33       | 263       |
| Eyelid top            | 159      | 386       |
| Eyelid bottom         | 145      | 374       |

Head tilt = `atan2(dy, dx)` between the two iris centres.

### Overlay anchor calibration

Each overlay PNG has a natural "eye window" — the almond-shaped dark region that shows the real eye through. The `OVERLAY_CONFIGS` dict in `overlay_renderer.py` defines where this window sits as a fraction of the image:

```python
OVERLAY_CONFIGS = [
    {"anchor": (0.62, 0.50), "eye_scale": 5.8},  # teal fish
    {"anchor": (0.57, 0.62), "eye_scale": 5.5},  # red fish
]
```

If the overlays look misaligned for your artwork, adjust these fractions by visually inspecting where the eye opening centre is relative to the full image dimensions.

---

## Desktop setup (development)

### Prerequisites

- Python 3.13 on Windows (current desktop setup) or Python 3.11+
- A webcam
- Ubuntu / macOS / Windows with a GPU (MediaPipe runs on CPU too, just slower)

### Install

```bash
# Clone / download the project
cd retro_eye_cam

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy your overlay assets (if not already present)
cp /path/to/1.png assets/overlay_teal.png
cp /path/to/2.png assets/overlay_red.png

# Run
python main.py
```

The app window opens at 390 × 844 px (iPhone-like portrait aspect ratio).

### Controls

| Button         | Action                                |
| -------------- | ------------------------------------- |
| 🐟 (teal)      | Activate teal spirit overlay          |
| 🐟 (red)       | Activate red phantom overlay          |
| 👁 off         | Disable overlay (camera + retro only) |
| 📺 icon        | Toggle retro CRT filter on/off        |
| ● capture      | Snapshot (navigate to preview)        |
| Preview → SAVE | Save JPEG to `~/Pictures/RetroCam/`   |

---

## Android APK build

### System requirements

- Ubuntu 20.04 / 22.04 (native or WSL2 on Windows)
- Java JDK 17
- buildozer 1.5+

### Install buildozer

```bash
pip install buildozer cython

# Ubuntu dependencies
sudo apt-get install -y \
  python3-pip build-essential git python3 python3-dev \
  ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
  libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev \
  libavcodec-dev zlib1g-dev libgstreamer1.0 gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good libltdl-dev autoconf libtool \
  libffi-dev openjdk-17-jdk
```

### Build debug APK

```bash
cd retro_eye_cam
buildozer android debug
```

The first build downloads the Android SDK, NDK, and all dependencies — expect 20–40 minutes. Subsequent builds are cached and take 3–5 minutes.

Output APK: `.buildozer/android/platform/build-arm64-v8a/dists/retrocam/bin/RetroCam-1.0.0-arm64-v8a-debug.apk`

### Deploy to device

```bash
# Install ADB if needed
sudo apt-get install android-tools-adb

# Enable USB debugging on your phone, then:
adb install *.apk

# Or deploy + launch in one step:
buildozer android debug deploy run logcat
```

### Release build

```bash
# Generate a signing key (once)
keytool -genkey -v -keystore retrocam.keystore \
        -alias retrocam -keyalg RSA -keysize 2048 -validity 10000

# Build signed release APK
buildozer android release
```

Sign with `apksigner` or `jarsigner` before distributing.

---

## Tuning & customisation

### Change overlay scale

Edit `eye_scale` in `OVERLAY_CONFIGS` inside `overlay_renderer.py`:

- Larger value → overlay grows relative to eye size
- Recommended range: 4.0 – 7.0

### Change retro intensity

All parameters are adjustable in `RetroFilter.__init__()`:

```python
RetroFilter(
    chroma_strength   = 3,     # px offset of R/B channels; 0 = off
    scanline_gap      = 3,     # rows between scanlines; higher = subtler
    scanline_alpha    = 0.35,  # darkness of scanlines; 0.0–1.0
    vignette_strength = 0.60,  # edge darkening; 0.0–1.0
    grain_intensity   = 14,    # noise ±px; 0 = off
    sepia_amount      = 0.22,  # sepia blend; 0.0 = colour, 1.0 = full sepia
)
```

### Add more overlays

1. Add your PNG to `assets/`
2. Append an entry to `OVERLAY_CONFIGS` in `overlay_renderer.py`
3. Add a button in `screens/camera_screen.py` calling `self.set_overlay(new_index)`
4. Update `OVERLAY_LABELS` and `OVERLAY_COLOURS`

### Front vs rear camera (Android)

In `main.py` or `camera_screen.py`, pass `camera_index=1` to  
`processor.start(camera_index=1)` for the front-facing selfie camera.

---

## Known limitations & tips

- **MediaPipe accuracy**: Face Mesh performs best with adequate lighting and a clear front-facing view. For rear-camera use, remove the `cv2.flip(frame, 1)` mirror in `camera_processor.py`.
- **Performance on older phones**: Reduce `TARGET_FPS` to 20 and set `max_num_faces=1` (already default). Disable retro filter on low-end devices.
- **Android camera permission**: The first launch will request the `CAMERA` permission. If denied, the app shows a black viewfinder — grant permission in Settings → Apps → RetroCam.
- **Buildozer mediapipe**: The `mediapipe` recipe in python-for-android may not be listed by default — you may need to use the `--local-recipes` flag pointing to a custom recipe directory, or install the pre-built wheel via `p4a.pip_requirements`. See the [p4a docs](https://python-for-android.readthedocs.io/en/latest/).

---

## File manifest

```
retro_eye_cam/
├── main.py
├── camera_processor.py
├── eye_tracker.py
├── retro_filter.py
├── overlay_renderer.py
├── screens/
│   ├── __init__.py
│   ├── camera_screen.py
│   └── preview_screen.py
├── assets/
│   ├── overlay_teal.png    ← copy of 1.png
│   └── overlay_red.png     ← copy of 2.png
├── requirements.txt
├── buildozer.spec
└── README.md
```

[app]

# ── Identity ────────────────────────────────────────────────────────────────
title           = RetroCam
package.name    = retrocam
package.domain  = com.kafkhabian
version         = 1.0.0

# ── Source ──────────────────────────────────────────────────────────────────
source.dir      = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,txt

# ── Entry point ─────────────────────────────────────────────────────────────
# The main.py at root is automatically found by buildozer.

# ── Orientation & display ───────────────────────────────────────────────────
orientation = portrait
fullscreen  = 0

# ── Android SDK/NDK ─────────────────────────────────────────────────────────
android.api             = 33
android.minapi          = 26
android.ndk             = 25b
android.sdk             = 33
android.accept_sdk_license = True

# ── Architecture ────────────────────────────────────────────────────────────
# Build for modern 64-bit devices. Add armeabi-v7a for older phones if needed.
android.archs = arm64-v8a

# ── Permissions ─────────────────────────────────────────────────────────────
android.permissions =
    CAMERA,
    READ_EXTERNAL_STORAGE,
    WRITE_EXTERNAL_STORAGE,
    READ_MEDIA_IMAGES

# ── Python requirements ─────────────────────────────────────────────────────
#
# IMPORTANT: mediapipe ships prebuilt Android wheels for arm64-v8a.
# opencv-python is provided as a p4a recipe (no compilation needed).
# numpy must be <2.0 to stay compatible with the mediapipe release.
#
requirements =
    python3,
    kivy==2.3.0,
    kivymd==1.2.0,
    numpy,
    opencv,
    mediapipe,
    pillow,
    pyjnius,
    plyer

# ── p4a (python-for-android) configuration ──────────────────────────────────
#
# mediapipe provides ARM64 wheels on PyPI — tell p4a to use them directly.
p4a.local_recipes      =
p4a.bootstrap          = sdl2

# Pre-download the mediapipe wheel for arm64 (buildozer will cache it)
# Adjust the version tag to match the latest mediapipe release if needed.
android.add_aars =

# ── Icons & splash ──────────────────────────────────────────────────────────
# Replace these paths with actual icon files for production.
# android.icon.filename        = %(source.dir)s/assets/icon.png
# android.presplash.filename   = %(source.dir)s/assets/splash.png
# android.presplash_color      = #000000

# ── Build output ────────────────────────────────────────────────────────────
android.release_artifact = apk

# ── Debug options ───────────────────────────────────────────────────────────
log_level = 2
warn_on_root = 1

[buildozer]
# Buildozer working directory (cache, build artefacts)
buildozer_dir = .buildozer

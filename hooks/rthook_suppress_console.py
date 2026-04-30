# hooks/rthook_suppress_console.py
#
# PyInstaller runtime hook — runs before any application code.
# Patches subprocess.Popen to always set CREATE_NO_WINDOW on Windows
# so no console windows appear from any subprocess spawned by the app
# or its dependencies (TensorFlow, DeepFace, YOLO, ffmpeg, etc.)

import sys

if sys.platform == "win32":
    import subprocess

    _original_popen_init = subprocess.Popen.__init__
    _CREATE_NO_WINDOW = 0x08000000

    def _patched_popen_init(self, *args, **kwargs):
        # Always add CREATE_NO_WINDOW to creationflags
        flags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = flags | _CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init
# tools/

Place `ffmpeg.exe` here before building the installer.

Download: https://www.gyan.dev/ffmpeg/builds/
Use the **essentials** build — `ffmpeg-release-essentials.zip`
Extract `ffmpeg.exe` from the `bin/` folder into this directory.

When bundled, `ffmpeg.exe` is placed in the root of `dist/AESTHETIC/`
and added to PATH automatically at startup via `app.py:_setup_bundle_env()`.

If `tools/ffmpeg.exe` is absent at build time, the app will fall back
to any `ffmpeg` found on the system PATH. Distribution without a bundled
ffmpeg will require users to install ffmpeg separately.

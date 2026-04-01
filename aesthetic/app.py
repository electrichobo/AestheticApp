# aesthetic/app.py
#
# Boot shell only. Opens the pywebview window and hands it AestheticAPI.
# All business logic lives in aesthetic/bridge/api.py.
#
# Works in three contexts:
#   - Development: python -m aesthetic.app
#   - PyInstaller bundle: AESTHETIC.exe
#   - macOS/Linux packaged app

import sys
import os
from pathlib import Path


def _setup_bundle_env() -> None:
    """
    When running from a PyInstaller bundle, ensure ffmpeg/ffprobe
    (bundled in the same directory as the .exe) are on PATH.
    Also set the multiprocessing start method to avoid spawning issues.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # add bundle directory to PATH so ffmpeg subprocess calls work
        os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")

        # on Windows, multiprocessing spawn can conflict with PyInstaller
        # freeze_support() must be called before any multiprocessing
        import multiprocessing
        multiprocessing.freeze_support()


def main() -> None:
    _setup_bundle_env()

    import webview

    # use absolute imports when frozen (PyInstaller), relative when running as module
    if getattr(sys, "frozen", False):
        from aesthetic.bridge.api import AestheticAPI
        from aesthetic.config import WEB_DIR
    else:
        from .bridge.api import AestheticAPI
        from .config import WEB_DIR

    APP_NAME = "AESTHETIC"

    api    = AestheticAPI()

    # In a frozen bundle, use http_server=True so pywebview serves the HTML
    # via localhost rather than file:// URI — this ensures the JS bridge
    # (window.pywebview.api) initialises correctly in the WebView2 context.
    use_http = getattr(sys, "frozen", False)

    window = webview.create_window(
        APP_NAME,
        str(WEB_DIR / "index.html") if use_http else (WEB_DIR / "index.html").as_uri(),
        width=1280,
        height=860,
        resizable=True,
        js_api=api,
    )
    # store window reference so open_file_dialog can access it
    api._window = window
    webview.start(http_server=use_http)


if __name__ == "__main__":
    main()
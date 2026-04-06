# aesthetic/app.py
#
# Boot shell only. Opens the pywebview window and hands it AestheticAPI.
# All business logic lives in aesthetic/bridge/api.py.
#
# Works in three contexts:
#   - Development: python -m aesthetic.app  (file:// URI, video preview works)
#   - PyInstaller bundle: AESTHETIC.exe     (http_server, bridge init reliable)
#   - macOS/Linux packaged app

import sys
import os
from pathlib import Path


def _setup_bundle_env() -> None:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")
        import multiprocessing
        multiprocessing.freeze_support()


def main() -> None:
    _setup_bundle_env()

    import webview

    if getattr(sys, "frozen", False):
        from aesthetic.bridge.api import AestheticAPI
        from aesthetic.config import WEB_DIR
    else:
        from .bridge.api import AestheticAPI
        from .config import WEB_DIR

    APP_NAME = "AESTHETIC"
    frozen   = getattr(sys, "frozen", False)

    # Dev: file:// so local video preview works natively
    # Bundle: string path + http_server=True for reliable WebView2 bridge init
    html_url = str(WEB_DIR / "index.html") if frozen else (WEB_DIR / "index.html").as_uri()

    api    = AestheticAPI()
    window = webview.create_window(
        APP_NAME,
        html_url,
        width=1280,
        height=860,
        resizable=True,
        js_api=api,
    )
    api._window = window
    webview.start(http_server=frozen)


if __name__ == "__main__":
    main()
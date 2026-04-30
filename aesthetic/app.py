# aesthetic/app.py
#
# Boot shell only. Opens the pywebview window and hands it AestheticAPI.
# All business logic lives in aesthetic/bridge/api.py.
#
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")   # suppress TF info/warning noise
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

    # Print startup info — visible in console window during debugging
    frozen = getattr(sys, "frozen", False)
    meipass = getattr(sys, "_MEIPASS", None)
    print(f"[app] frozen={frozen}, _MEIPASS={meipass}")
    print(f"[app] Python {sys.version}")
    print(f"[app] executable: {sys.executable}")

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
        min_size=(900, 600),
        resizable=True,
        js_api=api,
    )
    api._window = window

    start_kwargs: dict = {}
    if frozen:
        # Bundle: use EdgeChromium (WebView2) explicitly for reliable JS bridge
        # http_server serves files so WebView2 security allows pywebview API calls
        start_kwargs["gui"]         = "edgechromium"
        start_kwargs["http_server"] = True

    try:
        webview.start(**start_kwargs)
    except Exception as _e:
        # EdgeChromium not available — fall back to default
        print(f"[app] edgechromium start failed ({_e}), retrying with default GUI")
        webview.start(http_server=frozen)
    # Ensure process exits cleanly — pywebview can leave threads running
    # on Windows which prevents the terminal from releasing
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
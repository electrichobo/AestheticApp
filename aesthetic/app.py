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

    print("[app] importing webview...")
    import webview

    print("[app] importing AestheticAPI...")
    if getattr(sys, "frozen", False):
        from aesthetic.bridge.api import AestheticAPI
        from aesthetic.config import WEB_DIR
    else:
        from .bridge.api import AestheticAPI
        from .config import WEB_DIR

    APP_NAME = "AESTHETIC"
    frozen   = getattr(sys, "frozen", False)

    print(f"[app] WEB_DIR: {WEB_DIR}")
    print(f"[app] WEB_DIR exists: {WEB_DIR.exists()}")

    html_url = str(WEB_DIR / "index.html") if frozen else (WEB_DIR / "index.html").as_uri()
    print(f"[app] html_url: {html_url}")

    print("[app] instantiating AestheticAPI...")
    try:
        api = AestheticAPI()
        print("[app] AestheticAPI ready")
    except Exception as _api_exc:
        import traceback
        print(f"[app] AestheticAPI FAILED: {_api_exc}")
        traceback.print_exc()
        input("Press Enter to exit...")
        return

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

    if frozen:
        print("[app] starting webview (bundle mode)...")
        # Try edgechromium without http_server first — most reliable for JS bridge
        # http_server can cause bridge injection timing issues in some environments
        try:
            print("[app] attempting edgechromium without http_server...")
            webview.start(gui="edgechromium")
        except Exception as _e1:
            print(f"[app] attempt 1 failed: {_e1}")
            try:
                print("[app] attempting edgechromium with http_server...")
                webview.start(gui="edgechromium", http_server=True)
            except Exception as _e2:
                print(f"[app] attempt 2 failed: {_e2}")
                print("[app] falling back to default GUI...")
                webview.start()
    else:
        webview.start()
    # Ensure process exits cleanly — pywebview can leave threads running
    # on Windows which prevents the terminal from releasing
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
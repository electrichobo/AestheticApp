# aesthetic/app.py
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import sys
from pathlib import Path


def _setup_bundle_env() -> None:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")
        import multiprocessing
        multiprocessing.freeze_support()


def main() -> None:
    _setup_bundle_env()

    frozen = getattr(sys, "frozen", False)
    print(f"[app] frozen={frozen}")
    print(f"[app] Python {sys.version.split()[0]}")

    print("[app] importing webview...")
    import webview

    print("[app] importing AestheticAPI...")
    if frozen:
        from aesthetic.bridge.api import AestheticAPI
        from aesthetic.config import WEB_DIR
    else:
        from .bridge.api import AestheticAPI
        from .config import WEB_DIR

    print(f"[app] WEB_DIR: {WEB_DIR} (exists={WEB_DIR.exists()})")

    # Always pass the raw file path — pywebview with http_server=True
    # will start its own local HTTP server and convert this to http://localhost:PORT/
    # This is the only reliable way to get bridge injection on Windows/EdgeChromium
    html_path = str(WEB_DIR / "index.html")
    print(f"[app] html_path: {html_path}")

    print("[app] instantiating AestheticAPI...")
    try:
        api = AestheticAPI()
        print("[app] AestheticAPI ready")
    except Exception as exc:
        import traceback
        print(f"[app] AestheticAPI FAILED: {exc}")
        traceback.print_exc()
        input("Press Enter to exit...")
        return

    window = webview.create_window(
        "AESTHETIC",
        html_path,
        width=1280,
        height=860,
        min_size=(900, 600),
        resizable=True,
        js_api=api,
    )
    api._window = window

    print("[app] starting webview with http_server=True...")
    # http_server=True is required for pywebview to inject window.pywebview
    # on Windows with the EdgeChromium (WebView2) backend
    webview.start(http_server=True)

    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
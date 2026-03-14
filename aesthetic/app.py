# aesthetic/app.py
#
# Boot shell only. Opens the pywebview window and hands it AestheticAPI.
# All business logic lives in aesthetic/bridge/api.py.

import webview

from .bridge.api import AestheticAPI
from .config import WEB_DIR

APP_NAME = "AESTHETIC"


def main() -> None:
    api    = AestheticAPI()
    window = webview.create_window(
        APP_NAME,
        (WEB_DIR / "index.html").as_uri(),
        width=1280,
        height=860,
        resizable=True,
        js_api=api,
    )
    # store window reference so open_file_dialog can access it
    api._window = window
    webview.start(http_server=False)


if __name__ == "__main__":
    main()
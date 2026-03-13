# aesthetic/app.py
#
# Boot shell only. This file does ONE thing: open the pywebview desktop window
# and hand it the canonical API from bridge/api.py.
#
# Do not add config logic, baseline logic, job handling, or any other
# business logic here. All of that lives in aesthetic/bridge/api.py.

import webview

from .bridge.api import AestheticAPI
from .config import WEB_DIR

APP_NAME = "AESTHETIC"


def main() -> None:
    api = AestheticAPI()
    webview.create_window(
        APP_NAME,
        (WEB_DIR / "index.html").as_uri(),
        width=1280,
        height=820,
        resizable=True,
        js_api=api,
    )
    webview.start(http_server=False)


if __name__ == "__main__":
    main()
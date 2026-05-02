# aesthetic/app.py
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import sys
from pathlib import Path


def _setup_bundle_env() -> None:
    if getattr(sys, "frozen", False):
        exe_dir  = Path(sys.executable).parent
        internal = Path(sys._MEIPASS)

        # Add all directories needed for CUDA DLL discovery
        cuda_paths = [
            str(exe_dir),
            str(internal / "torch" / "lib"),        # CUDA runtime DLLs
            str(internal / "torch" / "bin"),
            str(internal),
        ]
        existing = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(cuda_paths) + os.pathsep + existing

        # Tell PyTorch where to find CUDA
        os.environ.setdefault("CUDA_PATH", str(internal / "torch" / "lib"))

        import multiprocessing
        multiprocessing.freeze_support()


def _seed_baseline_if_needed() -> None:
    """
    On first run, copy the bundled baseline embeddings to the user data directory
    if the user data directory has no valid baseline yet.
    Only runs in frozen (bundled) mode.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        from aesthetic.config import DATA_DIR
        user_emb = DATA_DIR / "baseline" / "embeddings"
        # Check if user already has 1152-dim embeddings
        if user_emb.exists():
            existing = list(user_emb.glob("*.json"))
            if existing:
                import json
                sample = json.loads(existing[0].read_text(encoding="utf-8"))
                if len(sample.get("embedding", [])) == 1152:
                    print("[app] baseline already seeded — skipping")
                    return

        # Find bundled baseline
        import sys as _sys
        bundle_emb = Path(_sys._MEIPASS) / "aesthetic" / "data" / "baseline" / "embeddings"
        bundle_golden = Path(_sys._MEIPASS) / "aesthetic" / "data" / "baseline" / "golden"
        if not bundle_emb.exists() or not any(bundle_emb.glob("*.json")):
            print("[app] no bundled baseline found — skipping seed")
            return

        import shutil
        # Copy embeddings
        user_emb.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in bundle_emb.glob("*.json"):
            dest = user_emb / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                n += 1

        # Copy golden manifest
        if bundle_golden.exists():
            user_golden = DATA_DIR / "baseline" / "golden"
            user_golden.mkdir(parents=True, exist_ok=True)
            for f in bundle_golden.glob("*"):
                dest = user_golden / f.name
                if not dest.exists():
                    shutil.copy2(f, dest)

        print(f"[app] seeded baseline: {n} embeddings copied to {user_emb}")

    except Exception as e:
        print(f"[app] baseline seed skipped: {e}")


def main() -> None:
    _setup_bundle_env()
    _seed_baseline_if_needed()

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
    webview.start(http_server=True)

    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
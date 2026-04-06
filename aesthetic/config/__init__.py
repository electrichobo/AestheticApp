# aesthetic/config/__init__.py
#
# Path resolution that works in three contexts:
#   1. Development  — running from source tree
#   2. PyInstaller  — running from frozen bundle (sys._MEIPASS)
#   3. Installed    — user data lives in AppData/Local/AESTHETIC

import sys
import os
from pathlib import Path
from typing import Dict, Any
import yaml


def _get_bundle_dir() -> Path:
    """Return the root of the PyInstaller bundle, or the repo root in dev."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


def _get_user_data_dir() -> Path:
    """Platform user data directory — always %LOCALAPPDATA%/AESTHETIC/data etc."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "AESTHETIC" / "data"


def _get_data_dir() -> Path:
    """
    Return the writable data directory.

    Frozen bundle: always uses platform user data dir (%LOCALAPPDATA%/AESTHETIC/data).

    Dev mode: uses source tree aesthetic/data/ if it has baseline embeddings
    (i.e. the developer has trained a baseline in the source tree).
    Otherwise falls back to the platform user data dir so that running
    'python -m aesthetic.app' uses the same trained baseline as the installed app.
    This fixes the (4,8) shape error caused by having zero embeddings in dev mode.
    """
    if getattr(sys, "frozen", False):
        return _get_user_data_dir()

    # development — check source tree first
    source_data = Path(__file__).resolve().parent.parent / "data"
    emb_dir = source_data / "baseline" / "embeddings"
    if emb_dir.exists() and any(emb_dir.glob("*.json")):
        return source_data

    # no embeddings in source tree — use user data dir (has the trained baseline)
    user_dir = _get_user_data_dir()
    if user_dir.exists():
        return user_dir

    # last resort: source tree (will be empty, but at least won't crash)
    return source_data


# ---------------------------------------------------------------------------
# Canonical paths
# ---------------------------------------------------------------------------
BUNDLE_DIR   = _get_bundle_dir()
PKG_DIR      = Path(__file__).resolve().parent        # aesthetic/config
BASE_DIR     = PKG_DIR.parent                          # aesthetic/
WEB_DIR      = BUNDLE_DIR / "aesthetic" / "webui"     # webui
DATA_DIR     = _get_data_dir()                         # user-writable
OUTPUTS_DIR  = DATA_DIR / "outputs"
BASELINE_DIR = DATA_DIR / "baseline"
BASELINE_PATH= BASELINE_DIR / "baseline.json"
JOBS_DIR     = DATA_DIR / "jobs"
UPLOADS_DIR  = DATA_DIR / "uploads"

# config.yaml is read-only — lives in the bundle or source
CONFIG_PATH  = BUNDLE_DIR / "aesthetic" / "config" / "config.yaml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = PKG_DIR / "config.yaml"

# ensure user-writable dirs exist
for _d in (DATA_DIR, OUTPUTS_DIR, BASELINE_DIR,
           BASELINE_DIR / "embeddings", BASELINE_DIR / "golden",
           JOBS_DIR, UPLOADS_DIR, DATA_DIR / "feedback"):
    _d.mkdir(parents=True, exist_ok=True)


def _seed_baseline_from_bundle() -> None:
    """
    On first launch of a frozen build, copy the bundled Golden Baseline
    into the user's writable data directory. Skips if already seeded.
    """
    if not getattr(sys, "frozen", False):
        return

    user_golden = BASELINE_DIR / "golden"
    if any(user_golden.glob("v*.json")):
        return  # already seeded

    exe_dir = Path(sys.executable).parent
    bundle_baseline = exe_dir / "aesthetic" / "data" / "baseline"
    if not bundle_baseline.exists():
        return

    import shutil
    try:
        for sub in ("embeddings", "golden"):
            src = bundle_baseline / sub
            dst = BASELINE_DIR / sub
            if src.exists():
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    dest_item = dst / item.name
                    if not dest_item.exists():
                        shutil.copy2(str(item), str(dest_item))
        print("[config] Golden Baseline seeded from bundle.")
    except Exception as exc:
        print(f"[config] Baseline seed warning (non-fatal): {exc}")


_seed_baseline_from_bundle()


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    return {}


def to_yaml(cfg: Dict[str, Any]) -> str:
    return yaml.safe_dump(cfg or {}, sort_keys=False, allow_unicode=True)
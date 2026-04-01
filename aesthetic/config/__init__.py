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
    """Return the root of the PyInstaller bundle, or the package dir in dev."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # running inside a PyInstaller bundle
        return Path(sys._MEIPASS)
    # development — package is at aesthetic/config/../..
    return Path(__file__).resolve().parent.parent.parent


def _get_data_dir() -> Path:
    """
    Return the user-writable data directory.
    In a bundle: %LOCALAPPDATA%/AESTHETIC/data  (Windows)
                 ~/Library/Application Support/AESTHETIC/data  (macOS)
                 ~/.local/share/AESTHETIC/data  (Linux)
    In dev: aesthetic/data (relative to source root)
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "AESTHETIC" / "data"
    # development
    return Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Canonical paths
# ---------------------------------------------------------------------------
BUNDLE_DIR   = _get_bundle_dir()
PKG_DIR      = Path(__file__).resolve().parent        # aesthetic/config
BASE_DIR     = PKG_DIR.parent                          # aesthetic/
WEB_DIR      = BUNDLE_DIR / "aesthetic" / "webui"     # webui (from bundle or source)
DATA_DIR     = _get_data_dir()                         # user-writable
OUTPUTS_DIR  = DATA_DIR / "outputs"
BASELINE_DIR = DATA_DIR / "baseline"
BASELINE_PATH= BASELINE_DIR / "baseline.json"
JOBS_DIR     = DATA_DIR / "jobs"
UPLOADS_DIR  = DATA_DIR / "uploads"

# config.yaml is read-only — lives in the bundle or source
CONFIG_PATH  = BUNDLE_DIR / "aesthetic" / "config" / "config.yaml"
if not CONFIG_PATH.exists():
    # fallback for dev layout
    CONFIG_PATH = PKG_DIR / "config.yaml"

# ensure user-writable dirs exist
for d in (DATA_DIR, OUTPUTS_DIR, BASELINE_DIR,
          BASELINE_DIR / "embeddings", BASELINE_DIR / "golden",
          JOBS_DIR, UPLOADS_DIR, DATA_DIR / "feedback"):
    d.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    return {}


def to_yaml(cfg: Dict[str, Any]) -> str:
    return yaml.safe_dump(cfg or {}, sort_keys=False, allow_unicode=True)

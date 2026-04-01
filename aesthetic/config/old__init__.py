# aesthetic/config/__init__.py
from pathlib import Path
from typing import Dict, Any
import yaml

# repo layout anchors
PKG_DIR = Path(__file__).resolve().parent          # .../aesthetic/config
BASE_DIR = PKG_DIR.parent                           # .../aesthetic
WEB_DIR = BASE_DIR / "webui"                        # .../aesthetic/webui
DATA_DIR = BASE_DIR / "data"                        # .../aesthetic/data
OUTPUTS_DIR = DATA_DIR / "outputs"                  # .../aesthetic/data/outputs
BASELINE_DIR = DATA_DIR / "baseline"                # .../aesthetic/data/baseline
BASELINE_PATH = BASELINE_DIR / "baseline.json"      # canonical baseline
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"   # .../aesthetic/config/config.yaml

# ensure dirs exist
for d in (DATA_DIR, OUTPUTS_DIR, BASELINE_DIR):
    d.mkdir(parents=True, exist_ok=True)

def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    return {}

def to_yaml(cfg: Dict[str, Any]) -> str:
    return yaml.safe_dump(cfg or {}, sort_keys=False, allow_unicode=True)

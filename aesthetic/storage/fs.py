from __future__ import annotations
from pathlib import Path
from aesthetic.config import DATA_DIR

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)

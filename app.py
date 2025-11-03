
import os
import sys
import json
import base64
import threading
import webview  # pip install pywebview
from dataclasses import dataclass, asdict
from pathlib import Path

APP_NAME = "AESTHETIC (Local Desktop)"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
BASELINE_PATH = DATA_DIR / "baseline.json"
CONFIG_PATH = BASE_DIR / "config.yaml"

@dataclass
class Shot:
    id: int
    start: float
    end: float
    totalScore: int
    scores: dict

@dataclass
class Manifest:
    source_file: str
    analysis_timestamp: str
    config: dict
    golden_baseline_summary: dict
    shots: list

class API:
    def __init__(self, window):
        self.window = window
        self.last_video_path = None
        self.last_manifest = None
        self.baseline = self._load_baseline()

    # ------- Utility -------
    def _load_baseline(self):
        if BASELINE_PATH.exists():
            try:
                return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "sampleCount": 0,
            "avgTechnical": 0.0,
            "avgSubjective": 0.0,
            "avgGranular": {
                "exposure": 0.0, "lighting": 0.0, "composition": 0.0,
                "movement": 0.0, "color": 0.0, "clarity": 0.0, "emotionalResponse": 0.0
            }
        }

    def _save_baseline(self):
        BASELINE_PATH.write_text(json.dumps(self.baseline, indent=2), encoding="utf-8")

    # ------- Bridge methods exposed to JS -------
    def ping(self):
        return {"ok": True, "name": APP_NAME}

    def get_config_yaml(self):
        if CONFIG_PATH.exists():
            return CONFIG_PATH.read_text(encoding="utf-8")
        # minimal starter
        return (
            "extract:\n"
            "  per_scene_candidates: 9\n"
            "  per_scene_keep_pct: 0.4\n"
            "  min_scene_len_frames: 12\n\n"
            "weights:\n"
            "  technical: 0.5\n"
            "  subjective: 0.5\n"
        )

    def open_file_dialog(self):
        # Let the native dialog pick a video; returns filesystem path
        file_types = ('Video files (*.mp4;*.mov;*.mkv;*.avi)', 'All files (*.*)')
        path = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if path:
            self.last_video_path = path[0]
            return {"path": self.last_video_path}
        return {"path": None}

    def analyze(self, options=None):
        """
        Pretend to run the pipeline locally. You will replace this with real calls.
        options: dict with fields like sensitivity, etc.
        """
        from datetime import datetime
        import random

        if not self.last_video_path:
            raise RuntimeError("No video selected. Use open_file_dialog first.")

        # Simulate generating some shots
        num = max(3, int((options or {}).get("numShots", 6)))
        shots = []
        t = 0.0
        for i in range(1, num+1):
            dur = random.uniform(2.0, 7.0)
            start = t
            end = t + dur
            t = end
            total = random.randint(68, 95)
            shots.append({
                "id": i,
                "start": start,
                "end": end,
                "totalScore": total,
                "scores": {
                    "exposure": {"total": random.randint(60, 95)},
                    "lighting": {"total": random.randint(60, 95)},
                    "composition": {"total": random.randint(60, 95)},
                    "movement": {"total": random.randint(60, 95)},
                    "color": {"total": random.randint(60, 95)},
                    "quality": {"total": random.randint(60, 95)},
                    "narrative": {"total": random.randint(60, 95)},
                }
            })

        manifest = {
            "source_file": os.path.basename(self.last_video_path),
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "config": {"note": "stub manifest from local desktop API"},
            "golden_baseline_summary": {
                "sample_count": self.baseline.get("sampleCount", 0),
                "avg_technical": self.baseline.get("avgTechnical", 0.0),
                "avg_subjective": self.baseline.get("avgSubjective", 0.0)
            },
            "shots": shots
        }
        self.last_manifest = manifest
        return manifest

    def export_sidecar(self):
        if not self.last_manifest:
            raise RuntimeError("Nothing to export. Run analyze first.")
        out_path = DATA_DIR / f"{Path(self.last_manifest['source_file']).stem}_run_manifest.json"
        out_path.write_text(json.dumps(self.last_manifest, indent=2), encoding="utf-8")
        return {"saved": str(out_path)}

    def export_hero(self):
        # Create a tiny fake MP4 header to satisfy the UI download
        out_path = DATA_DIR / f"{Path(self.last_manifest['source_file']).stem}_hero_scenes.mp4"
        fake = bytes([
            0x00,0x00,0x00,0x18,0x66,0x74,0x79,0x70,0x69,0x73,0x6F,0x6D,
            0x00,0x00,0x02,0x00,0x69,0x73,0x6F,0x6D,0x69,0x73,0x6F,0x32,
            0x61,0x76,0x63,0x31,0x6D,0x70,0x34,0x31,0x00,0x00,0x00,0x08,
            0x66,0x72,0x65,0x65
        ])
        out_path.write_bytes(fake)
        return {"saved": str(out_path)}

    def get_baseline(self):
        return self.baseline

    def train_baseline(self, count:int=1):
        # Bumps baseline numbers locally
        self.baseline["sampleCount"] = self.baseline.get("sampleCount", 0) + int(count)
        # naive rolling averages
        import random
        for key in ["avgTechnical", "avgSubjective"]:
            cur = self.baseline.get(key, 0.0)
            new = (cur + random.uniform(80, 95)) / 2.0 if self.baseline["sampleCount"] > 1 else random.uniform(80, 95)
            self.baseline[key] = new
        for gk in self.baseline["avgGranular"].keys():
            cur = self.baseline["avgGranular"][gk]
            new = (cur + random.uniform(75, 95)) / 2.0 if self.baseline["sampleCount"] > 1 else random.uniform(75, 95)
            self.baseline["avgGranular"][gk] = new
        self._save_baseline()
        return {"ok": True, "baseline": self.baseline}


def main():
    html = (BASE_DIR / "webui" / "index.html").as_uri()
    window = webview.create_window(APP_NAME, html, width=1280, height=820, resizable=True)
    api = API(window)
    webview.start(gui='qt', http_server=False, debug=False, func=None, private_mode=False, api=api)

if __name__ == "__main__":
    main()

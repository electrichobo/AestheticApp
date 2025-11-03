# aesthetic/app.py
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import webview  # pip install pywebview

from .config import (
    load_config,
    to_yaml,
    BASE_DIR,
    WEB_DIR,
    DATA_DIR,
    OUTPUTS_DIR,
    BASELINE_PATH,
    CONFIG_PATH,
)

APP_NAME = "AESTHETIC (Local Desktop)"

class API:
    def __init__(self, window: Optional[Any] = None):
        self.window: Optional[Any] = window
        self.cfg: Dict[str, Any] = load_config()
        self.jobs: Dict[int, Dict[str, Any]] = {}
        self.next_job_id: int = 1
        self._baseline: Dict[str, Any] = self._load_baseline()

    # -------- baseline helpers --------
    def _load_baseline(self) -> Dict[str, Any]:
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
                "exposure": 0.0,
                "lighting": 0.0,
                "composition": 0.0,
                "movement": 0.0,
                "color": 0.0,
                "clarity": 0.0,
                "emotionalResponse": 0.0,
            },
        }

    def _save_baseline(self) -> None:
        BASELINE_PATH.write_text(json.dumps(self._baseline, indent=2), encoding="utf-8")

    # -------- API used by index.html --------
    def get_config(self):
        text = to_yaml(self.cfg) if self.cfg else (
            "extract:\n"
            "  per_scene_candidates: 9\n"
            "  per_scene_keep_pct: 0.4\n"
            "  min_scene_len_frames: 12\n\n"
            "weights:\n"
            "  technical: 0.5\n"
            "  subjective: 0.5\n"
        )
        return {"ok": True, "text": text}

    def load_baseline(self):
        self._baseline = self._load_baseline()
        return {"ok": True, "baseline": self._baseline}

    def save_baseline(self, baseline_obj: Dict[str, Any]):
        if not isinstance(baseline_obj, dict):
            return {"ok": False, "error": "baseline_obj must be a dict"}
        self._baseline = baseline_obj
        self._save_baseline()
        return {"ok": True}

    def create_job(self, filename: str):
        if not filename:
            return {"ok": False, "error": "filename required"}
        job_id = self.next_job_id
        self.next_job_id += 1
        self.jobs[job_id] = {"filename": filename, "manifest": None}
        return {"ok": True, "job_id": job_id}

    def analyze(self, job_id: int, sensitivity: int = 50):
        if job_id not in self.jobs:
            return {"ok": False, "error": f"unknown job_id {job_id}"}

        # simple mapping of sensitivity to shot count
        target = max(3, min(12, int(3 + (sensitivity / 100.0) * 9)))
        t = 0.0
        shots = []
        for i in range(1, target + 1):
            dur = random.uniform(2.0, 7.0)
            start = t
            end = t + dur
            t = end
            total = random.randint(68, 95)
            shots.append(
                {
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
                    },
                }
            )

        manifest = {
            "source_file": self.jobs[job_id]["filename"],
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "config": self.cfg or {"note": "stub config"},
            "golden_baseline_summary": {
                "sample_count": self._baseline.get("sampleCount", 0),
                "avg_technical": self._baseline.get("avgTechnical", 0.0),
                "avg_subjective": self._baseline.get("avgSubjective", 0.0),
            },
            "shots": shots,
        }
        self.jobs[job_id]["manifest"] = manifest
        return {"ok": True, "shots": shots}

    def export_manifest(self, job_id: int):
        job = self.jobs.get(job_id)
        if not job or not job.get("manifest"):
            return {"ok": False, "error": "no manifest available; run analyze first"}

        stem = Path(job["manifest"]["source_file"]).stem or f"job_{job_id}"
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUTS_DIR / f"{stem}_run_manifest.json"
        out_path.write_text(json.dumps(job["manifest"], indent=2), encoding="utf-8")
        return {"ok": True, "path": str(out_path)}

def main():
    html = (WEB_DIR / "index.html").as_uri()
    api = API()
    window = webview.create_window(APP_NAME, html, width=1280, height=820, resizable=True, js_api=api)
    api.window = window
    webview.start(http_server=False)

if __name__ == "__main__":
    main()

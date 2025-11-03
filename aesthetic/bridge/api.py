
import os
import json
from typing import Any, Dict, List, Optional

# Lightweight "bridge" that the Web UI calls. No HTTP server is started.
# JS calls window.pywebview.api.<method>(...) and receives a Promise.

class AestheticAPI:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.data_dir = os.path.join(root_dir, "data")
        self.jobs_dir = os.path.join(self.data_dir, "jobs")
        self.baseline_dir = os.path.join(self.data_dir, "baseline")
        self.uploads_dir = os.path.join(self.data_dir, "uploads")
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.baseline_dir, exist_ok=True)
        os.makedirs(self.uploads_dir, exist_ok=True)

    # --- Config ---
    def get_config(self) -> Dict[str, Any]:
        cfg_path = os.path.join(self.root_dir, "config", "config.yaml")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return {"ok": True, "text": f.read()}
        except FileNotFoundError:
            return {"ok": False, "error": "config/config.yaml not found"}

    # --- Baseline ---
    def load_baseline(self) -> Dict[str, Any]:
        path = os.path.join(self.baseline_dir, "baseline.json")
        if not os.path.exists(path):
            # Empty baseline to start
            return {
                "ok": True,
                "baseline": {
                    "sampleCount": 0,
                    "avgTechnical": 0.0,
                    "avgSubjective": 0.0,
                    "avgGranular": {
                        "exposure": 0.0, "lighting": 0.0, "composition": 0.0,
                        "movement": 0.0, "color": 0.0, "clarity": 0.0, "emotionalResponse": 0.0
                    }
                }
            }
        with open(path, "r", encoding="utf-8") as f:
            return {"ok": True, "baseline": json.load(f)}

    def save_baseline(self, baseline: Dict[str, Any]) -> Dict[str, Any]:
        path = os.path.join(self.baseline_dir, "baseline.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2)
        return {"ok": True}

    # --- Jobs ---
    def create_job(self, filename: str) -> Dict[str, Any]:
        # In a future pass, create a UUID and copy uploads to a job folder.
        job_id = filename.replace(" ", "_")
        job_dir = os.path.join(self.jobs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        # Placeholder manifest
        manifest = {
            "job_id": job_id,
            "source_file": filename,
            "status": "queued",
            "shots": []
        }
        with open(os.path.join(job_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return {"ok": True, "job_id": job_id}

    def analyze(self, job_id: str, sensitivity: int = 50) -> Dict[str, Any]:
        # Stub: return a tiny mock so the UI can render cards while backend lands.
        # Replace with real pipeline calls in app/pipeline.py.
        shots = []
        for i in range(1, 5):
            shots.append({
                "id": i,
                "start": (i - 1) * 5,
                "end": i * 5,
                "scores": {
                    "exposure": {"total": 82},
                    "lighting": {"total": 78},
                    "composition": {"total": 80},
                    "movement": {"total": 76},
                    "color": {"total": 84},
                    "quality": {"total": 79},
                    "narrative": {"total": 73}
                },
                "totalScore": 80
            })
        job_dir = os.path.join(self.jobs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "shots.json"), "w", encoding="utf-8") as f:
            json.dump(shots, f, indent=2)
        return {"ok": True, "shots": shots}

    def export_manifest(self, job_id: str) -> Dict[str, Any]:
        job_dir = os.path.join(self.jobs_dir, job_id)
        manifest_path = os.path.join(job_dir, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        else:
            manifest = {"job_id": job_id, "shots": []}
        # In a real run, merge runtime config + baseline + shots here
        out_path = os.path.join(job_dir, f"{job_id}_run_manifest.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return {"ok": True, "path": out_path}

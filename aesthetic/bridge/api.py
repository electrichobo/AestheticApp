# aesthetic/bridge/api.py
#
# This is the ONE canonical API surface for AESTHETIC.
# The pywebview JS bridge calls these methods directly via:
#     window.pywebview.api.<method>(...)
#
# app.py does nothing except boot the pywebview window and hand it this class.
# All job handling, config, and baseline logic lives here or in the modules it imports.
# Do not add a second API class anywhere else.

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ..baseline import BaselineStore
from ..config import (
    load_config,
    to_yaml,
    DATA_DIR,
    OUTPUTS_DIR,
    BASELINE_DIR,
    CONFIG_PATH,
)

# ---------------------------------------------------------------------------
# Directory layout (all paths derived from config anchors — never hardcoded)
# ---------------------------------------------------------------------------
JOBS_DIR   = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"

for _d in (JOBS_DIR, UPLOADS_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class AestheticAPI:
    """
    Single API class exposed to the Web UI via pywebview.
    Every public method returns a dict with at minimum {"ok": True} or {"ok": False, "error": "..."}.
    All baseline operations route through BaselineStore.
    All job state is persisted to disk under data/jobs/<job_id>/.
    """

    def __init__(self) -> None:
        self._cfg: Dict[str, Any] = load_config()
        self._baseline = BaselineStore(DATA_DIR)

    # -----------------------------------------------------------------------
    # Config
    # -----------------------------------------------------------------------

    def get_config(self) -> Dict[str, Any]:
        """Return the current config.yaml content as a text string for the UI editor."""
        if CONFIG_PATH.exists():
            return {"ok": True, "text": CONFIG_PATH.read_text(encoding="utf-8")}
        return {"ok": False, "error": "config/config.yaml not found"}

    # -----------------------------------------------------------------------
    # Baseline  (all reads and writes go through BaselineStore)
    # -----------------------------------------------------------------------

    def load_baseline(self) -> Dict[str, Any]:
        """
        Return a summary of the current Golden Baseline state for the UI display tab.
        Includes the active golden version metadata and buffer counts.
        """
        try:
            summary = self._baseline.get_summary()
            return {"ok": True, "baseline": summary}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_baseline_detail(self) -> Dict[str, Any]:
        """
        Return the full active golden baseline stats dict.
        Used when the UI needs to display raw per-metric values.
        """
        try:
            active = self._baseline.load_active_golden()
            return {"ok": True, "baseline": active}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_baseline(self, baseline_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Accept a dict of metric values from the UI and push them into the staging buffer.
        Does NOT promote to golden — promotion is an explicit separate action.
        baseline_obj should be: { "metric_name": float_value, ... }
        """
        if not isinstance(baseline_obj, dict):
            return {"ok": False, "error": "baseline_obj must be a flat dict of metric: value pairs"}
        try:
            self._baseline.update_staging([baseline_obj])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def promote_baseline(self, note: str = "") -> Dict[str, Any]:
        """
        Promote the current staging buffer to a new versioned golden baseline.
        Clears staging after promotion.
        """
        try:
            result = self._baseline.promote_staging_to_golden(note=note)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def reset_staging(self) -> Dict[str, Any]:
        """Wipe the staging buffer without promoting."""
        try:
            self._baseline.reset_staging()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Jobs
    # -----------------------------------------------------------------------

    def create_job(self, filename: str) -> Dict[str, Any]:
        """
        Create a new analysis job for the given source file.
        Generates a unique job ID, creates the job folder, and writes an initial manifest.
        Returns the job_id the UI should use for all subsequent calls.
        """
        if not filename:
            return {"ok": False, "error": "filename is required"}

        job_id = _make_job_id(filename)
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "job_id":      job_id,
            "source_file": filename,
            "status":      "queued",
            "created":     _now_iso(),
            "config":      self._cfg,
            "shots":       [],
        }
        _write_json(job_dir / "manifest.json", manifest)

        return {"ok": True, "job_id": job_id}

    def analyze(self, job_id: str, sensitivity: int = 50) -> Dict[str, Any]:
        """
        Run analysis on the given job.
        Currently returns mock shot data so the UI flows remain testable.
        This method will be replaced with real pipeline calls in Phase 2+.
        sensitivity: 1-100, maps to scene detection threshold (higher = more shots).
        """
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}

        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "manifest missing or corrupt"}

        # --- MOCK PIPELINE (replaced in Phase 2+) ---
        # Sensitivity maps to shot count: low sensitivity = fewer shots, high = more.
        import random
        rng = random.Random(self._cfg.get("runtime", {}).get("seed", 42))
        target = max(3, min(12, int(3 + (sensitivity / 100.0) * 9)))
        t = 0.0
        shots = []
        for i in range(1, target + 1):
            dur = rng.uniform(2.0, 7.0)
            shots.append({
                "id":         i,
                "start":      round(t, 3),
                "end":        round(t + dur, 3),
                "totalScore": rng.randint(68, 95),
                "scores": {
                    "exposure":    {"total": rng.randint(60, 95)},
                    "lighting":    {"total": rng.randint(60, 95)},
                    "composition": {"total": rng.randint(60, 95)},
                    "movement":    {"total": rng.randint(60, 95)},
                    "color":       {"total": rng.randint(60, 95)},
                    "quality":     {"total": rng.randint(60, 95)},
                    "narrative":   {"total": rng.randint(60, 95)},
                },
            })
            t += dur
        # --- END MOCK ---

        _write_json(job_dir / "shots.json", shots)

        manifest["status"] = "complete"
        manifest["analyzed"] = _now_iso()
        manifest["shots"] = shots
        manifest["baseline_version"] = self._baseline.get_summary().get("active", {}).get("version", 0)
        _write_json(job_dir / "manifest.json", manifest)

        return {"ok": True, "shots": shots}

    def export_manifest(self, job_id: str) -> Dict[str, Any]:
        """
        Write the finalized run manifest to the outputs directory.
        Returns the output path so the UI can display or link it.
        """
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}

        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "no manifest found; run analyze first"}

        if not manifest.get("shots"):
            return {"ok": False, "error": "no shots in manifest; run analyze first"}

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        stem = Path(manifest.get("source_file", job_id)).stem
        out_path = OUTPUTS_DIR / f"{stem}_{job_id}_manifest.json"
        _write_json(out_path, manifest)

        return {"ok": True, "path": str(out_path)}

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Return the current status of a job.
        Used by the UI to poll progress once the real pipeline is running.
        """
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}

        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "manifest missing or corrupt"}

        return {
            "ok":     True,
            "status": manifest.get("status", "unknown"),
            "shots":  len(manifest.get("shots", [])),
        }


# ---------------------------------------------------------------------------
# Module-level helpers (not exposed to the UI)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_job_id(filename: str) -> str:
    stem = Path(filename).stem[:32].replace(" ", "_")
    short = uuid.uuid4().hex[:8]
    return f"{stem}_{short}"


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
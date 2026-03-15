# aesthetic/bridge/api.py
#
# Canonical API surface for AESTHETIC.
# JS calls window.pywebview.api.<method>(...) via pywebview bridge.
#
# This file now runs the real pipeline end-to-end.
# Progress events are pushed to the UI via a polling endpoint.
# All pipeline stages run synchronously in the same process for now —
# subprocess workers are a Phase 11 hardening item.

from __future__ import annotations

import json
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..baseline import BaselineStore
from ..config import (
    load_config,
    to_yaml,
    DATA_DIR,
    OUTPUTS_DIR,
    BASELINE_DIR,
    CONFIG_PATH,
)
from ..models.job import Job, JobStatus, Shot, Scene, CandidateFrame

JOBS_DIR    = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"

for _d in (JOBS_DIR, UPLOADS_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class AestheticAPI:
    """
    Single API class exposed to the Web UI via pywebview.
    Every public method returns {"ok": True, ...} or {"ok": False, "error": "..."}.
    """

    def __init__(self) -> None:
        self._cfg      = load_config()
        self._baseline = BaselineStore(DATA_DIR)
        # progress log per job: job_id -> list of {stage, message, pct}
        self._progress: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # active job state cache
        self._jobs: Dict[str, Job] = {}

    # -----------------------------------------------------------------------
    # Config
    # -----------------------------------------------------------------------

    def get_config(self) -> Dict[str, Any]:
        if CONFIG_PATH.exists():
            return {"ok": True, "text": CONFIG_PATH.read_text(encoding="utf-8")}
        return {"ok": False, "error": "config/config.yaml not found"}

    def reload_config(self) -> Dict[str, Any]:
        self._cfg = load_config()
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Baseline
    # -----------------------------------------------------------------------

    def load_baseline(self) -> Dict[str, Any]:
        try:
            return {"ok": True, "baseline": self._baseline.get_summary()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_baseline_detail(self) -> Dict[str, Any]:
        try:
            return {"ok": True, "baseline": self._baseline.load_active_golden()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_baseline(self, baseline_obj: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(baseline_obj, dict):
            return {"ok": False, "error": "baseline_obj must be a dict"}
        try:
            self._baseline.update_staging([baseline_obj])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def promote_baseline(self, note: str = "") -> Dict[str, Any]:
        try:
            result = self._baseline.promote_staging_to_golden(note=note)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def train_baseline(self, source_dir: str, note: str = "", mode: str = "staging") -> Dict[str, Any]:
        """
        Ingest reference stills from source_dir into the Golden Baseline.
        mode: "staging" for initial build, "augment" to add to existing golden.
        """
        try:
            from ..agents.baseline_trainer import train_baseline_from_folder

            def progress_cb(current: int, total: int, filename: str) -> None:
                pct = int(current / total * 100) if total > 0 else 0
                self._push_progress("baseline_training", f"[{current}/{total}] {filename}", pct)

            result = train_baseline_from_folder(
                source_dir=source_dir,
                data_dir=DATA_DIR,
                config=self._cfg,
                note=note,
                mode=mode,
                progress_cb=progress_cb,
            )
            self._baseline = BaselineStore(DATA_DIR)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def train_baseline_from_video(self, video_path: str, note: str = "", sensitivity: int = 50) -> Dict[str, Any]:
        """
        Ingest a reference video file into the Golden Baseline corpus.
        Always augments — never replaces existing stills or previous versions.
        """
        try:
            from ..agents.baseline_trainer import train_baseline_from_video

            def progress_cb(current: int, total: int, stage: str) -> None:
                self._push_progress("baseline_video", stage, current)

            result = train_baseline_from_video(
                video_path=video_path,
                data_dir=DATA_DIR,
                config=self._cfg,
                note=note,
                sensitivity=sensitivity,
                per_scene_candidates=self._cfg.get("extract", {}).get("per_scene_candidates", 6),
                progress_cb=progress_cb,
            )
            self._baseline = BaselineStore(DATA_DIR)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Jobs
    # -----------------------------------------------------------------------

    def create_job(self, filename: str) -> Dict[str, Any]:
        if not filename:
            return {"ok": False, "error": "filename is required"}

        job_id  = _make_job_id(filename)
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        self._progress[job_id] = []

        # resolve the source file path
        source_file = filename
        is_url = filename.startswith("http://") or filename.startswith("https://")

        if is_url:
            # download via yt-dlp
            self._push_progress(job_id, f"Downloading from URL…", 2)
            dl = self.download_url(filename, job_id)
            if not dl["ok"]:
                return {"ok": False, "error": f"Download failed: {dl["error"]}"}
            source_file = dl["path"]
            self._push_progress(job_id, f"Downloaded: {Path(source_file).name}", 5)
        else:
            # try to resolve bare filename to absolute path
            resolved = self.resolve_file_path(filename)
            if resolved["ok"]:
                source_file = resolved["path"]
            # if we can not resolve it, use as-is (may be an absolute path already)

        job = Job(
            job_id=job_id,
            source_file=source_file,
            status=JobStatus.QUEUED,
            config=self._cfg,
            seed=self._cfg.get("runtime", {}).get("seed", 42),
        )
        _write_json(job_dir / "manifest.json", job.to_manifest_dict())
        self._jobs[job_id] = job

        return {"ok": True, "job_id": job_id, "source_file": source_file}

    def resolve_file_path(self, filename: str) -> Dict[str, Any]:
        """
        Resolve a bare filename to an absolute path.
        pywebview file inputs give us only the filename, not the full path.
        We check the uploads dir and common video locations.
        """
        # check uploads dir first
        upload_path = UPLOADS_DIR / filename
        if upload_path.exists():
            return {"ok": True, "path": str(upload_path)}
        # check if it is already an absolute path
        p = Path(filename)
        if p.is_absolute() and p.exists():
            return {"ok": True, "path": str(p)}
        return {"ok": False, "error": f"Cannot resolve path for: {filename}"}

    def rebuild_cluster_index(self) -> Dict[str, Any]:
        """
        Force a rebuild of the style cluster index from the current baseline corpus.
        Call this after adding new material to the baseline.
        """
        try:
            from ..agents.stratification import rebuild_cluster_index
            bv     = self._baseline.get_summary().get("active", {}).get("version", 0)
            result = rebuild_cluster_index(DATA_DIR, bv)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_file_dialog(self) -> Dict[str, Any]:
        """
        Open a native Windows file picker using ctypes GetOpenFileName.
        This bypasses pywebview entirely and calls the Win32 API directly,
        which is the most reliable way to get a native file dialog on Windows.
        Falls back to a PowerShell-based dialog if ctypes fails.
        """
        import sys

        if sys.platform == "win32":
            return self._open_file_dialog_win32()
        elif sys.platform == "darwin":
            return self._open_file_dialog_macos()
        else:
            return self._open_file_dialog_linux()

    def _open_file_dialog_win32(self) -> Dict[str, Any]:
        """Windows native file dialog via ctypes."""
        try:
            import ctypes
            import ctypes.wintypes

            # filter string: pairs of display name + pattern, null-separated
            nul = chr(0)
            filter_str = (
                "Video Files" + nul +
                "*.mp4;*.mov;*.avi;*.mkv;*.mxf;*.mts;*.m2ts;*.wmv;*.webm;"
                "*.flv;*.m4v;*.mpg;*.mpeg;*.3gp;*.ts;*.r3d;*.braw" + nul +
                "All Files" + nul + "*.*" + nul + nul
            )

            buf = ctypes.create_unicode_buffer(32768)

            ofn = ctypes.wintypes.OPENFILENAMEW()
            ofn.lStructSize    = ctypes.sizeof(ofn)
            ofn.hwndOwner      = 0
            ofn.lpstrFilter    = filter_str
            ofn.lpstrFile      = buf
            ofn.nMaxFile       = ctypes.sizeof(buf)
            ofn.lpstrTitle     = "Select Video File"
            ofn.Flags          = 0x00080000 | 0x00001000  # OFN_EXPLORER | OFN_FILEMUSTEXIST

            comdlg32 = ctypes.windll.comdlg32
            ok = comdlg32.GetOpenFileNameW(ctypes.byref(ofn))

            if ok:
                return {"ok": True, "path": buf.value}
            # user cancelled — not an error
            return {"ok": False, "error": "no file selected"}

        except Exception as exc:
            # fallback to PowerShell dialog
            return self._open_file_dialog_powershell()

    def _open_file_dialog_powershell(self) -> Dict[str, Any]:
        """PowerShell fallback file dialog for Windows."""
        try:
            import subprocess
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                "$f.Filter = 'Video Files|*.mp4;*.mov;*.avi;*.mkv;*.mxf;*.mts;*.m2ts;*.wmv;*.webm;*.flv;*.m4v;*.mpg;*.mpeg;*.3gp;*.ts|All Files|*.*'; "
                "$f.Title = 'Select Video File'; "
                "if($f.ShowDialog() -eq 'OK'){ Write-Output $f.FileName }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=60
            )
            path = result.stdout.strip()
            if path and Path(path).exists():
                return {"ok": True, "path": path}
            return {"ok": False, "error": "no file selected"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _open_file_dialog_macos(self) -> Dict[str, Any]:
        """macOS file dialog via osascript."""
        try:
            import subprocess
            script = (
                'tell application "System Events" to '
                'set f to choose file with prompt "Select Video File" '
                'of type {"mp4","mov","avi","mkv","mxf","wmv","webm","m4v","mpg","mpeg"}\n'
                'return POSIX path of f'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=60
            )
            path = result.stdout.strip()
            if path:
                return {"ok": True, "path": path}
            return {"ok": False, "error": "no file selected"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _open_file_dialog_linux(self) -> Dict[str, Any]:
        """Linux file dialog via zenity or kdialog."""
        try:
            import subprocess
            result = subprocess.run(
                ["zenity", "--file-selection", "--title=Select Video File",
                 "--file-filter=Video|*.mp4 *.mov *.avi *.mkv *.mxf *.wmv *.webm *.m4v *.mpg *.mpeg"],
                capture_output=True, text=True, timeout=60
            )
            path = result.stdout.strip()
            if path:
                return {"ok": True, "path": path}
            return {"ok": False, "error": "no file selected"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_output_folder(self, folder_path: str) -> Dict[str, Any]:
        """Open a folder in Windows Explorer / macOS Finder."""
        try:
            import subprocess
            import sys
            path = Path(folder_path)
            if not path.exists():
                return {"ok": False, "error": f"path not found: {folder_path}"}
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def download_url(self, url: str, job_id: str) -> Dict[str, Any]:
        """
        Download a video from a web URL using yt-dlp.
        Supports YouTube, Vimeo, and any direct video URL.
        Downloads to uploads/<job_id>/ and returns the local path.
        """
        try:
            import yt_dlp
            out_dir  = UPLOADS_DIR / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out_tmpl = str(out_dir / "%(title)s.%(ext)s")

            ydl_opts = {
                "outtmpl":        out_tmpl,
                "format":         "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "quiet":          True,
                "no_warnings":    True,
                "merge_output_format": "mp4",
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # yt-dlp may change extension after merge
                for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                    candidate = Path(filename).with_suffix(ext)
                    if candidate.exists():
                        return {"ok": True, "path": str(candidate)}
                # fallback — find any video file in out_dir
                for f in out_dir.iterdir():
                    if f.suffix.lower() in [".mp4",".mkv",".webm",".mov",".avi"]:
                        return {"ok": True, "path": str(f)}
            return {"ok": False, "error": "download completed but output file not found"}

        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Editor feedback
    # -----------------------------------------------------------------------

    def save_feedback(self, job_id: str, shot_id: str, rating: int) -> Dict[str, Any]:
        """
        Save editor feedback for a shot.
        rating: 1 = thumbs up, -1 = thumbs down, 0 = neutral/reset
        Feedback persists across sessions in data/feedback/<job_id>.json
        """
        try:
            feedback_dir  = DATA_DIR / "feedback"
            feedback_dir.mkdir(parents=True, exist_ok=True)
            feedback_path = feedback_dir / f"{job_id}.json"

            feedback: Dict[str, Any] = {}
            if feedback_path.exists():
                try:
                    feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
                except Exception:
                    feedback = {}

            if rating == 0:
                feedback.pop(shot_id, None)   # reset to neutral
            else:
                feedback[shot_id] = {
                    "rating":    rating,
                    "shot_id":   shot_id,
                    "job_id":    job_id,
                    "timestamp": _now_iso(),
                }

            feedback_path.write_text(json.dumps(feedback, indent=2), encoding="utf-8")
            return {"ok": True, "shot_id": shot_id, "rating": rating}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_feedback(self, job_id: str) -> Dict[str, Any]:
        """Return all feedback for a job."""
        try:
            feedback_path = DATA_DIR / "feedback" / f"{job_id}.json"
            if not feedback_path.exists():
                return {"ok": True, "feedback": {}}
            feedback = json.loads(feedback_path.read_text(encoding="utf-8"))
            return {"ok": True, "feedback": feedback}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def reset_feedback(self, job_id: str) -> Dict[str, Any]:
        """Reset all feedback for a job to neutral."""
        try:
            feedback_path = DATA_DIR / "feedback" / f"{job_id}.json"
            if feedback_path.exists():
                feedback_path.unlink()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_all_feedback(self) -> Dict[str, Any]:
        """Return aggregated feedback across all jobs — used for future learning."""
        try:
            feedback_dir = DATA_DIR / "feedback"
            if not feedback_dir.exists():
                return {"ok": True, "feedback": {}, "total": 0}
            all_feedback: Dict[str, Any] = {}
            for p in feedback_dir.glob("*.json"):
                try:
                    job_feedback = json.loads(p.read_text(encoding="utf-8"))
                    all_feedback[p.stem] = job_feedback
                except Exception:
                    continue
            total = sum(len(v) for v in all_feedback.values())
            return {"ok": True, "feedback": all_feedback, "total": total}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Baseline corpus browser
    # -----------------------------------------------------------------------

    def get_baseline_thumbnails(self, limit: int = 48) -> Dict[str, Any]:
        """
        Return a sample of reference still paths from the baseline corpus
        for display in the corpus browser UI.
        Returns up to limit paths, sampled evenly across the corpus.
        """
        try:
            embeddings_dir = DATA_DIR / "baseline" / "embeddings"
            if not embeddings_dir.exists():
                return {"ok": True, "thumbnails": [], "total": 0}

            # embedding files reference their source — read source paths
            embedding_files = sorted(embeddings_dir.glob("*.json"))
            total           = len(embedding_files)

            # sample evenly
            if total <= limit:
                sample = embedding_files
            else:
                step   = total / limit
                sample = [embedding_files[int(i * step)] for i in range(limit)]

            thumbnails = []
            for ef in sample:
                try:
                    record = json.loads(ef.read_text(encoding="utf-8"))
                    source = record.get("source", "")
                    # find the original image in uploads or common locations
                    thumbnails.append({
                        "filename": source,
                        "model":    record.get("model"),
                    })
                except Exception:
                    continue

            return {"ok": True, "thumbnails": thumbnails, "total": total}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -----------------------------------------------------------------------
    # Run comparison
    # -----------------------------------------------------------------------

    def get_job_list(self) -> Dict[str, Any]:
        """Return a list of completed jobs available for comparison."""
        try:
            jobs = []
            for job_dir in sorted(JOBS_DIR.iterdir(), reverse=True):
                if not job_dir.is_dir():
                    continue
                shots_path = job_dir / "shots.json"
                manifest_path = job_dir / "manifest.json"
                if not shots_path.exists():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
                    shots    = json.loads(shots_path.read_text(encoding="utf-8"))
                    jobs.append({
                        "job_id":       job_dir.name,
                        "source_file":  manifest.get("source_file", "unknown"),
                        "created":      manifest.get("created", ""),
                        "shot_count":   len(shots),
                        "baseline_version": manifest.get("baseline_version", 0),
                    })
                except Exception:
                    continue
            return {"ok": True, "jobs": jobs}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def compare_jobs(self, job_id_a: str, job_id_b: str) -> Dict[str, Any]:
        """
        Compare the shot selections from two jobs.
        Returns shots unique to A, unique to B, and common to both
        (matched by scene_id and approximate timecode).
        """
        try:
            def load_shots(job_id: str) -> List[Dict]:
                p = JOBS_DIR / job_id / "shots.json"
                if not p.exists():
                    return []
                return json.loads(p.read_text(encoding="utf-8"))

            shots_a = load_shots(job_id_a)
            shots_b = load_shots(job_id_b)

            # match shots by scene_id
            scenes_a = {s["scene_id"]: s for s in shots_a}
            scenes_b = {s["scene_id"]: s for s in shots_b}

            common   = []
            only_a   = []
            only_b   = []

            all_scenes = set(scenes_a.keys()) | set(scenes_b.keys())
            for scene_id in sorted(all_scenes):
                in_a = scene_id in scenes_a
                in_b = scene_id in scenes_b
                if in_a and in_b:
                    common.append({
                        "scene_id":    scene_id,
                        "shot_a":      scenes_a[scene_id],
                        "shot_b":      scenes_b[scene_id],
                        "score_delta": round(
                            (scenes_a[scene_id].get("total_score") or 0) -
                            (scenes_b[scene_id].get("total_score") or 0), 2
                        ),
                    })
                elif in_a:
                    only_a.append(scenes_a[scene_id])
                else:
                    only_b.append(scenes_b[scene_id])

            return {
                "ok":      True,
                "job_a":   job_id_a,
                "job_b":   job_id_b,
                "common":  common,
                "only_a":  only_a,
                "only_b":  only_b,
                "summary": {
                    "common_count": len(common),
                    "only_a_count": len(only_a),
                    "only_b_count": len(only_b),
                },
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}
        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "manifest missing"}
        return {
            "ok":     True,
            "status": manifest.get("status", "unknown"),
            "shots":  len(manifest.get("shots", [])),
        }

    def poll_progress(self, job_id: str) -> Dict[str, Any]:
        """
        Return all progress events for a job since last poll.
        UI calls this on an interval while analysis is running.
        Clears the event queue after returning.
        """
        events = self._progress.pop(job_id, [])
        return {"ok": True, "events": events}

    # -----------------------------------------------------------------------
    # Analysis — real pipeline
    # -----------------------------------------------------------------------

    def analyze(self, job_id: str, sensitivity: int = 50) -> Dict[str, Any]:
        """
        Run the full analysis pipeline on the given job.
        Stages: ingest → scenes → sampling → metrics → inference → aggregation → selection → export
        """
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}

        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "manifest missing or corrupt"}

        source_file = manifest.get("source_file", "")
        cfg         = self._cfg
        seed        = cfg.get("runtime", {}).get("seed", 42)

        try:
            # --- stage 1: ingest ---
            self._push_progress(job_id, "Ingesting video metadata…", 5)
            from ..agents.ingest import ingest
            video_meta = ingest(source_file)

            # --- stage 2: scene detection ---
            self._push_progress(job_id, f"Detecting scenes (sensitivity {sensitivity})…", 15)
            from ..agents.scenes import detect_scenes, sensitivity_to_threshold
            threshold = sensitivity_to_threshold(sensitivity)
            scenes    = detect_scenes(video_meta, job_dir, threshold=threshold, config=cfg, seed=seed)
            self._push_progress(job_id, f"Found {len(scenes)} scenes", 25)

            # --- stage 3: candidate sampling ---
            self._push_progress(job_id, "Sampling candidate frames…", 30)
            from ..agents.sampling import sample_candidates
            per_scene = cfg.get("extract", {}).get("per_scene_candidates", 9)
            candidates = sample_candidates(video_meta, scenes, job_dir, per_scene_candidates=per_scene, seed=seed)
            self._push_progress(job_id, f"Extracted {len(candidates)} candidate frames", 40)

            # --- stage 4: metrics ---
            self._push_progress(job_id, "Computing frame metrics…", 42)
            from ..agents.metrics import compute_frame_metrics
            from collections import defaultdict as _dd
            by_scene: Dict[int, List] = _dd(list)
            for c in candidates:
                by_scene[c.scene_id].append(c)

            all_frame_metrics = []
            scene_candidate_map: Dict[int, List] = _dd(list)
            total_frames = len(candidates)
            for fi, c in enumerate(candidates):
                prev_path = candidates[fi-1].path if fi > 0 and candidates[fi-1].scene_id == c.scene_id else None
                fm = compute_frame_metrics(c.path, c.scene_id, c.timestamp, job_dir, cfg, prev_frame_path=prev_path)
                all_frame_metrics.append(fm)
                scene_candidate_map[c.scene_id].append(fm)
                if fi % 10 == 0:
                    pct = 42 + int((fi / total_frames) * 18)
                    self._push_progress(job_id, f"Metrics: {fi+1}/{total_frames} frames", pct)

            # --- stage 5: AI inference ---
            features = cfg.get("features", {})
            if features.get("clip_enabled", True) or features.get("midas_enabled", True) or features.get("yolo_enabled", True):
                self._push_progress(job_id, "Running AI model inference…", 60)
                from ..agents.inference import run_frame_inference
                for fi, fm in enumerate(all_frame_metrics):
                    c = candidates[fi]
                    all_frame_metrics[fi] = run_frame_inference(fm, c.path, job_dir, cfg)
                    if fi % 5 == 0:
                        pct = 60 + int((fi / total_frames) * 15)
                        self._push_progress(job_id, f"Inference: {fi+1}/{total_frames} frames", pct)

            # --- stage 5b: shot classification ---
            self._push_progress(job_id, "Classifying shot intent and scale…", 75)
            from ..agents.classifier import classify_shot, classify_scene_from_shots

            # load CLIP once and reuse across all frames
            _clip_model = _clip_pre = None
            _clip_dev   = "cpu"
            if features.get("clip_enabled", True):
                try:
                    import torch
                    import open_clip
                    _clip_dev = "cuda" if (features.get("gpu_enabled", False) and torch.cuda.is_available()) else "cpu"
                    _clip_model, _, _clip_pre = open_clip.create_model_and_transforms(
                        "ViT-B-32", pretrained="openai", device=_clip_dev
                    )
                    _clip_model.eval()
                except Exception:
                    pass

            # classify per frame, then aggregate to shot level
            frame_classifications: Dict[int, List[Dict]] = defaultdict(list)
            for fm in all_frame_metrics:
                cls = classify_shot(
                    fm, fm.frame_path, cfg,
                    clip_model=_clip_model,
                    clip_preprocess=_clip_pre,
                    clip_device=_clip_dev,
                )
                frame_classifications[fm.scene_id].append(cls)

            # aggregate to shot-level classification
            shot_classifications: Dict[int, Dict] = {}
            for scene_id, frame_cls_list in frame_classifications.items():
                shot_classifications[scene_id] = classify_scene_from_shots(frame_cls_list)

            # --- stage 6: aggregation ---
            self._push_progress(job_id, "Aggregating shot scores…", 76)
            from ..agents.aggregation import aggregate_shot

            shots: List[Shot]     = []
            scores                = []

            for scene in scenes:
                scene_frames = scene_candidate_map[scene.scene_id]
                if not scene_frames:
                    continue

                shot_id = f"shot_{scene.scene_id:04d}"
                score   = aggregate_shot(shot_id, scene.scene_id, scene_frames, cfg)

                # Creative pillar — stratified baseline similarity
                scene_candidates_list = by_scene[scene.scene_id]
                for fm in scene_frames:
                    if fm.inference.clip_embedding:
                        from ..agents.stratification import compute_stratified_similarity
                        bv  = self._baseline.get_summary().get("active", {}).get("version", 0)
                        sim_result = compute_stratified_similarity(
                            fm.inference.clip_embedding, DATA_DIR, baseline_version=bv
                        )
                        sim = sim_result.get("score")
                        if sim is not None:
                            score.baseline_similarity_score = sim
                            score.creative_total = round(sim, 2)
                            # store cluster info for manifest and UI
                            score.rationale = (
                                f"Style cluster: {sim_result.get('cluster_label', 'unknown')} "
                                f"(confidence: {sim_result.get('cluster_confidence', 0):.0%})"
                            ) if not score.rationale else score.rationale
                        break

                # attach classification to shot
                cls        = shot_classifications.get(scene.scene_id, {})
                shot_intent = cls.get("shot_intent", "unknown")

                # harmonised scoring — replaces simple weighted average
                # applies intent-aware category weights and creative/subjective alignment bonus
                from ..agents.scoring import compute_harmonised_score
                score = compute_harmonised_score(score, shot_intent, cfg)

                hero_frame = scene_candidates_list[len(scene_candidates_list)//2].path if scene_candidates_list else None

                try:
                    from ..models.job import MovementType, ShotScale, SceneType
                    mv_type  = MovementType(cls.get("movement_type", "unknown"))
                    sh_scale = ShotScale(cls.get("shot_scale",    "unknown"))
                    sc_type  = SceneType(cls.get("scene_type",    "unknown"))
                except ValueError:
                    mv_type  = MovementType.UNKNOWN
                    sh_scale = ShotScale.UNKNOWN
                    sc_type  = SceneType.UNKNOWN

                shot = Shot(
                    shot_id=shot_id,
                    scene_id=scene.scene_id,
                    start_time=scene.start_time,
                    end_time=scene.end_time,
                    start_frame=scene.start_frame,
                    end_frame=scene.end_frame,
                    frame_paths=[c.path for c in scene_candidates_list],
                    hero_frame=hero_frame,
                    movement_type=mv_type,
                    shot_scale=sh_scale,
                    scene_type=sc_type,
                )
                shots.append(shot)
                scores.append(score)

            # --- stage 7: selection ---
            self._push_progress(job_id, "Selecting best shots…", 82)
            from ..agents.selection import select_shots
            selected = select_shots(shots, scores, job_dir, cfg, seed=seed)
            self._push_progress(job_id, f"Selected {len(selected)} shots", 88)

            # --- stage 8: VLM rationale (optional) ---
            if features.get("vlm_rationale_enabled", False):
                self._push_progress(job_id, "Generating shot rationale…", 89)
                from ..agents.inference import run_shot_rationale
                score_map = {s.shot_id: s for s in scores}
                for i, sel in enumerate(selected):
                    sid   = sel.get("shot_id")
                    hero  = sel.get("hero_frame")
                    sc    = score_map.get(sid)
                    if sc and hero:
                        sc = run_shot_rationale(sc, hero, cfg)
                        selected[i]["rationale"] = sc.rationale

            # --- stage 9: export ---
            self._push_progress(job_id, "Exporting deliverables…", 90)
            from ..agents.export import export_job
            job_model = Job(
                job_id=job_id,
                source_file=source_file,
                status=JobStatus.COMPLETE,
                config=cfg,
                scenes=scenes,
                shots=shots,
                video_meta=video_meta,
                baseline_version=self._baseline.get_summary().get("active", {}).get("version", 0),
                seed=seed,
            )
            manifest_out = export_job(job_model, selected, job_dir, cfg)

            self._push_progress(job_id, "Analysis complete", 100)

            # build UI-friendly shot list
            ui_shots = _build_ui_shots(selected)

            return {
                "ok":            True,
                "shots":         ui_shots,
                "scene_count":   len(scenes),
                "selected_count":len(selected),
                "output_dir":    str(OUTPUTS_DIR / job_id),
                "contact_sheet": manifest_out.contact_sheet,
                "edl_path":      str(OUTPUTS_DIR / job_id / f"{Path(source_file).stem}_{job_id}.edl"),
                "csv_path":      str(OUTPUTS_DIR / job_id / f"{Path(source_file).stem}_selects.csv"),
            }

        except Exception as exc:
            self._push_progress(job_id, f"Error: {exc}", -1)
            return {"ok": False, "error": str(exc)}

    def export_manifest(self, job_id: str) -> Dict[str, Any]:
        """Re-export the manifest for a completed job."""
        job_dir = JOBS_DIR / job_id
        if not job_dir.exists():
            return {"ok": False, "error": f"job not found: {job_id}"}
        manifest = _read_json(job_dir / "manifest.json")
        if not manifest:
            return {"ok": False, "error": "no manifest found; run analyze first"}
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        stem     = Path(manifest.get("source_file", job_id)).stem
        out_path = OUTPUTS_DIR / job_id / f"{stem}_{job_id}_manifest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(out_path, manifest)
        return {"ok": True, "path": str(out_path)}

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _push_progress(self, job_id: str, message: str, pct: int) -> None:
        self._progress[job_id].append({
            "message": message,
            "pct":     pct,
            "ts":      _now_iso(),
        })


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_job_id(filename: str) -> str:
    import re
    # for URLs, extract just the domain + a short hash rather than the full URL
    if filename.startswith("http://") or filename.startswith("https://"):
        # extract domain as a label
        try:
            from urllib.parse import urlparse
            domain = urlparse(filename).netloc.replace("www.", "").split(".")[0]
            stem   = re.sub(r"[^a-zA-Z0-9_]", "", domain)[:16] or "url"
        except Exception:
            stem = "url"
    else:
        stem = Path(filename).stem[:32]
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)
    short = uuid.uuid4().hex[:8]
    return f"{stem}_{short}"


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_ui_shots(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise selected shots into the format the UI shot card renderer expects."""
    ui_shots = []
    for s in selected:
        scores = s.get("scores", {})
        ui_shots.append({
            "id":         s.get("rank"),
            "shot_id":    s.get("shot_id"),
            "scene_id":   s.get("scene_id"),
            "start":      s.get("start_time", 0.0),
            "end":        s.get("end_time",   0.0),
            "duration":   s.get("duration_sec", 0.0),
            "hero_frame": s.get("hero_frame"),
            "totalScore": s.get("total_score"),
            "technical":  s.get("technical_total"),
            "creative":   s.get("creative_total"),
            "baseline_similarity": s.get("baseline_similarity"),
            "rationale":  s.get("rationale"),
            "movement_type": s.get("movement_type"),
            "shot_scale":    s.get("shot_scale"),
            "scene_type":    s.get("scene_type"),
            "shot_intent":   s.get("shot_intent"),
            "scores": {
                "exposure":    {"total": scores.get("exposure")},
                "lighting":    {"total": scores.get("lighting")},
                "composition": {"total": scores.get("composition")},
                "movement":    {"total": scores.get("movement")},
                "color":       {"total": scores.get("color")},
                "quality":     {"total": scores.get("quality")},
                "narrative":   {"total": scores.get("narrative")},
            },
        })
    return ui_shots
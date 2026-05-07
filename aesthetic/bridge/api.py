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
        self._baseline_video_result: Dict[str, Any] = {}
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
            # auto-rebuild style clusters after stills augment
            try:
                from ..agents.stratification import rebuild_cluster_index
                bv = self._baseline.get_summary().get("active", {}).get("version", 0)
                rebuild_cluster_index(DATA_DIR, bv)
            except Exception as cluster_exc:
                print(f"[bridge] cluster rebuild failed (non-fatal): {cluster_exc}")
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def train_baseline_from_video(self, video_path: str, note: str = "", sensitivity: int = 50) -> Dict[str, Any]:
        """
        Start baseline video ingest in a background thread.
        Returns immediately with a task_id the UI can poll via poll_baseline_video_progress().
        Always augments — never replaces existing stills or previous versions.
        """
        import threading

        task_id = f"baseline_video_{Path(video_path).stem[:24]}"
        self._progress[task_id] = []
        self._baseline_video_result[task_id] = {"status": "running"}

        def _run():
            try:
                from ..agents.baseline_trainer import train_baseline_from_video as _train

                def progress_cb(current: int, total: int, stage: str) -> None:
                    self._push_progress(task_id, stage, current)

                result = _train(
                    video_path=video_path,
                    data_dir=DATA_DIR,
                    config=self._cfg,
                    note=note,
                    sensitivity=sensitivity,
                    per_scene_candidates=self._cfg.get("extract", {}).get("per_scene_candidates", 6),
                    progress_cb=progress_cb,
                )
                self._baseline = BaselineStore(DATA_DIR)
                # auto-rebuild style clusters after augment
                try:
                    self._push_progress(task_id, "Rebuilding style clusters…", 98)
                    from ..agents.stratification import rebuild_cluster_index
                    bv = self._baseline.get_summary().get("active", {}).get("version", 0)
                    rebuild_cluster_index(DATA_DIR, bv)
                except Exception as cluster_exc:
                    print(f"[bridge] cluster rebuild failed (non-fatal): {cluster_exc}")
                self._baseline_video_result[task_id] = {"status": "complete", "result": result}
                self._push_progress(task_id, "Baseline ingest complete", 100)
                # invalidate embedding cache so next analysis loads fresh data
                try:
                    from ..agents.baseline_trainer import invalidate_embedding_cache
                    invalidate_embedding_cache()
                except Exception:
                    pass
            except Exception as exc:
                self._baseline_video_result[task_id] = {"status": "error", "error": str(exc)}
                self._push_progress(task_id, f"Error: {exc}", -1)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"ok": True, "task_id": task_id}

    def queue_baseline_videos(self, video_paths: list, sensitivity: int = 50) -> Dict[str, Any]:
        """
        Queue multiple video files for sequential baseline augmentation.
        Processes them one at a time in a background thread.
        Returns a queue_id the UI can poll via poll_baseline_queue().
        """
        import threading

        if not video_paths:
            return {"ok": False, "error": "no paths provided"}

        queue_id = "baseline_queue"
        self._progress[queue_id] = []
        self._baseline_video_result[queue_id] = {
            "status":   "running",
            "total":    len(video_paths),
            "current":  0,
            "current_name": "",
            "completed": [],
            "errors":    [],
        }

        def _run_queue():
            print(f"[queue] _run_queue started, video_paths={video_paths}")
            from ..agents.baseline_trainer import train_baseline_from_video as _train
            from ..agents.stratification  import rebuild_cluster_index
            from ..agents.baseline_trainer import invalidate_embedding_cache

            state = self._baseline_video_result[queue_id]
            print(f"[queue] state initialized, iterating {len(video_paths)} paths")

            for i, vpath in enumerate(video_paths):
                print(f"[queue] processing item {i}: {vpath}")
                name = Path(vpath).name
                state["current"]      = i + 1
                state["current_name"] = name
                self._push_progress(queue_id,
                    f"[{i+1}/{len(video_paths)}] Starting: {name}", int(i / len(video_paths) * 100))

                try:
                    def _cb(current, total, stage):
                        # blend item progress into overall queue progress
                        item_pct = int(current)
                        overall  = int((i + item_pct / 100) / len(video_paths) * 100)
                        self._push_progress(queue_id,
                            f"[{i+1}/{len(video_paths)}] {name}: {stage}", overall)

                    result = _train(
                        video_path=vpath,
                        data_dir=DATA_DIR,
                        config=self._cfg,
                        note=f"queue item {i+1}/{len(video_paths)}: {name}",
                        sensitivity=sensitivity,
                        per_scene_candidates=self._cfg.get("extract", {}).get("per_scene_candidates", 6),
                        progress_cb=_cb,
                    )
                    print(f"[queue] _train result for {name}: {result}")
                    if not result.get("ok", False):
                        err = result.get("error", "unknown error")
                        print(f"[queue] _train failed for {name}: {err}")
                        state["errors"].append({"name": name, "error": err})
                        self._push_progress(queue_id,
                            f"[{i+1}/{len(video_paths)}] ✗ {name}: {err}",
                            int((i + 1) / len(video_paths) * 100))
                    else:
                        self._baseline = BaselineStore(DATA_DIR)
                        invalidate_embedding_cache()
                        state["completed"].append({
                            "name":      name,
                            "processed": result.get("processed", 0),
                            "scenes":    result.get("scene_count", 0),
                        })
                        self._push_progress(queue_id,
                            f"[{i+1}/{len(video_paths)}] ✓ {name} — {result.get('processed',0)} frames",
                            int((i + 1) / len(video_paths) * 100))

                except Exception as exc:
                    state["errors"].append({"name": name, "error": str(exc)})
                    self._push_progress(queue_id,
                        f"[{i+1}/{len(video_paths)}] ✗ {name}: {exc}",
                        int((i + 1) / len(video_paths) * 100))

            # rebuild clusters once at the end, not after every file
            try:
                self._push_progress(queue_id, "Rebuilding style clusters…", 99)
                bv = self._baseline.get_summary().get("active", {}).get("version", 0)
                rebuild_cluster_index(DATA_DIR, bv)
            except Exception as ce:
                print(f"[bridge] cluster rebuild after queue: {ce}")

            state["status"] = "complete"
            total_frames = sum(c["processed"] for c in state["completed"])
            self._push_progress(queue_id,
                f"Queue complete — {len(state['completed'])} files, {total_frames} frames added", 100)

        threading.Thread(target=_run_queue, daemon=True).start()
        return {"ok": True, "queue_id": queue_id, "total": len(video_paths)}

    def poll_baseline_queue(self) -> Dict[str, Any]:
        """Poll progress for the running baseline video queue."""
        queue_id = "baseline_queue"
        events   = self._progress.get(queue_id, [])
        self._progress[queue_id] = []
        state    = self._baseline_video_result.get(queue_id, {"status": "idle"})
        return {
            "ok":      True,
            "events":  events,
            "status":  state.get("status", "idle"),
            "total":   state.get("total", 0),
            "current": state.get("current", 0),
            "current_name": state.get("current_name", ""),
            "completed": state.get("completed", []),
            "errors":    state.get("errors", []),
        }

    def poll_baseline_video_progress(self, task_id: str) -> Dict[str, Any]:
        """
        Poll progress events for a running baseline video ingest.
        Returns accumulated progress events and current status.
        """
        events = self._progress.get(task_id, [])
        # drain the queue
        self._progress[task_id] = []
        result_info = self._baseline_video_result.get(task_id, {"status": "unknown"})
        return {
            "ok":     True,
            "events": events,
            "status": result_info.get("status", "unknown"),
            "result": result_info.get("result"),
            "error":  result_info.get("error"),
        }

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

        # quick ingest to get colour space metadata for UI display
        meta_dict = {}
        try:
            from ..agents.ingest import ingest
            video_meta = ingest(source_file)
            meta_dict = {
                "duration_sec":    video_meta.duration_sec,
                "fps":             video_meta.fps,
                "width":           video_meta.width,
                "height":          video_meta.height,
                "codec":           video_meta.codec,
                "color_primaries": video_meta.color_primaries,
                "color_trc":       video_meta.color_trc,
                "color_space":     video_meta.color_space,
                "is_log_encoded":  video_meta.is_log_encoded,
            }
        except Exception:
            pass
        return {"ok": True, "job_id": job_id, "source_file": source_file, "meta": meta_dict}

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
        Open a native file picker via pywebview's built-in dialog.
        Works on all platforms with no external processes.
        """
        try:
            import webview
            file_types = (
                "Video Files (*.mp4;*.mov;*.avi;*.mkv;*.mxf;*.mts;*.m2ts;"
                "*.wmv;*.webm;*.flv;*.m4v;*.mpg;*.mpeg;*.3gp;*.ts;*.r3d;*.braw)",
                "All Files (*.*)",
            )
            if self._window is None:
                raise RuntimeError("window not initialised")
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=file_types,
            )
            if result and len(result) > 0:
                return {"ok": True, "path": result[0], "paths": list(result)}
            return {"ok": False, "error": "no file selected"}
        except Exception as exc:
            print(f"[bridge] pywebview dialog failed: {exc} — trying PowerShell fallback")
            return self._open_file_dialog_powershell()

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
            # log the ctypes failure then try PowerShell fallback
            print(f"[bridge] ctypes dialog failed: {exc} — trying PowerShell fallback")
            return self._open_file_dialog_powershell()

    def _open_file_dialog_powershell(self) -> Dict[str, Any]:
        """PowerShell fallback file dialog for Windows."""
        try:
            import subprocess
            import sys
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                "$f.Filter = 'Video Files|*.mp4;*.mov;*.avi;*.mkv;*.mxf;*.mts;*.m2ts;*.wmv;*.webm;*.flv;*.m4v;*.mpg;*.mpeg;*.3gp;*.ts|All Files|*.*'; "
                "$f.Title = 'Select Video File'; "
                "if($f.ShowDialog() -eq 'OK'){ Write-Output $f.FileName }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True, text=True, timeout=300,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
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

    def set_export_clips(self, enabled: bool) -> Dict[str, Any]:
        """Toggle video clip export on or off."""
        self._cfg.setdefault("export", {})["export_clips"] = bool(enabled)
        return {"ok": True, "export_clips": bool(enabled)}

    def get_export_clips(self) -> Dict[str, Any]:
        """Return current clip export setting."""
        enabled = bool(self._cfg.get("export", {}).get("export_clips", False))
        return {"ok": True, "export_clips": enabled}

    def open_output_folder(self, folder_path: str) -> Dict[str, Any]:
        """Open a folder in Windows Explorer / macOS Finder / Linux file manager."""
        try:
            import subprocess
            import sys
            import os
            path = Path(folder_path)
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_local_file_url(self, file_path: str) -> Dict[str, Any]:
        """
        Return a URL for a local file that can be loaded in http_server mode.

        Images: returned as data: URI (inline base64).
        Videos: pywebview's http server can serve files from their directory —
                we use evaluate_js to get the server's base URL and construct
                a relative path. Falls back to file:// for non-bundle mode.
        """
        try:
            import base64
            path = Path(file_path)
            if not path.exists():
                return {"ok": False, "error": "file not found"}
            suffix = path.suffix.lower()

            if suffix in (".jpg", ".jpeg", ".png", ".webp"):
                data = base64.b64encode(path.read_bytes()).decode()
                mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else f"image/{suffix[1:]}"
                return {"ok": True, "url": f"data:{mime};base64,{data}"}

            # For video: in bundle (http_server mode), file:// is blocked.
            # Use pywebview's load_url workaround — store path for JS to use.
            # The video element will use a blob URL created from fetch via the bridge.
            import sys
            if getattr(sys, "frozen", False):
                # Return the path; JS will use get_video_data to fetch as blob
                return {"ok": True, "url": None, "path": str(path), "use_blob": True}

            return {"ok": True, "url": path.as_uri()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_video_data(self, file_path: str) -> Dict[str, Any]:
        """
        Return video file as base64 for blob URL creation in bundle mode.
        Only called for short preview clips — not full films.
        Limits to 50MB to avoid memory issues.
        """
        try:
            import base64
            path = Path(file_path)
            if not path.exists():
                return {"ok": False, "error": "file not found"}
            size = path.stat().st_size
            if size > 50 * 1024 * 1024:  # 50MB limit for preview
                return {"ok": False, "error": "file too large for preview", "too_large": True}
            suffix = path.suffix.lower().lstrip(".")
            mime_map = {"mp4": "video/mp4", "mov": "video/quicktime",
                        "avi": "video/x-msvideo", "mkv": "video/x-matroska",
                        "webm": "video/webm", "m4v": "video/mp4"}
            mime = mime_map.get(suffix, "video/mp4")
            data = base64.b64encode(path.read_bytes()).decode()
            return {"ok": True, "data": data, "mime": mime}
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

    def save_feedback(
        self,
        job_id:       str,
        shot_id:      str,
        rating:       int,
        shot_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persist a feedback event to the SQLite feedback store.
        rating: 1 = thumbs up, -1 = thumbs down, 0 = retracted/neutral

        Only thumbs up and thumbs down generate training signal.
        Neutral (0) is recorded for audit but excluded from reranker training.
        Pairwise preferences are derived automatically after each event.

        shot_context: full shot dict from the UI — attached to the event so
        the feature export pipeline doesn't need to re-run inference.
        """
        try:
            from ..agents.feedback_store import save_feedback_event

            # build job context from current job if available
            job_context: Dict[str, Any] = {}
            job = self._jobs.get(job_id)
            if job and job.video_meta:
                vm = job.video_meta
                job_context = {
                    "source_file":    str(job.source_file),
                    "width":          vm.width,
                    "height":         vm.height,
                    "fps":            vm.fps,
                    "color_primaries":vm.color_primaries,
                    "color_trc":      vm.color_trc,
                    "is_log_encoded": vm.is_log_encoded,
                }

            ok = save_feedback_event(
                job_id       = job_id,
                shot_id      = shot_id,
                rating       = rating,
                shot_context = shot_context or {},
                job_context  = job_context,
            )
            return {"ok": ok, "shot_id": shot_id, "rating": rating}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_feedback(self, job_id: str) -> Dict[str, Any]:
        """Return all non-neutral feedback for a job as {shot_id: rating}."""
        try:
            from ..agents.feedback_store import get_feedback_for_job
            feedback = get_feedback_for_job(job_id)
            return {"ok": True, "feedback": feedback}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def clean_stale_embeddings(self) -> Dict[str, Any]:
        """Delete embedding files whose dim doesn't match the current model dim."""
        try:
            from ..agents.baseline_trainer import clean_stale_embeddings, invalidate_embedding_cache
            result = clean_stale_embeddings(DATA_DIR)
            invalidate_embedding_cache()
            # also clear the compat cache on the baseline object
            if hasattr(self._baseline.get_embedding_dim_status, '__defaults__'):
                self._baseline.get_embedding_dim_status.__defaults__[0].clear()
            return {"ok": True, **result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def train_transition_classifier(self, data_dir: str) -> Dict[str, Any]:
        """
        Train the transition type classifier from labelled clips.
        data_dir should point to the transitiontrainer directory.
        """
        try:
            from ..agents.transition_classifier import train as _train_tc
            from ..config import DATA_DIR
            model_path = _train_tc(
                data_dir=data_dir,
                output_dir=str(DATA_DIR),
                verbose=True,
            )
            # Load the saved payload to report accuracy
            import pickle
            with open(model_path, "rb") as f:
                payload = pickle.load(f)
            return {
                "ok":          True,
                "model_path":  str(model_path),
                "cv_accuracy": round(payload.get("cv_accuracy", 0) * 100, 1),
                "n_samples":   payload.get("n_samples", 0),
                "classes":     payload.get("classes", []),
            }
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def get_transition_model_status(self) -> Dict[str, Any]:
        """Check whether a trained transition model exists.
        Checks user data dir first, then source tree, then _MEIPASS bundle."""
        import pickle
        from pathlib import Path as _Path
        from ..config import DATA_DIR

        candidates = [
            DATA_DIR / "transition_model.pkl",                                   # user-trained
            _Path(__file__).resolve().parent.parent / "data" / "transition_model.pkl",  # source tree (dev)
        ]
        # Bundle path (_MEIPASS) if frozen
        import sys as _sys
        if getattr(_sys, "frozen", False):
            candidates.append(_Path(_sys._MEIPASS) / "aesthetic" / "data" / "transition_model.pkl")

        for model_path in candidates:
            if not model_path.exists():
                continue
            try:
                with open(model_path, "rb") as f:
                    payload = pickle.load(f)
                source = ("user" if model_path == candidates[0]
                          else "bundled" if "MEIPASS" in str(model_path)
                          else "bundled")
                return {
                    "trained":     True,
                    "cv_accuracy": round(payload.get("cv_accuracy", 0) * 100, 1),
                    "n_samples":   payload.get("n_samples", 0),
                    "classes":     payload.get("classes", []),
                    "source":      source,
                }
            except Exception:
                continue
        return {"trained": False}


    def get_baseline_compat(self) -> Dict[str, Any]:
        """Check whether stored baseline embeddings match the current model."""
        try:
            result = self._baseline.get_embedding_dim_status()
            print(f"[compat] {result}")
            return result
        except Exception as exc:
            import traceback
            print(f"[compat] EXCEPTION: {exc}")
            traceback.print_exc()
            return {"ok": False, "error": str(exc), "compatible": False,
                    "reason": "error", "stored_dim": 0, "current_dim": 0,
                    "current_model": "unknown", "stale_count": 0, "total_count": 0}

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Return summary stats for the feedback store (for UI display)."""
        try:
            from ..agents.feedback_store import get_feedback_stats
            return {"ok": True, **get_feedback_stats()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_training_features(self, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Export feedback events as a flat feature matrix for reranker training.
        Writes feedback_features.csv and pairwise_features.csv to output_dir
        (defaults to DATA_DIR/training/).
        """
        try:
            from ..agents.feature_export import (
                export_training_features,
                export_pairwise_features,
            )
            out = Path(output_dir) if output_dir else DATA_DIR / "training"
            out.mkdir(parents=True, exist_ok=True)

            feat_result = export_training_features(
                output_path=str(out / "feedback_features.csv")
            )
            pair_result = export_pairwise_features(
                output_path=str(out / "pairwise_features.csv")
            )
            return {
                "ok":             feat_result["ok"],
                "feedback_rows":  feat_result.get("rows", 0),
                "pairwise_rows":  pair_result.get("rows", 0),
                "feature_cols":   feat_result.get("feature_cols", 0),
                "output_dir":     str(out),
            }
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

    def analyze(self, job_id: str, sensitivity: int = 50, preset: str = "auto") -> Dict[str, Any]:
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

        # --- Runtime preset (always assigned before any stage references it) ---
        try:
            from ..agents.model_utils import resolve_preset
            _preset = resolve_preset(preset)
        except Exception as _preset_exc:
            print(f"[bridge] preset resolution failed: {_preset_exc} — using balanced defaults")
            _preset = {
                "name": "balanced", "description": "balanced (fallback)",
                "per_scene_candidates": 9, "per_scene_keep_pct": 0.40,
                "shortlist_pct": 0.25, "midas_enabled": True,
                "yolo_enabled": True, "clip_enabled": True,
                "subject_metrics": True, "top_k_multiplier": 1.0,
            }
        self._push_progress(job_id, f"Runtime preset: {_preset['name']} — {_preset['description']}", 2)

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
            per_scene = _preset.get("per_scene_candidates",
                          cfg.get("extract", {}).get("per_scene_candidates", 9))
            candidates = sample_candidates(video_meta, scenes, job_dir, per_scene_candidates=per_scene, seed=seed)
            self._push_progress(job_id, f"Extracted {len(candidates)} candidate frames", 40)

            # --- stage 4: metrics (parallel, CPU-capped) ---
            self._push_progress(job_id, "Computing frame metrics…", 42)
            from ..agents.metrics import compute_frame_metrics
            from ..agents.baseline_trainer import _compute_frame_metrics_worker
            from collections import defaultdict as _dd
            import concurrent.futures as _cf
            import psutil as _psutil
            import os as _os

            by_scene: Dict[int, List] = _dd(list)
            for c in candidates:
                by_scene[c.scene_id].append(c)

            total_frames  = len(candidates)
            cpu_cap_pct   = float(cfg.get("runtime", {}).get("cpu_cap_pct", 60.0))
            phys_cores    = _psutil.cpu_count(logical=False) or _psutil.cpu_count() or 4
            max_workers   = max(1, min(phys_cores - 1, int(phys_cores * cpu_cap_pct / 100.0)))

            # detect repo root for subprocess sys.path injection
            import sys as _sys
            repo_root = str(Path(__file__).resolve().parents[3])
            if not _os.path.isfile(_os.path.join(repo_root, 'aesthetic', '__init__.py')):
                p = Path(__file__).resolve()
                for _ in range(6):
                    p = p.parent
                    if (p / 'aesthetic' / '__init__.py').exists():
                        repo_root = str(p)
                        break

            # build args — include prev_path for temporal metrics
            # CUDA suppression env vars are set inside the worker itself
            frame_args = []
            for fi, c in enumerate(candidates):
                prev_path = (candidates[fi-1].path
                             if fi > 0 and candidates[fi-1].scene_id == c.scene_id
                             else None)
                frame_args.append((c.path, c.scene_id, c.timestamp,
                                   str(job_dir), cfg, prev_path, repo_root))

            # Use ThreadPoolExecutor on Windows to avoid DLL conflicts
            # (cublas/BLAS conflict when spawning processes after torch loads).
            # numpy/OpenCV/scipy release the GIL so threads achieve parallelism.
            import platform as _plat
            _executor_cls = (_cf.ThreadPoolExecutor
                             if _plat.system() == "Windows"
                             else _cf.ProcessPoolExecutor)

            # parallel metrics
            metrics_by_path: Dict[str, Any] = {}
            completed = 0
            with _executor_cls(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(_compute_frame_metrics_worker, args): args[0]
                    for args in frame_args
                }
                for future in _cf.as_completed(future_map):
                    frame_path = future_map[future]
                    completed += 1
                    try:
                        fm = future.result()
                        if fm is not None:
                            metrics_by_path[frame_path] = fm
                    except Exception as exc:
                        print(f"[bridge] metrics failed for {frame_path}: {exc}")
                    if completed % 5 == 0:
                        pct = 42 + int((completed / total_frames) * 18)
                        self._push_progress(job_id, f"Metrics: {completed}/{total_frames} frames", pct)

            # reassemble in candidate order, preserving scene grouping
            all_frame_metrics = []
            scene_candidate_map: Dict[int, List] = _dd(list)
            for c in candidates:
                fm = metrics_by_path.get(c.path)
                if fm is None:
                    from ..models.scores import FrameMetrics
                    fm = FrameMetrics(frame_id=Path(c.path).stem,
                                      scene_id=c.scene_id,
                                      timestamp=c.timestamp,
                                      frame_path=c.path)
                all_frame_metrics.append(fm)
                scene_candidate_map[c.scene_id].append(fm)

            # --- stage 5: AI inference — two-stage ---
            #
            # Stage 1 (all frames): CLIP + YOLO, NO MiDaS
            #   → fast first-pass scores, used to compute shortlist
            #
            # Stage 2 (shortlisted scenes only): MiDaS depth
            #   → refines depth_separation for scenes that matter
            #   → gamut data also collected per-scene in aggregation
            #
            features = cfg.get("features", {})
            from ..agents.two_stage import (
                stage1_config, compute_shortlist,
                stage2_config, shortlist_progress_label, build_stage_summary,
                DEFAULT_SHORTLIST_PCT,
            )
            shortlist_pct = float(_preset.get("shortlist_pct",
                          cfg.get("selection", {}).get("shortlist_pct", DEFAULT_SHORTLIST_PCT)))

            # Apply preset feature flag overrides
            for _flag in ("midas_enabled", "yolo_enabled", "clip_enabled"):
                if _flag in _preset:
                    features[_flag] = _preset[_flag]
            # subject_metrics flag propagated to frame_cfg later

            if features.get("clip_enabled", True) or features.get("midas_enabled", True) or features.get("yolo_enabled", True):
                from ..agents.inference import run_frame_inference

                # ── Stage 1: CLIP + YOLO on all frames, MiDaS disabled ──
                self._push_progress(job_id, "Stage 1: running CLIP + YOLO on all frames…", 58)
                s1_cfg = stage1_config(cfg)   # MiDaS disabled

                for fi, fm in enumerate(all_frame_metrics):
                    c = candidates[fi]
                    all_frame_metrics[fi] = run_frame_inference(fm, c.path, job_dir, s1_cfg)
                    if fi % 5 == 0:
                        pct = 58 + int((fi / total_frames) * 10)
                        self._push_progress(job_id, f"Stage 1 inference: {fi+1}/{total_frames} frames", pct)

                # ── Stage 1 aggregation: quick scores to determine shortlist ──
                self._push_progress(job_id, "Stage 1: computing initial scores…", 68)
                from ..agents.aggregation import aggregate_shot as _agg
                from ..agents.scoring import compute_harmonised_score as _score

                # Load corpus distributions once for corpus-relative scoring
                _corpus_stats: Dict[str, Any] = {}
                try:
                    _corpus_stats = self._baseline.get_metric_distributions()
                    if _corpus_stats:
                        print(f"[analysis] corpus stats loaded: {len(_corpus_stats)} metrics")
                    else:
                        print("[analysis] no corpus stats available — scoring without baseline distributions")
                except Exception as _ce:
                    print(f"[analysis] corpus stats load failed: {_ce}")

                s1_shots: List[Shot] = []
                s1_scores: List[ShotScore] = []

                for scene in scenes:
                    scene_frames = scene_candidate_map[scene.scene_id]
                    if not scene_frames:
                        continue
                    s_id  = f"shot_{scene.scene_id:04d}"
                    sc    = _agg(s_id, scene.scene_id, scene_frames, cfg,
                                corpus_stats=_corpus_stats)
                    sc    = _score(sc, "unknown", cfg)   # intent unknown at stage 1
                    s1_shots.append(Shot(
                        shot_id=s_id,
                        scene_id=scene.scene_id,
                        start_time=scene.start_time,
                        end_time=scene.end_time,
                        start_frame=scene.start_frame,
                        end_frame=scene.end_frame,
                        frame_paths=[],
                        hero_frame=None,
                    ))
                    s1_scores.append(sc)

                # compute shortlist from stage-1 scores
                shortlist_ids = compute_shortlist(s1_shots, s1_scores, shortlist_pct)
                summary = build_stage_summary(s1_scores, shortlist_ids)
                self._push_progress(
                    job_id,
                    shortlist_progress_label(shortlist_ids, len(scenes)),
                    70
                )
                print(f"[bridge] two-stage summary: {summary}")
                self._push_progress(
                    job_id,
                    f"Shortlist: {summary['shortlisted']}/{summary['total_scenes']} scenes "
                    f"(avg score: all={summary['avg_score_all']:.1f}, shortlist={summary['avg_score_shortlist']:.1f})",
                    70
                )

                # ── Stage 2: MiDaS on shortlisted scenes only ──
                if features.get("midas_enabled", True) and shortlist_ids:
                    self._push_progress(job_id, "Stage 2: depth analysis on shortlisted scenes…", 71)
                    _midas_done: set = set()
                    shortlisted_frames = [
                        (fi, fm) for fi, fm in enumerate(all_frame_metrics)
                        if fm.scene_id in shortlist_ids
                    ]
                    for idx2, (fi, fm) in enumerate(shortlisted_frames):
                        c = candidates[fi]
                        run_midas = fm.scene_id not in _midas_done
                        if run_midas:
                            _midas_done.add(fm.scene_id)
                        # build per-frame config: MiDaS only for first frame of each shortlisted scene
                        frame_cfg = dict(cfg)
                        frame_cfg["features"] = dict(features)
                        frame_cfg["features"]["midas_enabled"] = run_midas
                        frame_cfg["features"]["subject_metrics_enabled"] = _preset.get("subject_metrics", True)
                        # re-run inference (CLIP cached, only depth runs again)
                        if run_midas:
                            all_frame_metrics[fi] = run_frame_inference(
                                all_frame_metrics[fi], c.path, job_dir, frame_cfg
                            )
                        pct = 71 + int((idx2 / max(1, len(shortlisted_frames))) * 4)
                        self._push_progress(
                            job_id,
                            f"Stage 2 depth: {len(_midas_done)}/{len(shortlist_ids)} scenes processed",
                            pct
                        )

            # --- stage 5b: shot classification ---
            self._push_progress(job_id, "Classifying shot intent and scale…", 76)
            from ..agents.classifier import classify_shot, classify_scene_from_shots

            # load CLIP once and reuse across all frames
            _clip_model = _clip_pre = None
            _clip_dev   = "cpu"
            if features.get("clip_enabled", True):
                try:
                    import torch
                    import open_clip
                    from ..agents.model_utils import get_device, load_model
                    _clip_dev = get_device(bool(features.get("gpu_enabled", True)))
                    _clip_model, _clip_pre, _mn, _ = load_model(_clip_dev)
                except Exception:
                    pass

            # classify per frame with adaptive subsampling for long scenes.
            # Shot intent rarely changes within a scene — classifying every
            # frame of a 60-frame scene wastes GPU. Sample up to MAX_CLS_PER_SCENE
            # frames per scene, spread evenly, then propagate the result.
            MAX_CLS_PER_SCENE = 4
            from collections import defaultdict as _dd2
            frames_by_scene: Dict[int, List] = _dd2(list)
            for fm in all_frame_metrics:
                frames_by_scene[fm.scene_id].append(fm)

            frame_classifications: Dict[int, List[Dict]] = defaultdict(list)
            for scene_id, scene_fms in frames_by_scene.items():
                n = len(scene_fms)
                if n <= MAX_CLS_PER_SCENE:
                    sample = scene_fms
                else:
                    # evenly spaced sample
                    step   = n / MAX_CLS_PER_SCENE
                    sample = [scene_fms[int(i * step)] for i in range(MAX_CLS_PER_SCENE)]

                for fm in sample:
                    cls = classify_shot(
                        fm, fm.frame_path, cfg,
                        clip_model=_clip_model,
                        clip_preprocess=_clip_pre,
                        clip_device=_clip_dev,
                    )
                    frame_classifications[scene_id].append(cls)

            # aggregate to shot-level classification
            shot_classifications: Dict[int, Dict] = {}
            for scene_id, frame_cls_list in frame_classifications.items():
                shot_classifications[scene_id] = classify_scene_from_shots(frame_cls_list)

            # Rebuild scene_candidate_map with post-inference FrameMetrics
            # (the map was built before inference ran — references are stale)
            from collections import defaultdict as _dd3
            scene_candidate_map = _dd3(list)
            for fi, fm in enumerate(all_frame_metrics):
                scene_candidate_map[candidates[fi].scene_id].append(fm)

            # --- stage 6: aggregation ---
            self._push_progress(job_id, "Aggregating shot scores…", 78)
            from ..agents.aggregation import aggregate_shot

            shots: List[Shot]     = []
            scores                = []

            for scene in scenes:
                scene_frames = scene_candidate_map[scene.scene_id]
                if not scene_frames:
                    continue

                shot_id = f"shot_{scene.scene_id:04d}"
                score   = aggregate_shot(shot_id, scene.scene_id, scene_frames, cfg,
                                       corpus_stats=_corpus_stats)

                # Colour aggregation — ΔE averaged from frames
                de_vals = [fm.color.color_accuracy_de2000 for fm in scene_frames
                           if fm.color and fm.color.color_accuracy_de2000 is not None]
                if de_vals:
                    score.delta_e_d65 = round(float(sum(de_vals) / len(de_vals)), 3)

                # ΔE vs baseline corpus reference colour
                try:
                    ref = self._baseline.get_reference_colour()
                    # get mean Lab from this shot's frames
                    from ..agents.metrics import _compute_delta_e2000
                    L_vals = [fm.exposure.histogram_mean for fm in scene_frames
                              if fm.exposure and fm.exposure.histogram_mean is not None]
                    wb_vals= [fm.color.wb_deviation for fm in scene_frames
                              if fm.color and fm.color.wb_deviation is not None]
                    if L_vals and wb_vals:
                        L_shot = sum(L_vals) / len(L_vals)
                        # use temp to estimate hue direction for this shot
                        temp_vals = [fm.lighting.color_temp_kelvin for fm in scene_frames
                                     if fm.lighting and fm.lighting.color_temp_kelvin is not None]
                        temp_shot = sum(temp_vals) / len(temp_vals) if temp_vals else 5600.0
                        norm = (temp_shot - 5600.0) / 3400.0
                        a_shot = -norm * 8.0
                        b_shot = -norm * 12.0
                        score.delta_e_baseline = _compute_delta_e2000(
                            L_shot, a_shot, b_shot,
                            ref["L_mean"], ref["a_mean"], ref["b_mean"]
                        )
                except Exception:
                    pass

                # Skin tone — true if any frame had YOLO detections
                score.skin_tone_detected = any(
                    bool(fm.inference and fm.inference.detections)
                    for fm in scene_frames
                )

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
                            score.creative_total            = round(sim, 2)
                            score.style_family              = sim_result.get("cluster_label")
                            score.cluster_percentile        = sim_result.get("cluster_percentile")
                            pct_str = (f" · {sim_result['cluster_percentile']:.0f}th percentile"
                                       if sim_result.get("cluster_percentile") is not None else "")
                            score.rationale = (
                                f"Style: {sim_result.get('cluster_label', 'unknown')}{pct_str} "
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
            self._push_progress(job_id, "Selecting best shots…", 84)
            from ..agents.selection import select_shots
            selected = select_shots(shots, scores, job_dir, cfg, seed=seed)
            self._push_progress(job_id, f"Selected {len(selected)} shots", 90)

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
            # --- stage 8: shot clustering ---
            self._push_progress(job_id, "Clustering shots by visual similarity…", 92)
            try:
                from ..agents.scene_clusters import cluster_shots, attach_clusters_to_shots
                cluster_result = cluster_shots(selected, cfg)
                selected = attach_clusters_to_shots(selected, cluster_result)
                print(f"[bridge] {cluster_result.n_clusters} visual clusters")
            except Exception as _ce:
                print(f"[bridge] clustering skipped: {_ce}")
                cluster_result = None

            export_clips = bool(cfg.get("export", {}).get("export_clips", False))

            # Build maps needed for hero window extraction
            _scenes_map      = {s.scene_id: s for s in scenes}
            _shot_frames_map = {}
            for _shot in selected:
                # selected items are dicts from select_shots()
                _sid  = _shot.get("shot_id") if isinstance(_shot, dict) else _shot.shot_id
                _scid = _shot.get("scene_id") if isinstance(_shot, dict) else _shot.scene_id
                if _sid is not None:
                    _shot_frames_map[_sid] = scene_candidate_map.get(_scid, [])

            manifest_out = export_job(
                job_model, selected, job_dir, cfg,
                export_clips=export_clips,
                shot_frames_map=_shot_frames_map,
                scenes_map=_scenes_map,
            )

            self._push_progress(job_id, "Analysis complete", 100)

            # build UI-friendly shot list
            ui_shots = _build_ui_shots(selected)

            # Build cluster summary for UI
            ui_clusters = []
            if cluster_result:
                for c in cluster_result.clusters:
                    ui_clusters.append({
                        "cluster_id":    c.cluster_id,
                        "shot_ids":      c.shot_ids,
                        "representative":c.representative,
                        "label":         c.label,
                        "coherence":     c.coherence,
                        "mean_score":    c.mean_score,
                        "size":          len(c.shot_ids),
                    })

            return {
                "ok":            True,
                "shots":         ui_shots,
                "clusters":      ui_clusters,
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
        def _cat(key):
            """Pass through full category score dict; wrap scalar if old format."""
            v = scores.get(key)
            if isinstance(v, dict):
                return v
            return {"total": v, "technical": None, "creative": None, "subjective": None}

        ui_shots.append({
            "id":              s.get("rank"),
            "shot_id":         s.get("shot_id"),
            "scene_id":        s.get("scene_id"),
            "start":           s.get("start_time", 0.0),
            "end":             s.get("end_time",   0.0),
            "duration":        s.get("duration_sec", 0.0),
            "hero_frame":      s.get("hero_frame"),
            "totalScore":      s.get("total_score"),
            "technicalTotal":  s.get("technical_total"),
            "creativeTotal":   s.get("creative_total"),
            "subjectiveTotal": s.get("subjective_total"),
            "baseline_similarity": s.get("baseline_similarity"),
            "rationale":       s.get("rationale"),
            "movement_type":   s.get("movement_type"),
            "shot_scale":      s.get("shot_scale"),
            "scene_type":      s.get("scene_type"),
            "shot_intent":     s.get("shot_intent"),
            "scores": {
                "exposure":    _cat("exposure"),
                "lighting":    _cat("lighting"),
                "composition": _cat("composition"),
                "movement":    _cat("movement"),
                "color":       _cat("color"),
                "quality":     _cat("quality"),
                "narrative":   _cat("narrative"),
            },
            "metricDetail":     s.get("metric_detail", {}),
                "corpusScores":     s.get("corpus_scores", {}),
            "deltaED65":        s.get("delta_e_d65"),
            "deltaEBaseline":   s.get("delta_e_baseline"),
            "gamutCoverage":    s.get("gamut_coverage"),
            "dominantColours":  s.get("dominant_colours"),
            "perFrameColours":  s.get("per_frame_colours"),
            "waveform":         s.get("waveform"),
            "paradeR":          s.get("parade_r"),
            "paradeG":          s.get("parade_g"),
            "paradeB":          s.get("parade_b"),
            "skinToneDetected": s.get("skin_tone_detected", False),
            "clusterId":        s.get("cluster_id"),
            "isRepresentative": s.get("is_representative", False),
            "styleFamily":      s.get("style_family"),
            "clusterPct":       s.get("cluster_percentile"),
        })
    return ui_shots
# aesthetic/agents/export.py
#
# Export agent.
# Takes the final selected shots from selection.py and produces
# all editor-usable deliverables:
#
#   outputs/<job_id>/
#     frames/         — hero frames named with score prefix (sorts by quality)
#     clips/          — hero scene clips trimmed from source video
#     contact_sheet.jpg — tiled overview of all selected shots with scores
#     manifest.json   — full run record, every decision explained
#
# All paths are predictable and stable across runs with the same seed.
# The manifest is both human-readable and machine-parseable.

from __future__ import annotations

import json
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from ..config import OUTPUTS_DIR
from ..models.job import Job
from ..models.scores import Manifest


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_job(
    job:          Job,
    selected_shots: List[Dict[str, Any]],
    job_dir:      Path,
    config:       Dict[str, Any],
    export_clips: bool = False,
) -> Manifest:
    """
    Run the full export pipeline for a completed job.

    Args:
        job:             Completed Job model.
        selected_shots:  Output of selection.select_shots() — ranked shot dicts.
        job_dir:         Job working directory.
        config:          Full config dict.

    Returns:
        Populated Manifest model. Also writes all deliverables to disk.
    """
    output_dir = OUTPUTS_DIR / job.job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    frames_dir = output_dir / "frames"
    clips_dir  = output_dir / "clips"
    frames_dir.mkdir(exist_ok=True)
    clips_dir.mkdir(exist_ok=True)

    features = config.get("features", {})
    warnings: List[str] = []
    errors:   List[str] = []
    sidecars: List[str] = []
    timing:   Dict[str, float] = {}

    # --- hero frames ---
    import time
    t0 = time.time()
    hero_frame_paths = _export_hero_frames(selected_shots, frames_dir, warnings)
    timing["hero_frames"] = round(time.time() - t0, 2)

    # --- hero clips (only if requested) ---
    t0 = time.time()
    clip_paths = {}
    if export_clips:
        clip_paths = _export_hero_clips(
            selected_shots,
            job.source_file,
            clips_dir,
            warnings,
        )
    timing["hero_clips"] = round(time.time() - t0, 2)

    # --- EDL and CSV timecode list ---
    t0 = time.time()
    stem = Path(job.source_file).stem
    fps  = job.video_meta.fps if job.video_meta else 24.0
    edl_path = _export_edl(selected_shots, output_dir, stem, job.job_id, fps)
    csv_path = _export_csv(selected_shots, output_dir, stem, fps)
    timing["edl_csv"] = round(time.time() - t0, 2)

    # --- contact sheet ---
    t0 = time.time()
    contact_sheet_path = _export_contact_sheet(
        selected_shots,
        hero_frame_paths,
        output_dir,
        warnings,
    )
    timing["contact_sheet"] = round(time.time() - t0, 2)

    # --- collect sidecars ---
    metrics_dir = job_dir / "metrics"
    if metrics_dir.exists():
        sidecars = [str(p) for p in sorted(metrics_dir.glob("*.json"))]

    # --- build manifest ---
    manifest = Manifest(
        job_id=job.job_id,
        source_file=job.source_file,
        created=job.created,
        analyzed=_now_iso(),
        seed=job.seed,
        config=job.config,
        baseline_version=job.baseline_version,
        scene_count=len(job.scenes),
        candidate_count=sum(len(s.frame_paths) for s in job.shots) if job.shots else 0,
        selected_count=len(selected_shots),
        shots=selected_shots,
        sidecars=sidecars,
        contact_sheet=str(contact_sheet_path) if contact_sheet_path else None,
        hero_clips_dir=str(clips_dir),
        hero_frames_dir=str(frames_dir),
        pipeline_timing=timing,
        warnings=warnings,
        errors=errors,
    )

    # --- write manifest ---
    stem         = Path(job.source_file).stem
    manifest_path= output_dir / f"{stem}_{job.job_id}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_output_dict(), indent=2),
        encoding="utf-8",
    )

    return manifest


# ---------------------------------------------------------------------------
# Hero frames
# ---------------------------------------------------------------------------

def _export_hero_frames(
    shots:      List[Dict[str, Any]],
    frames_dir: Path,
    warnings:   List[str],
) -> Dict[str, Optional[str]]:
    """
    Copy hero frames to the output directory with score-prefixed names
    so they sort by quality in Finder/Explorer.

    Naming: <rank>_<score>_<shot_id>.jpg
    e.g.    01_091.2_shot_0003.jpg
    """
    paths: Dict[str, Optional[str]] = {}

    for shot in shots:
        shot_id    = shot.get("shot_id", "unknown")
        rank       = shot.get("rank", 0)
        score      = shot.get("total_score") or 0.0
        hero_frame = shot.get("hero_frame")

        if not hero_frame or not Path(hero_frame).exists():
            warnings.append(f"Hero frame missing for {shot_id}")
            paths[shot_id] = None
            continue

        out_name = f"{rank:02d}_{score:05.1f}_{shot_id}.jpg"
        out_path = frames_dir / out_name

        try:
            shutil.copy2(hero_frame, out_path)
            paths[shot_id] = str(out_path)
        except Exception as exc:
            warnings.append(f"Failed to copy hero frame for {shot_id}: {exc}")
            paths[shot_id] = None

    return paths


# ---------------------------------------------------------------------------
# Hero clips
# ---------------------------------------------------------------------------

def _export_hero_clips(
    shots:       List[Dict[str, Any]],
    source_file: str,
    clips_dir:   Path,
    warnings:    List[str],
) -> Dict[str, Optional[str]]:
    """
    Export a trimmed clip for each selected shot using ffmpeg.
    Uses stream copy (no re-encode) for speed and quality preservation.
    Falls back to re-encode if stream copy produces an unusable file.

    Naming: <rank>_<score>_<shot_id>.mp4
    """
    if not shutil.which("ffmpeg"):
        warnings.append("ffmpeg not on PATH — hero clip export skipped")
        return {}

    if not Path(source_file).exists():
        warnings.append(f"Source file not found for clip export: {source_file}")
        return {}

    paths: Dict[str, Optional[str]] = {}

    for shot in shots:
        shot_id    = shot.get("shot_id", "unknown")
        rank       = shot.get("rank", 0)
        score      = shot.get("total_score") or 0.0
        start_time = shot.get("start_time", 0.0)
        end_time   = shot.get("end_time", 0.0)
        duration   = end_time - start_time

        if duration <= 0:
            warnings.append(f"Invalid duration for {shot_id} — skipping clip")
            paths[shot_id] = None
            continue

        out_name = f"{rank:02d}_{score:05.1f}_{shot_id}.mp4"
        out_path = clips_dir / out_name

        success = _ffmpeg_trim(
            source_file=source_file,
            start_time=start_time,
            duration=duration,
            out_path=out_path,
        )

        if success:
            paths[shot_id] = str(out_path)
        else:
            warnings.append(f"Clip export failed for {shot_id}")
            paths[shot_id] = None

    return paths


def _ffmpeg_trim(
    source_file: str,
    start_time:  float,
    duration:    float,
    out_path:    Path,
) -> bool:
    """
    Trim a clip from source_file using ffmpeg stream copy.
    Returns True on success.
    """
    cmd = [
        "ffmpeg",
        "-ss",       str(round(start_time, 3)),
        "-i",        source_file,
        "-t",        str(round(duration, 3)),
        "-c",        "copy",        # stream copy — no re-encode
        "-avoid_negative_ts", "make_zero",
        "-y",
        str(out_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0 and out_path.exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Contact sheet
# ---------------------------------------------------------------------------

def _export_contact_sheet(
    shots:            List[Dict[str, Any]],
    hero_frame_paths: Dict[str, Optional[str]],
    output_dir:       Path,
    warnings:         List[str],
    thumb_w:          int = 320,
    thumb_h:          int = 180,
    cols:             int = 4,
    padding:          int = 8,
    header_h:         int = 40,
) -> Optional[Path]:
    """
    Generate a contact sheet — a tiled image of all selected shots
    with rank, score, and timecode overlaid on each thumbnail.
    """
    if not shots:
        return None

    # collect valid thumbnails
    thumbs = []
    for shot in shots:
        shot_id = shot.get("shot_id", "unknown")
        path    = hero_frame_paths.get(shot_id)

        if path and Path(path).exists():
            img = cv2.imread(path)
            if img is not None:
                img = cv2.resize(img, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
                thumbs.append((img, shot))
                continue

        # placeholder for missing frame
        placeholder = np.zeros((thumb_h, thumb_w, 3), dtype=np.uint8)
        placeholder[:] = (40, 40, 40)
        thumbs.append((placeholder, shot))

    if not thumbs:
        warnings.append("No thumbnails available for contact sheet")
        return None

    rows = (len(thumbs) + cols - 1) // cols

    sheet_w = cols * (thumb_w + padding) + padding
    sheet_h = header_h + rows * (thumb_h + padding + 40) + padding
    sheet   = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
    sheet[:] = (20, 20, 20)

    # header
    cv2.putText(
        sheet, "AESTHETIC — Selected Shots",
        (padding, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA,
    )

    for i, (thumb, shot) in enumerate(thumbs):
        row = i // cols
        col = i  % cols

        x = padding + col * (thumb_w + padding)
        y = header_h + row * (thumb_h + padding + 30)

        # place thumbnail
        sheet[y:y+thumb_h, x:x+thumb_w] = thumb

        # overlay border
        rank  = shot.get("rank", i + 1)
        score        = shot.get("total_score") or 0.0
        start        = shot.get("start_time", 0.0)
        end          = shot.get("end_time",   0.0)
        scale        = shot.get("shot_scale",    "")
        movement     = shot.get("movement_type", "")
        scene_type   = shot.get("scene_type",    "")
        shot_intent  = shot.get("shot_intent",   "")

        # score-based border color
        if score >= 75:
            border_color = (75, 200, 100)
        elif score >= 55:
            border_color = (75, 180, 220)
        else:
            border_color = (100, 100, 200)

        cv2.rectangle(sheet, (x, y), (x+thumb_w, y+thumb_h), border_color, 2)

        # score badge top-left
        badge_text = f"#{rank}  {score:.1f}"
        cv2.rectangle(sheet, (x, y), (x+90, y+20), (0, 0, 0), -1)
        cv2.putText(
            sheet, badge_text,
            (x+4, y+14),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42, border_color, 1, cv2.LINE_AA,
        )

        # strongest category badge top-right
        scores_dict = shot.get("scores", {})
        if scores_dict:
            best_cat = max(scores_dict.items(), key=lambda kv: kv[1] or 0, default=(None, None))
            if best_cat[0]:
                cat_label = best_cat[0][:3].upper()   # EXP / LIT / COM / MOV / COL / QUA / NAR
                cv2.rectangle(sheet, (x+thumb_w-36, y), (x+thumb_w, y+20), (0, 0, 0), -1)
                cv2.putText(
                    sheet, cat_label,
                    (x+thumb_w-32, y+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 100), 1, cv2.LINE_AA,
                )

        # classification tags below thumbnail
        # line 1: timecode + duration
        tc_text = f"{_fmt_tc(start)}-{_fmt_tc(end)}"
        cv2.putText(
            sheet, tc_text,
            (x, y + thumb_h + 14),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1, cv2.LINE_AA,
        )

        # line 2: scale + movement icons
        scale_abbr   = _abbrev_scale(scale)
        movement_sym = _symbol_movement(movement)
        intent_abbr  = shot_intent[:3].upper() if shot_intent and shot_intent != "unknown" else ""
        tag_text     = " ".join(filter(None, [scale_abbr, movement_sym, intent_abbr]))
        if tag_text:
            cv2.putText(
                sheet, tag_text,
                (x, y + thumb_h + 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (120, 140, 180), 1, cv2.LINE_AA,
            )

    out_path = output_dir / "contact_sheet.jpg"
    cv2.imwrite(str(out_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out_path


def _abbrev_scale(scale: str) -> str:
    """Short label for shot scale annotation on contact sheet."""
    mapping = {
        "extreme_close": "ECU",
        "close":         "CU",
        "medium_close":  "MCU",
        "medium":        "MS",
        "medium_wide":   "MWS",
        "wide":          "WS",
        "extreme_wide":  "EWS",
    }
    return mapping.get(scale, "")


def _symbol_movement(movement: str) -> str:
    """Short symbol for movement type annotation on contact sheet."""
    mapping = {
        "static":   "●",
        "pan":      "→",
        "tilt":     "↑",
        "dolly":    "▶",
        "handheld": "~",
        "drone":    "^",
    }
    return mapping.get(movement, "")


def _fmt_tc(seconds: float) -> str:
    """Format seconds as MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# EDL export (CMX 3600)
# ---------------------------------------------------------------------------

def _export_edl(
    shots:      List[Dict[str, Any]],
    output_dir: Path,
    stem:       str,
    job_id:     str,
    fps:        float = 24.0,
) -> Optional[Path]:
    """
    Export a CMX 3600 EDL using the actual source frame rate.
    Handles drop-frame timecode for 29.97 and 59.94 fps.
    Importable directly into Premiere Pro, DaVinci Resolve, and Avid.
    """
    if not shots:
        return None

    try:
        drop_frame = _is_drop_frame(fps)
        fc         = _fcm_string(fps)

        lines = []
        lines.append(f"TITLE: AESTHETIC — {stem}")
        lines.append(f"FCM: {fc}")
        lines.append("")

        record_start_sec = 3600.0

        for shot in shots:
            event_num  = shot.get("rank", 1)
            start_time = float(shot.get("start_time", 0.0))
            end_time   = float(shot.get("end_time",   0.0))
            duration   = end_time - start_time
            score      = shot.get("total_score") or 0.0
            shot_id    = shot.get("shot_id", f"shot_{event_num:04d}")

            src_in  = _seconds_to_tc(start_time,              fps, drop_frame)
            src_out = _seconds_to_tc(end_time,                fps, drop_frame)
            rec_in  = _seconds_to_tc(record_start_sec,        fps, drop_frame)
            rec_out = _seconds_to_tc(record_start_sec + duration, fps, drop_frame)

            lines.append(f"{event_num:03d}  AX  V  C  {src_in} {src_out} {rec_in} {rec_out}")
            lines.append(f"* FROM CLIP NAME: {stem}")
            lines.append(f"* AESTHETIC: {shot_id} | Score: {score:.1f} | FPS: {fps:.3f}")
            lines.append("")

            record_start_sec += duration

        edl_path = output_dir / f"{stem}_{job_id}.edl"
        edl_path.write_text("\n".join(lines), encoding="utf-8")
        return edl_path

    except Exception as exc:
        print(f"[export] EDL generation failed: {exc}")
        return None


def _is_drop_frame(fps: float) -> bool:
    """Return True if this frame rate uses drop-frame timecode."""
    return abs(fps - 29.97) < 0.01 or abs(fps - 59.94) < 0.01


def _fcm_string(fps: float) -> str:
    """Return the FCM header string for a given frame rate."""
    if _is_drop_frame(fps):
        return "DROP FRAME"
    return "NON-DROP FRAME"


def _seconds_to_tc(seconds: float, fps: float = 24.0, drop_frame: bool = False) -> str:
    """
    Convert seconds to SMPTE timecode string HH:MM:SS:FF (or HH:MM:SS;FF for drop-frame).

    Drop-frame timecode (used for 29.97 and 59.94 fps) skips frame numbers 00 and 01
    at the start of each minute, except every 10th minute, to compensate for the
    fractional frame rate. This keeps wall-clock time accurate over long durations.

    Non-drop frame timecode is used for all other rates (24, 25, 30, 48, 50, 60).
    """
    if drop_frame:
        return _seconds_to_df_tc(seconds, fps)

    nominal_fps = round(fps)
    total_frames = int(round(seconds * fps))
    ff = total_frames % nominal_fps
    ss = (total_frames // nominal_fps) % 60
    mm = (total_frames // nominal_fps // 60) % 60
    hh = total_frames // nominal_fps // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _seconds_to_df_tc(seconds: float, fps: float = 29.97) -> str:
    """
    Convert seconds to drop-frame SMPTE timecode (HH:MM:SS;FF).
    Uses the standard SMPTE drop-frame calculation.
    """
    # nominal fps for drop-frame is always the rounded value
    nominal = round(fps)
    drop_frames = 2 if nominal == 30 else 4   # 2 for 29.97, 4 for 59.94

    total_frames  = int(round(seconds * fps))
    frames_per_10 = nominal * 60 * 10 - drop_frames * 9
    frames_per_1  = nominal * 60 - drop_frames

    d, m = divmod(total_frames, frames_per_10)
    hh   = d // 6
    mm10 = d % 6

    if m < nominal * 60:
        mm1 = 0
        ff  = m
    else:
        m  -= nominal * 60
        mm1, ff = divmod(m, frames_per_1)
        mm1 += 1

    mm = mm10 * 10 + mm1
    ss, ff = divmod(ff, nominal)

    # handle overflow
    if ss >= 60:
        ss -= 60
        mm += 1
    if mm >= 60:
        mm -= 60
        hh += 1

    return f"{hh:02d}:{mm:02d}:{ss:02d};{ff:02d}"


# ---------------------------------------------------------------------------
# CSV timecode list
# ---------------------------------------------------------------------------

def _export_csv(
    shots:      List[Dict[str, Any]],
    output_dir: Path,
    stem:       str,
    fps:        float = 24.0,
) -> Optional[Path]:
    """
    Export a simple CSV timecode list using the actual source frame rate.
    """
    if not shots:
        return None

    try:
        import csv
        import io

        drop_frame = _is_drop_frame(fps)

        fieldnames = [
            "rank", "shot_id", "scene_id",
            "start_tc", "end_tc",
            "start_sec", "end_sec", "duration_sec",
            "fps",
            "total_score", "technical", "creative", "subjective",
            "exposure", "lighting", "composition",
            "movement", "color", "quality", "narrative",
            "baseline_similarity", "temporal_variance",
            "movement_type", "shot_scale",
        ]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()

        for shot in shots:
            scores = shot.get("scores", {})
            start  = float(shot.get("start_time", 0.0))
            end    = float(shot.get("end_time",   0.0))
            writer.writerow({
                "rank":               shot.get("rank"),
                "shot_id":            shot.get("shot_id"),
                "scene_id":           shot.get("scene_id"),
                "start_tc":           _seconds_to_tc(start, fps, drop_frame),
                "end_tc":             _seconds_to_tc(end,   fps, drop_frame),
                "start_sec":          round(start, 3),
                "end_sec":            round(end, 3),
                "duration_sec":       round(end - start, 3),
                "fps":                round(fps, 3),
                "total_score":        shot.get("total_score"),
                "technical":          shot.get("technical_total"),
                "creative":           shot.get("creative_total"),
                "subjective":         shot.get("subjective_total"),
                "exposure":           scores.get("exposure"),
                "lighting":           scores.get("lighting"),
                "composition":        scores.get("composition"),
                "movement":           scores.get("movement"),
                "color":              scores.get("color"),
                "quality":            scores.get("quality"),
                "narrative":          scores.get("narrative"),
                "baseline_similarity":shot.get("baseline_similarity"),
                "temporal_variance":  shot.get("temporal_variance"),
                "movement_type":      shot.get("movement_type"),
                "shot_scale":         shot.get("shot_scale"),
            })

        csv_path = output_dir / f"{stem}_selects.csv"
        csv_path.write_text(buf.getvalue(), encoding="utf-8")
        return csv_path

    except Exception as exc:
        print(f"[export] CSV generation failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
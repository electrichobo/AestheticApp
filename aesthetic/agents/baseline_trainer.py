# aesthetic/agents/baseline_trainer.py
#
# Golden Baseline trainer.
# Ingests reference stills (or extracted video frames) from a source folder,
# generates CLIP embeddings for each, and stores them in the BaselineStore.
#
# Workflow:
#   1. Scan source folder for image files
#   2. For each image, generate a CLIP embedding via the inference pipeline
#   3. Store embeddings in the staging buffer of BaselineStore
#   4. Optionally promote staging to a new versioned golden file
#
# The baseline stores two things per reference still:
#   - The CLIP embedding vector (for Creative pillar cosine similarity scoring)
#   - Technical metric summary (for Subjective pillar reference distribution)
#
# Adding new material:
#   - New stills go into augment buffer, not staging
#   - Augment is merged with the active golden on next promotion
#   - This preserves the original corpus while extending it
#
# Version history is immutable — every golden version is kept on disk.
# Manifests reference the version hash so results are always reproducible.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..baseline import BaselineStore
from ..agents.inference import _run_clip, _get_device
from ..agents.metrics import compute_frame_metrics
from ..config import DATA_DIR


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def train_baseline_from_folder(
    source_dir:  str,
    data_dir:    Path,
    config:      Dict[str, Any],
    note:        str = "",
    mode:        str = "staging",
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Ingest all images in source_dir and add them to the Golden Baseline.

    Args:
        source_dir:  Path to folder containing reference stills.
        data_dir:    Root data directory (baseline lives under data_dir/baseline/).
        config:      Full config dict.
        note:        Description stamped into the golden version metadata.
        mode:        "staging" for initial corpus build (promotes to new golden).
                     "augment" for adding new material to an existing golden.
        progress_cb: Optional callback(current, total, filename) for UI progress.

    Returns:
        Summary dict with counts and baseline version info.
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        return {"ok": False, "error": f"Source directory not found: {source_dir}"}

    images = _scan_images(source_path)
    if not images:
        return {"ok": False, "error": f"No supported image files found in: {source_dir}"}

    features  = config.get("features", {})
    gpu       = bool(features.get("gpu_enabled", False))
    device    = _get_device(gpu)

    store     = BaselineStore(data_dir)
    processed = 0
    failed    = 0
    errors    = []

    for idx, img_path in enumerate(images, start=1):
        if progress_cb:
            progress_cb(idx, len(images), img_path.name)

        result = _process_reference_still(img_path, device, config, data_dir)

        if result is None:
            failed += 1
            errors.append(str(img_path.name))
            continue

        # result is None for both failures and QC rejections

        # add to the appropriate buffer
        if mode == "augment":
            store.update_augment([result])
        else:
            store.update_staging([result])

        processed += 1

    # promote to golden
    promotion: Dict[str, Any] = {}
    if processed > 0:
        if mode == "augment":
            promotion = store.apply_augment_to_new_golden(
                note=note or f"augmented with {processed} new stills"
            )
        else:
            promotion = store.promote_staging_to_golden(
                note=note or f"initial corpus: {processed} reference stills"
            )

    qc_rejected = failed  # failed includes QC rejections
    return {
        "ok":          True,
        "processed":   processed,
        "failed":      qc_rejected,
        "errors":      errors[:20],
        "promotion":   promotion,
        "total":       len(images),
        "qc_pass_rate": round(processed / len(images) * 100, 1) if images else 0,
    }


def get_baseline_status(data_dir: Path) -> Dict[str, Any]:
    """
    Return a summary of the current baseline state for UI display.
    """
    store = BaselineStore(data_dir)
    return store.get_summary()


def train_baseline_from_video(
    video_path:           str,
    data_dir:             Path,
    config:               Dict[str, Any],
    note:                 str = "",
    sensitivity:          int = 50,
    per_scene_candidates: int = 6,
    progress_cb:          Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Ingest a reference video file into the Golden Baseline corpus.

    Runs the full pipeline on the video — ingest, scene detection, candidate
    sampling, full metrics engine, CLIP embedding — and pushes results into
    the augment buffer, then merges with the active golden to produce a new
    versioned snapshot.

    This is always an AUGMENT operation — it never replaces the existing
    corpus. The stills already in the baseline are preserved.

    Video frames provide metrics that stills cannot:
      - Optical flow, smoothness, stabilization, jerkiness
      - Temporal exposure consistency
      - Motion blur amount and direction
      - Movement type classification
      - Path trajectory
      - Cross-frame color and lighting consistency

    Args:
        video_path:           Absolute path to the reference video file.
        data_dir:             Root data directory.
        config:               Full config dict.
        note:                 Description stamped into the golden version.
                              Defaults to the video filename.
        sensitivity:          Scene detection sensitivity (1-100).
        per_scene_candidates: Frames to sample per scene. Lower = faster,
                              higher = richer baseline. 6 is a good default.
        progress_cb:          Optional callback(current, total, stage_name).

    Returns:
        Summary dict with scene count, frame count, and baseline version info.
    """
    from ..agents.ingest  import ingest
    from ..agents.scenes  import detect_scenes, sensitivity_to_threshold
    from ..agents.sampling import sample_candidates
    from ..agents.metrics import compute_frame_metrics
    from ..agents.inference import run_frame_inference

    video_path = str(video_path)
    video_file = Path(video_path)

    if not video_file.exists():
        return {"ok": False, "error": f"Video file not found: {video_path}"}

    features = config.get("features", {})
    gpu      = bool(features.get("gpu_enabled", False))
    device   = _get_device(gpu)
    seed     = config.get("runtime", {}).get("seed", 42)
    store    = BaselineStore(data_dir)

    # working directory for this video's extracted frames
    work_dir = data_dir / "baseline" / "video_work" / video_file.stem[:32]
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # --- stage 1: ingest ---
        if progress_cb:
            progress_cb(0, 100, f"Ingesting {video_file.name}…")
        video_meta = ingest(video_path)

        # --- stage 2: scene detection ---
        if progress_cb:
            progress_cb(5, 100, f"Detecting scenes…")
        threshold = sensitivity_to_threshold(sensitivity)
        scenes    = detect_scenes(
            video_meta, work_dir,
            threshold=threshold,
            config=config,
            seed=seed,
        )
        if progress_cb:
            progress_cb(15, 100, f"Found {len(scenes)} scenes")

        # --- stage 3: sample candidates ---
        if progress_cb:
            progress_cb(20, 100, "Sampling candidate frames…")
        candidates = sample_candidates(
            video_meta, scenes, work_dir,
            per_scene_candidates=per_scene_candidates,
            seed=seed,
        )
        total_frames = len(candidates)
        if progress_cb:
            progress_cb(30, 100, f"Extracted {total_frames} candidate frames")

        # --- stage 4: metrics + inference (parallel, CPU-capped, resumable) ---
        from collections import defaultdict
        by_scene = defaultdict(list)
        for c in candidates:
            by_scene[c.scene_id].append(c)

        # --- resume: skip frames already in the embeddings index ---
        embeddings_dir = data_dir / "baseline" / "embeddings"
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        already_done = {p.stem for p in embeddings_dir.glob("*.json")}

        remaining = [c for c in candidates if Path(c.path).stem[:64] not in already_done]
        skipped   = total_frames - len(remaining)
        if skipped > 0:
            if progress_cb:
                progress_cb(30, 100, f"Resuming — skipping {skipped} already-processed frames")
            print(f"[baseline_trainer] resume: skipping {skipped} frames, {len(remaining)} remaining")
        total_remaining = len(remaining)

        processed = skipped   # count resumed frames as processed
        failed    = 0

        if total_remaining == 0:
            if progress_cb:
                progress_cb(90, 100, "All frames already processed — skipping to promotion")
        else:
            # --- determine worker count based on CPU cap ---
            import psutil
            import concurrent.futures
            import time as _time

            cpu_cap_pct  = float(config.get("runtime", {}).get("cpu_cap_pct", 60.0))
            physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 4
            # use floor of (cap * physical_cores), minimum 1, maximum physical_cores - 1
            # keep at least one core free for the OS and UI
            max_workers  = max(1, min(
                physical_cores - 1,
                int(physical_cores * cpu_cap_pct / 100.0)
            ))
            print(f"[baseline_trainer] using {max_workers}/{physical_cores} cores "
                  f"(cap: {cpu_cap_pct:.0f}%)")
            if progress_cb:
                progress_cb(30, 100,
                    f"Processing {total_remaining} frames on {max_workers} cores "
                    f"({cpu_cap_pct:.0f}% CPU cap)…")

            # --- detect repo root for subprocess sys.path injection ---
            import os as _os
            repo_root = str(Path(__file__).resolve().parents[3])
            if not _os.path.isfile(_os.path.join(repo_root, 'aesthetic', '__init__.py')):
                # fallback: walk up until we find the aesthetic package
                p = Path(__file__).resolve()
                for _ in range(6):
                    p = p.parent
                    if (p / 'aesthetic' / '__init__.py').exists():
                        repo_root = str(p)
                        break

            # --- build per-frame args list ---
            frame_args = []
            for c in remaining:
                scene_cands  = by_scene[c.scene_id]
                idx_in_scene = scene_cands.index(c)
                prev_path    = scene_cands[idx_in_scene - 1].path if idx_in_scene > 0 else None
                frame_args.append((c.path, c.scene_id, c.timestamp, str(work_dir), config, prev_path, repo_root))

            # --- parallel metrics (CPU-bound, process pool) ---
            metrics_results = {}   # path -> FrameMetrics
            t_start = _time.time()
            completed_count = 0

            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(_compute_frame_metrics_worker, args): args[0]
                    for args in frame_args
                }
                for future in concurrent.futures.as_completed(future_map):
                    frame_path = future_map[future]
                    completed_count += 1
                    try:
                        fm = future.result()
                        if fm is not None:
                            metrics_results[frame_path] = fm
                    except Exception as exc:
                        failed += 1
                        print(f"[baseline_trainer] metrics failed for {frame_path}: {exc}")

                    # progress + ETA every frame
                    if progress_cb and completed_count % 5 == 0:
                        elapsed  = _time.time() - t_start
                        rate     = completed_count / elapsed if elapsed > 0 else 1
                        remaining_frames = total_remaining - completed_count
                        eta_sec  = remaining_frames / rate if rate > 0 else 0
                        eta_str  = _fmt_eta(eta_sec)
                        pct      = 30 + int((completed_count / total_remaining) * 55)
                        progress_cb(
                            pct, 100,
                            f"Metrics: {completed_count}/{total_remaining} frames "
                            f"({rate:.1f}/s) — ETA {eta_str}"
                        )

                    # adaptive throttle: if CPU usage exceeds cap, pause briefly
                    if completed_count % 20 == 0:
                        cpu_now = psutil.cpu_percent(interval=0.1)
                        if cpu_now > cpu_cap_pct + 15:
                            _time.sleep(0.5)

            # --- CLIP inference (GPU, batched, main thread) ---
            # MiDaS depth is disabled for baseline ingest — it generates large
            # PNG files per frame and the depth_separation metric is already
            # computed from the Laplacian pyramid in the metrics engine.
            # This alone saves 5+ GB per feature film ingested.
            baseline_features = dict(features)
            baseline_features["midas_enabled"] = False
            baseline_config   = dict(config)
            baseline_config["features"] = baseline_features

            if baseline_features.get("clip_enabled", True) and metrics_results:
                if progress_cb:
                    progress_cb(86, 100, f"Running CLIP on {len(metrics_results)} frames…")
                clip_count = 0
                for frame_path, fm in metrics_results.items():
                    try:
                        fm = run_frame_inference(fm, frame_path, work_dir, baseline_config)
                        metrics_results[frame_path] = fm
                        clip_count += 1
                        if progress_cb and clip_count % 100 == 0:
                            progress_cb(86, 100, f"CLIP: {clip_count}/{len(metrics_results)} frames…")
                    except Exception as exc:
                        print(f"[baseline_trainer] CLIP failed for {frame_path}: {exc}")

            # --- write results to store ---
            if progress_cb:
                progress_cb(90, 100, "Writing records to baseline store…")
            for frame_path, fm in metrics_results.items():
                record = _frame_metrics_to_baseline_record(fm)
                if record:
                    store.update_augment([record])
                    if fm.inference.clip_embedding:
                        _store_embedding(
                            Path(frame_path),
                            fm.inference.clip_embedding,
                            fm.inference.clip_model_version,
                            data_dir,
                        )
                    processed += 1
                else:
                    failed += 1

        # --- stage 4b: cleanup working files ---
        # frames, depth maps, and metrics sidecars are not needed after embeddings
        # are stored. Delete them to reclaim disk space.
        if progress_cb:
            progress_cb(91, 100, "Cleaning up working files…")
        _cleanup_video_work(work_dir)

        # --- stage 5: promote augment to new golden ---
        if progress_cb:
            progress_cb(92, 100, "Promoting to new golden version…")

        promotion: Dict[str, Any] = {}
        if processed > 0:
            film_note = note or f"reference video: {video_file.name} ({processed} frames)"
            promotion = store.apply_augment_to_new_golden(note=film_note)

        if progress_cb:
            progress_cb(100, 100, "Done")

        return {
            "ok":            True,
            "video":         video_file.name,
            "scene_count":   len(scenes),
            "frame_count":   total_frames,
            "processed":     processed,
            "failed":        failed,
            "promotion":     promotion,
        }

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cleanup_video_work(work_dir: Path) -> None:
    """
    Delete temporary working files after baseline video ingest completes.
    Keeps only the embeddings (stored separately in data/baseline/embeddings/).
    Deletes: extracted frames, MiDaS depth maps, metrics sidecars.
    The work_dir itself is left in place (empty) so resume detection still works.
    """
    import shutil
    deleted_bytes = 0
    for subdir in ["frames", "depth", "metrics"]:
        target = work_dir / subdir
        if target.exists():
            try:
                size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                shutil.rmtree(target)
                deleted_bytes += size
                print(f"[baseline_trainer] cleaned up {subdir}/ ({size / 1024**2:.0f} MB)")
            except Exception as exc:
                print(f"[baseline_trainer] cleanup warning for {subdir}: {exc}")
    if deleted_bytes > 0:
        print(f"[baseline_trainer] total reclaimed: {deleted_bytes / 1024**3:.2f} GB")


def _fmt_eta(seconds: float) -> str:
    """Format seconds into a human-readable ETA string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


def _compute_frame_metrics_worker(args: tuple):
    """
    Worker function for ProcessPoolExecutor.
    Runs in a separate process — must be a module-level function.
    Injects the repo root into sys.path so aesthetic is importable
    regardless of how the subprocess was spawned (pywebview, IDE, CLI).
    """
    frame_path, scene_id, timestamp, work_dir_str, config, prev_frame_path, repo_root = args
    import sys
    from pathlib import Path

    # ensure the repo root is on the path in this subprocess
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from aesthetic.agents.metrics import compute_frame_metrics
        fm = compute_frame_metrics(
            frame_path, scene_id, timestamp,
            Path(work_dir_str), config,
            prev_frame_path=prev_frame_path,
        )
        return fm
    except Exception as exc:
        print(f"[worker] metrics failed for {frame_path}: {exc}")
        return None


def _frame_metrics_to_baseline_record(fm) -> Optional[Dict[str, float]]:
    """
    Convert a full FrameMetrics object into a flat dict for BaselineStore.
    Covers all 48+ metrics including the temporal/video-only ones that
    stills cannot provide.
    """
    record: Dict[str, float] = {}

    def _add(key: str, val) -> None:
        if val is not None and isinstance(val, (int, float)):
            record[key] = round(float(val), 6)

    e = fm.exposure
    _add("histogram_mean",      e.histogram_mean)
    _add("histogram_median",    e.histogram_median)
    _add("histogram_std",       e.histogram_std)
    _add("histogram_skew",      e.histogram_skew)
    _add("histogram_kurtosis",  e.histogram_kurtosis)
    _add("highlight_clip_pct",  e.highlight_clip_pct)
    _add("shadow_clip_pct",     e.shadow_clip_pct)
    _add("psnr",                e.psnr)
    _add("ssim",                e.ssim)
    _add("third_moment_18gray", e.third_moment_18gray)
    _add("snr_luma",            e.snr_luma)
    _add("snr_chroma",          e.snr_chroma)
    _add("temporal_consistency",e.temporal_consistency)
    _add("exposure_intent",     e.exposure_intent)

    li = fm.lighting
    _add("dynamic_range_stops", li.dynamic_range_stops)
    _add("key_fill_ratio",      li.key_fill_ratio)
    _add("color_temp_kelvin",   li.color_temp_kelvin)
    _add("color_temp_deviation",li.color_temp_deviation)
    _add("shadow_detail",       li.shadow_detail)
    _add("shadow_noise",        li.shadow_noise)
    _add("transition_hardness", li.transition_hardness)
    _add("light_motivation",    li.light_motivation)

    co = fm.composition
    _add("rule_of_thirds",      co.rule_of_thirds)
    _add("face_placement",      co.face_placement)
    _add("center_of_mass_x",    co.center_of_mass_x)
    _add("center_of_mass_y",    co.center_of_mass_y)
    _add("negative_space_ratio",co.negative_space_ratio)
    _add("depth_separation",    co.depth_separation)
    _add("occupancy_map_score", co.occupancy_map_score)
    _add("symmetry_score",      co.symmetry_score)
    _add("headroom",            co.headroom)
    _add("lead_room",           co.lead_room)
    _add("frame_balance",       co.frame_balance)

    mv = fm.movement
    _add("optical_flow_mean",     mv.optical_flow_mean)
    _add("optical_flow_std",      mv.optical_flow_std)
    _add("smoothness",            mv.smoothness)
    _add("jerkiness",             mv.jerkiness)
    _add("stabilization",         mv.stabilization)
    _add("motion_blur_amount",    mv.motion_blur_amount)
    _add("motion_blur_direction", mv.motion_blur_direction)
    _add("focus_during_movement", mv.focus_during_movement)
    _add("trajectory_smoothness", mv.trajectory_smoothness)

    cl = fm.color
    _add("wb_deviation",          cl.wb_deviation)
    _add("saturation_mean",       cl.saturation_mean)
    _add("saturation_uniformity", cl.saturation_uniformity)
    _add("palette_entropy",       cl.palette_entropy)
    _add("chroma_noise",          cl.chroma_noise)
    _add("banding_score",         cl.banding_score)
    if cl.palette_family is not None:
        fam_map = {"desaturated":0,"dark":1,"bright":2,"warm":3,"cool":4,"neutral":5}
        record["palette_family_id"] = float(fam_map.get(cl.palette_family, 5))

    qu = fm.quality
    _add("sharpness_laplacian",    qu.sharpness_laplacian)
    _add("sharpness_edge_density", qu.sharpness_edge_density)
    _add("mtf_proxy",              qu.mtf_proxy)
    _add("vignetting_stops",       qu.vignetting_stops)
    _add("ca_width_px",            qu.ca_width_px)
    _add("flare_contrast_loss",    qu.flare_contrast_loss)
    _add("compression_blocking",   qu.compression_blocking)
    _add("compression_banding",    qu.compression_banding)
    _add("compression_mosquito",   qu.compression_mosquito)
    _add("compression_ringing",    qu.compression_ringing)
    _add("texture_retention",      qu.texture_retention)

    na = fm.narrative
    _add("saliency_consistency", na.saliency_consistency)
    _add("compelling_mos",       na.compelling_mos)

    _add("clip_embedding_dim", float(len(fm.inference.clip_embedding)) if fm.inference.clip_embedding else None)

    return record if record else None


# ---------------------------------------------------------------------------
# Per-image processing
# ---------------------------------------------------------------------------

def _process_reference_still(
    img_path: Path,
    device:   str,
    config:   Dict[str, Any],
    data_dir: Path,
) -> Optional[Dict[str, Any]]:
    """
    Process a single reference still:
    - Validate it can be loaded
    - Run corpus QC checks — reject unsuitable images
    - Generate CLIP embedding
    - Compute full technical metric summary
    - Return a flat dict suitable for BaselineStore.update_staging()

    Returns None on failure or QC rejection.
    """
    try:
        # validate image loads
        img = cv2.imread(str(img_path))
        if img is None:
            return None

        # --- Corpus QC pass ---
        qc_result = _corpus_qc(img, img_path)
        if not qc_result["pass"]:
            print(f"[trainer] QC rejected {img_path.name}: {qc_result['reason']}")
            return None

        # CLIP embedding
        embedding, version = _run_clip(str(img_path), device)
        if embedding is None:
            return None

        # full technical metrics
        tech = _compute_reference_metrics(img)

        # build the record stored in BaselineStore
        record: Dict[str, Any] = {"clip_embedding_dim": float(len(embedding))}
        record.update({k: v for k, v in tech.items() if isinstance(v, (int, float))})

        # store embedding separately
        _store_embedding(img_path, embedding, version, data_dir)

        return record

    except Exception as exc:
        print(f"[trainer] Failed to process {img_path.name}: {exc}")
        return None


def _corpus_qc(img: np.ndarray, img_path: Path) -> Dict[str, Any]:
    """
    Run quality control checks on a reference still before ingesting it.
    Returns {"pass": True} or {"pass": False, "reason": "..."}.

    Checks:
    1. Minimum resolution — too small to contain meaningful cinematic information
    2. Cinema aspect ratio — reject portrait, square, or non-widescreen images
    3. Non-cinematic content — title cards, graphics, logos
    4. Subtitle/watermark detection — text in the lower third
    5. Suspect sharpness profile — upscaled or artificially processed images
    """
    h, w = img.shape[:2]

    # 1. minimum resolution
    if w < 480 or h < 270:
        return {"pass": False, "reason": f"resolution too low ({w}x{h})"}

    # 2. aspect ratio — must be roughly widescreen (wider than 1.2:1)
    ar = w / h
    if ar < 1.2:
        return {"pass": False, "reason": f"non-widescreen aspect ratio ({ar:.2f})"}

    # 3. non-cinematic content — reuse our title card signals
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    flat = gray.flatten()
    lab  = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    hsv  = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    nc_flags = 0

    # low color entropy — title cards have near-zero hue variety
    hue_flat  = hsv[:, :, 0].flatten().astype(np.float32)
    hist_h, _ = np.histogram(hue_flat, bins=36, range=(0, 180))
    hist_h    = hist_h.astype(np.float32) + 1e-6
    hist_h   /= hist_h.sum()
    entropy   = float(-np.sum(hist_h * np.log2(hist_h)))
    if entropy < 2.5:
        nc_flags += 1

    # low saturation — black/white/grey has zero chroma
    # OpenCV 8-bit Lab has a*/b* centred at 128 — subtract before measuring
    a_ch   = lab[:, :, 1].astype(np.float32) - 128.0
    b_ch   = lab[:, :, 2].astype(np.float32) - 128.0
    chroma = np.sqrt(a_ch**2 + b_ch**2)
    sat_mean = float(np.mean(chroma))
    if sat_mean < 8.0:
        nc_flags += 1

    # bimodal histogram — title cards have pixels clustered at extremes (black + white)
    # measure fraction of pixels in the two extreme deciles vs the middle
    p10 = float(np.percentile(flat, 10))
    p90 = float(np.percentile(flat, 90))
    extreme_px = float(np.mean((flat < p10 + 10) | (flat > p90 - 10)))
    if extreme_px > 0.85:
        nc_flags += 1

    # very sparse content — almost no mid-tone pixels
    bg_thresh = float(np.percentile(gray, 20))
    occ = float(np.mean(gray > bg_thresh * 1.5))
    if occ < 0.10:
        nc_flags += 1

    # zero saturation — perfectly achromatic content (0 chroma pixels)
    zero_sat_pct = float(np.mean(chroma < 2.0))
    if zero_sat_pct > 0.90:
        nc_flags += 1

    if nc_flags >= 3:
        return {"pass": False, "reason": "non-cinematic content (title card / logo / graphic)"}

    # 4. subtitle / watermark detection — look for horizontal text bands
    #    in the lower 20% of the frame (subtitle zone)
    # Subtitle text produces edges that are denser at the top/bottom of each
    # character row than in the interior — measure variance of horizontal
    # edge density across rows. Random noise has uniform row-by-row density.
    lower_band = gray[int(h * 0.80):, :]
    edges      = cv2.Canny(lower_band.astype(np.uint8), 50, 150)
    # per-row edge density
    row_densities = np.mean(edges > 0, axis=1).astype(np.float32)
    # subtitle text: rows alternate dense (text) and sparse (gaps between lines)
    row_variance  = float(np.var(row_densities))
    h_grad        = cv2.Sobel(lower_band.astype(np.uint8), cv2.CV_32F, 1, 0, ksize=3)
    h_density     = float(np.mean(np.abs(h_grad)))
    overall_edge  = float(np.mean(edges > 0))
    # require both high density AND structured row variance (not random noise)
    if h_density > 25.0 and overall_edge > 0.08 and row_variance > 0.02:
        return {"pass": False, "reason": "possible subtitles or watermark in lower third"}

    # 5. suspect sharpness profile — very high Laplacian variance
    #    combined with very low texture retention = artificial sharpening
    lap     = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
    lap_var = float(lap.var())
    blur    = cv2.GaussianBlur(gray.astype(np.uint8), (5, 5), 0)
    diff    = cv2.absdiff(gray.astype(np.uint8), blur)
    mask    = diff > 10
    texture = float(np.var(lap[mask])) if mask.any() else 0.0

    if lap_var > 5000.0 and texture < 100.0:
        return {"pass": False, "reason": "suspect sharpness profile (possible upscale or artificial sharpening)"}

    return {"pass": True, "reason": "ok"}


def _compute_reference_metrics(img: np.ndarray) -> Dict[str, float]:
    """
    Compute the full metric suite for a reference still.
    All metrics that can be derived from a single image are computed here.
    Temporal/video-only metrics (optical flow, stabilization, temporal consistency,
    shot duration) are omitted — they will be populated when video reference
    frames are added in a future corpus version.
    Each key corresponds to a field in FrameMetrics and becomes a dimension
    in the BaselineStore online statistics.
    """
    results: Dict[str, float] = {}

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        flat = gray.flatten()
        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
        hsv  = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        L, a, b = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]

        # ---- Exposure ----
        mean   = float(np.mean(flat))
        std    = float(np.std(flat))
        results["histogram_mean"]     = round(mean, 2)
        results["histogram_median"]   = round(float(np.median(flat)), 2)
        results["histogram_std"]      = round(std, 2)
        if std > 0:
            results["histogram_skew"]     = round(float(np.mean(((flat - mean) / std) ** 3)), 4)
            results["histogram_kurtosis"] = round(float(np.mean(((flat - mean) / std) ** 4)) - 3.0, 4)
        results["highlight_clip_pct"] = round(float(np.sum(flat >= 250) / len(flat) * 100.0), 3)
        results["shadow_clip_pct"]    = round(float(np.sum(flat <= 5)   / len(flat) * 100.0), 3)
        zone_v = 118.0
        results["third_moment_18gray"] = round(float(np.mean(((flat - zone_v) / 255.0) ** 3)), 6)
        signal_val = float(np.mean(flat))
        noise_val  = float(np.std(flat)) + 1e-6
        results["snr_luma"] = round(20.0 * np.log10(signal_val / noise_val) if signal_val > 0 else 0.0, 2)
        snr_a = round(20.0 * np.log10(abs(float(np.mean(a))) / (float(np.std(a)) + 1e-6) + 1e-6), 2)
        snr_b = round(20.0 * np.log10(abs(float(np.mean(b))) / (float(np.std(b)) + 1e-6) + 1e-6), 2)
        results["snr_chroma"] = round((snr_a + snr_b) / 2.0, 2)
        blurred = cv2.GaussianBlur(gray.astype(np.uint8), (5, 5), 0).astype(np.float32)
        mse = float(np.mean((gray - blurred) ** 2))
        results["psnr"] = round(10.0 * np.log10((255.0 ** 2) / mse), 2) if mse > 0 else 60.0
        from skimage.metrics import structural_similarity as ssim_func
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ssim_val = float(ssim_func(gray.astype(np.uint8), blurred.astype(np.uint8), data_range=255))
        results["ssim"] = round(ssim_val * 100.0, 2)
        spread_score = min(100.0, (std / 64.0) * 100.0)
        clip_penalty = (results["highlight_clip_pct"] * 2.0) + (results["shadow_clip_pct"] * 1.5)
        results["exposure_intent"] = round(max(0.0, spread_score - clip_penalty), 2)

        # ---- Lighting ----
        p2, p98 = np.percentile(L, 2), np.percentile(L, 98)
        dr = float(p98 - p2)
        results["dynamic_range_stops"] = round(np.log2(dr / 100.0 * 255.0 + 1.0), 2) if dr > 0 else 0.0
        bright_mask = L > np.percentile(L, 75)
        shadow_mask = L < np.percentile(L, 25)
        key_mean  = float(np.mean(L[bright_mask])) if bright_mask.any() else 0.0
        fill_mean = float(np.mean(L[shadow_mask])) + 1.0 if shadow_mask.any() else 1.0
        results["key_fill_ratio"] = round(key_mean / fill_mean, 2)
        b_mean = float(np.mean(img[:, :, 0].astype(np.float32)))
        r_mean = float(np.mean(img[:, :, 2].astype(np.float32)))
        br_ratio = b_mean / (r_mean + 1e-6)
        results["color_temp_kelvin"]    = round(2000.0 + br_ratio * 4000.0, 0)
        results["color_temp_deviation"] = round(abs(results["color_temp_kelvin"] - 5600.0) / 5600.0 * 100.0, 2)
        results["shadow_detail"] = round(float(np.mean(L[shadow_mask])) / 100.0 * 100.0, 2) if shadow_mask.any() else 0.0
        results["shadow_noise"]  = round(float(np.std(gray[shadow_mask])), 2) if shadow_mask.any() else 0.0
        grad_x = cv2.Sobel(gray.astype(np.uint8), cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray.astype(np.uint8), cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.sqrt(grad_x**2 + grad_y**2)
        results["transition_hardness"] = round(min(100.0, float(np.std(grad_mag)) / 50.0 * 100.0), 2)
        h_img, w_img = gray.shape
        quadrants = [gray[:h_img//2, :w_img//2], gray[:h_img//2, w_img//2:], gray[h_img//2:, :w_img//2], gray[h_img//2:, w_img//2:]]
        q_std = float(np.std([float(np.mean(q)) for q in quadrants]))
        results["light_motivation"] = round(min(100.0, q_std / 30.0 * 100.0), 2)

        # ---- Composition ----
        h_img, w_img = gray.shape
        thirds_x = [w_img // 3, 2 * w_img // 3]
        thirds_y = [h_img // 3, 2 * h_img // 3]
        edges = cv2.Canny(gray.astype(np.uint8), 50, 150)
        band = max(1, w_img // 20)
        td = 0.0
        for tx in thirds_x:
            td += float(np.mean(edges[:, max(0,tx-band):min(w_img,tx+band)]))
        band_h = max(1, h_img // 20)
        for ty in thirds_y:
            td += float(np.mean(edges[max(0,ty-band_h):min(h_img,ty+band_h), :]))
        results["rule_of_thirds"] = round(min(100.0, (td / 4.0) / 128.0 * 100.0), 2)
        total_lum = float(np.sum(gray)) + 1e-6
        y_coords, x_coords = np.mgrid[0:h_img, 0:w_img]
        com_x = round(float(np.sum(x_coords * gray) / total_lum) / w_img, 4)
        com_y = round(float(np.sum(y_coords * gray) / total_lum) / h_img, 4)
        results["center_of_mass_x"] = com_x
        results["center_of_mass_y"] = com_y
        results["negative_space_ratio"] = round(float(np.sum(gray < float(np.median(gray)))) / gray.size * 100.0, 2)
        bg_thresh = float(np.percentile(gray, 20))
        results["occupancy_map_score"] = round(float(np.mean(gray > bg_thresh * 1.5)) * 100.0, 2)
        mid = w_img // 2
        left  = gray[:, :mid].astype(np.float32)
        right = np.fliplr(gray[:, w_img-mid:]).astype(np.float32)
        min_w = min(left.shape[1], right.shape[1])
        results["symmetry_score"] = round(max(0.0, 100.0 - float(np.mean(np.abs(left[:, :min_w] - right[:, :min_w]))) / 128.0 * 100.0), 2)
        results["headroom"]  = round((1.0 - com_y) * 100.0, 2)
        results["lead_room"] = round(abs(com_x - 0.5) * 200.0, 2)
        thirds_pts = [(1/3,1/3),(2/3,1/3),(1/3,2/3),(2/3,2/3)]
        min_dist = min(((com_x-px)**2+(com_y-py)**2)**0.5 for px,py in thirds_pts)
        results["frame_balance"] = round(max(0.0, 100.0 - (min_dist / 0.5) * 100.0), 2)
        lap_sharp  = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
        blurred15  = cv2.GaussianBlur(gray.astype(np.uint8), (15, 15), 0)
        lap_blur   = cv2.Laplacian(blurred15, cv2.CV_32F)
        ratio = float(np.var(lap_sharp)) / (float(np.var(lap_blur)) + 1e-6)
        results["depth_separation"] = round(min(100.0, ratio / 10.0 * 100.0), 2)

        # ---- Color ----
        chroma = np.sqrt(a**2 + b**2)
        results["saturation_mean"]        = round(float(np.mean(chroma)), 2)
        results["saturation_uniformity"]  = round(max(0.0, 100.0 - float(np.std(chroma))), 2)
        results["wb_deviation"]           = round(float(np.sqrt(float(np.mean(a))**2 + float(np.mean(b))**2)), 3)
        hue_flat = hsv[:, :, 0].flatten().astype(np.float32)
        hist_h, _ = np.histogram(hue_flat, bins=36, range=(0, 180))
        hist_h = hist_h.astype(np.float32) + 1e-6
        hist_h /= hist_h.sum()
        results["palette_entropy"] = round(float(-np.sum(hist_h * np.log2(hist_h))), 4)
        results["chroma_noise"]    = round(float((np.std(a) + np.std(b)) / 2.0), 2)
        row_means = np.mean(np.abs(cv2.Sobel(np.clip(L / 100.0 * 255.0, 0, 255).astype(np.uint8), cv2.CV_32F, 0, 1, ksize=3)), axis=1)
        col_means = np.mean(np.abs(cv2.Sobel(np.clip(L / 100.0 * 255.0, 0, 255).astype(np.uint8), cv2.CV_32F, 1, 0, ksize=3)), axis=0)
        results["banding_score"] = round(min(100.0, (float(np.std(row_means)) + float(np.std(col_means))) / 2.0), 2)
        sat_val = float(np.mean(hsv[:,:,1]))
        mean_val = float(np.mean(hsv[:,:,2]))
        warm_pct = float(np.sum((hue_flat < 30) | (hue_flat > 150)) / len(hue_flat))
        cool_pct = float(np.sum((hue_flat > 60) & (hue_flat < 130)) / len(hue_flat))
        if sat_val < 30: results["palette_family_id"] = 0.0
        elif mean_val < 60: results["palette_family_id"] = 1.0
        elif mean_val > 200: results["palette_family_id"] = 2.0
        elif warm_pct > 0.5: results["palette_family_id"] = 3.0
        elif cool_pct > 0.5: results["palette_family_id"] = 4.0
        else: results["palette_family_id"] = 5.0

        # ---- Image Quality ----
        lap = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
        results["sharpness_laplacian"]    = round(float(lap.var()), 2)
        results["sharpness_edge_density"] = round(float(np.mean(edges > 0)) * 100.0, 2)
        f = np.fft.fftshift(np.fft.fft2(gray))
        mag = np.abs(f)
        cy, cx = h_img // 2, w_img // 2
        r_freq = min(h_img, w_img) // 8
        mask = np.zeros_like(mag)
        cv2.circle(mask, (cx, cy), r_freq, 1, -1)
        low = float(np.sum(mag * mask))
        high = float(np.sum(mag * (1 - mask)))
        results["mtf_proxy"] = round(high / (low + high + 1e-6) * 100.0, 2)
        results["vignetting_stops"] = _vignetting(gray, h_img, w_img)
        results["ca_width_px"]      = _ca_width(img, edges)
        edge_region = np.concatenate([gray[:h_img//6,:].flatten(), gray[-h_img//6:,:].flatten(),
                                       gray[:,:w_img//6].flatten(), gray[:,-w_img//6:].flatten()])
        results["flare_contrast_loss"] = round(float(np.sum(edge_region > 240) / len(edge_region) * 100.0), 3)
        kernel = np.array([[-1,-1,-1],[-1,8,-1],[-1,-1,-1]], dtype=np.float32)
        hp = cv2.filter2D(gray.astype(np.float32), -1, kernel)
        results["compression_ringing"]  = round(min(100.0, float(np.std(hp)) / 20.0 * 100.0), 2)
        results["texture_retention"]    = _texture_retention(gray)

        # ---- Narrative ----
        try:
            sal = cv2.saliency.StaticSaliencySpectralResidual_create()
            ok, sal_map = sal.computeSaliency(gray.astype(np.uint8))
            if ok:
                sal_f = sal_map.astype(np.float32)
                results["saliency_consistency"] = round(min(100.0, float(np.max(sal_f)) / (float(np.mean(sal_f)) + 1e-6) * 10.0), 2)
        except Exception:
            pass
        sharpness_s = min(100.0, float(lap.var()) / 500.0 * 100.0)
        exposure_s  = max(0.0, 100.0 - abs(mean - 128.0) / 128.0 * 100.0)
        contrast_s  = min(100.0, std / 80.0 * 100.0)
        results["compelling_mos"] = round(sharpness_s * 0.4 + exposure_s * 0.3 + contrast_s * 0.3, 2)

    except Exception as exc:
        print(f"[trainer metrics] partial failure: {exc}")

    return results


def _vignetting(gray: np.ndarray, h: int, w: int) -> float:
    try:
        margin = min(h, w) // 8
        center = float(np.mean(gray[h//2-margin:h//2+margin, w//2-margin:w//2+margin]))
        corners = [gray[:margin,:margin], gray[:margin,-margin:], gray[-margin:,:margin], gray[-margin:,-margin:]]
        corner_mean = float(np.mean([np.mean(c) for c in corners]))
        ratio = corner_mean / (center + 1e-6)
        return max(0.0, round(float(-np.log2(ratio + 1e-6)), 2))
    except Exception:
        return 0.0


def _ca_width(img: np.ndarray, edges: np.ndarray) -> float:
    try:
        edge_mask = edges > 0
        if not edge_mask.any():
            return 0.0
        r_e = img[:,:,2][edge_mask].astype(np.float32)
        g_e = img[:,:,1][edge_mask].astype(np.float32)
        b_e = img[:,:,0][edge_mask].astype(np.float32)
        return round((float(np.mean(np.abs(r_e-g_e))) + float(np.mean(np.abs(b_e-g_e)))) / 2.0, 2)
    except Exception:
        return 0.0


def _texture_retention(gray: np.ndarray) -> float:
    try:
        blur = cv2.GaussianBlur(gray.astype(np.uint8), (5,5), 0)
        diff = cv2.absdiff(gray.astype(np.uint8), blur)
        mask = diff > 10
        if not mask.any():
            return 50.0
        lap = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
        return round(min(100.0, float(np.var(lap[mask])) / 500.0 * 100.0), 2)
    except Exception:
        return 0.0


def _store_embedding(
    img_path:  Path,
    embedding: List[float],
    version:   Optional[str],
    data_dir:  Path,
) -> None:
    """
    Store the CLIP embedding for a reference still in the baseline embeddings index.
    All embeddings are stored in data/baseline/embeddings/<stem>.json.
    This file is what compute_baseline_similarity() reads at scoring time.
    """
    embeddings_dir = data_dir / "baseline" / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)

    # use a sanitized version of the filename as the key
    key  = img_path.stem[:64]
    record = {
        "source":    img_path.name,
        "model":     version,
        "embedding": embedding,
    }
    out_path = embeddings_dir / f"{key}.json"
    out_path.write_text(json.dumps(record), encoding="utf-8")


def _build_embeddings_index(data_dir: Path) -> List[List[float]]:
    """
    Load all stored reference embeddings into a list.
    Called by compute_baseline_similarity() at scoring time.
    """
    embeddings_dir = data_dir / "baseline" / "embeddings"
    if not embeddings_dir.exists():
        return []

    embeddings = []
    for p in embeddings_dir.glob("*.json"):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
            emb    = record.get("embedding")
            if emb and len(emb) > 0:
                embeddings.append(emb)
        except Exception:
            continue

    return embeddings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_images(source_dir: Path) -> List[Path]:
    """
    Scan a directory for supported image files.
    Returns a sorted list of Paths.
    """
    images = [
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images)
# aesthetic/agents/two_stage.py
#
# Two-stage ranking pipeline.
#
# Stage 1 — Broad cheap sweep (all candidates):
#   - Frame metrics (parallel, CPU)
#   - CLIP/SigLIP embeddings
#   - YOLO detection
#   - MiDaS DISABLED in stage 1
#   - Initial aggregation → first-pass score
#   - Produce ranked shortlist: top SHORTLIST_PCT of scenes
#
# Stage 2 — Shortlist rerank (top scenes only):
#   - MiDaS DPT_Hybrid depth (one frame per shortlisted scene)
#   - Gamut data collection (BGR→XYZ→xy per shortlisted scene)
#   - Denser classification (full MAX_CLS_PER_SCENE on shortlisted scenes)
#   - Re-aggregation with depth and gamut data
#   - Final scoring → selection
#
# Design notes:
#   - Stage 1 results are cached: re-running stage 2 with different
#     shortlist sizes does not re-run metrics or CLIP.
#   - Non-shortlisted scenes retain their stage-1 scores so they can
#     still appear in the final output if shortlist + diversity requires it.
#   - Progress reporting covers both stages in the 0-100 range.
#   - SHORTLIST_PCT is configurable in config.yaml under selection.shortlist_pct

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import defaultdict

from ..models.scores import FrameMetrics, ShotScore
from ..models.job import Scene, Shot

# fraction of scenes to include in Stage 2 shortlist
DEFAULT_SHORTLIST_PCT = 0.25
MIN_SHORTLIST_SCENES  = 3   # always process at least this many in stage 2


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------

def stage1_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a config dict with Stage 1 overrides:
    - MiDaS disabled (no depth maps yet — done in stage 2)
    - CLIP and YOLO still enabled (needed for first-pass scores)
    """
    s1 = dict(cfg)
    features = dict(cfg.get("features", {}))
    features["midas_enabled"] = False
    s1["features"] = features
    return s1


def compute_shortlist(
    shots:    List[Shot],
    scores:   List[ShotScore],
    shortlist_pct: float = DEFAULT_SHORTLIST_PCT,
) -> List[int]:
    """
    Return scene_ids of the top shortlist_pct shots by stage-1 score.

    Always includes at least MIN_SHORTLIST_SCENES scenes so stage 2
    has meaningful work to do even on short videos.
    """
    if not shots or not scores:
        return []

    n = max(MIN_SHORTLIST_SCENES, int(len(shots) * shortlist_pct))
    n = min(n, len(shots))

    ranked = sorted(
        zip(shots, scores),
        key=lambda x: x[1].total_score or 0.0,
        reverse=True,
    )
    return [shot.scene_id for shot, _ in ranked[:n]]


# ---------------------------------------------------------------------------
# Stage 2 helpers
# ---------------------------------------------------------------------------

def stage2_config(
    cfg:           Dict[str, Any],
    shortlist_ids: List[int],
    scene_id:      int,
) -> Dict[str, Any]:
    """
    Return a config dict for a specific frame in stage 2.
    Enables MiDaS only for the first frame of each shortlisted scene.
    """
    if scene_id not in shortlist_ids:
        # not on shortlist — run cheaply, no depth
        s2 = dict(cfg)
        features = dict(cfg.get("features", {}))
        features["midas_enabled"] = False
        s2["features"] = features
        return s2
    # on shortlist — full processing (MiDaS controlled per-frame externally)
    return cfg


def shortlist_progress_label(
    shortlist_ids: List[int],
    total_scenes:  int,
) -> str:
    n = len(shortlist_ids)
    pct = int(n / max(1, total_scenes) * 100)
    return f"Stage 2: deep analysis on {n}/{total_scenes} scenes ({pct}% shortlisted)"


# ---------------------------------------------------------------------------
# Shortlist summary for UI / logging
# ---------------------------------------------------------------------------

def build_stage_summary(
    all_scores:    List[ShotScore],
    shortlist_ids: List[int],
) -> Dict[str, Any]:
    """Build a summary dict for logging and UI display."""
    total   = len(all_scores)
    in_sl   = sum(1 for s in all_scores if s.scene_id in shortlist_ids)
    avg_s1  = (sum(s.total_score or 0 for s in all_scores) / total) if total else 0
    sl_scores = [s.total_score or 0 for s in all_scores if s.scene_id in shortlist_ids]
    avg_sl  = (sum(sl_scores) / len(sl_scores)) if sl_scores else 0

    return {
        "total_scenes":      total,
        "shortlisted":       in_sl,
        "shortlist_pct":     round(in_sl / max(1, total) * 100, 1),
        "avg_score_all":     round(avg_s1, 1),
        "avg_score_shortlist": round(avg_sl, 1),
    }
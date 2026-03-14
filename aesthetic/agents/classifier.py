# aesthetic/agents/classifier.py
#
# Shot intent classification.
# Determines shot scale, movement type, scene type, and shot intent
# for each candidate frame using a hybrid approach:
#
#   Shot scale:    YOLO person detection + face size relative to frame
#   Movement type: Optical flow signals (already computed in metrics)
#   Scene type:    CLIP zero-shot classification
#   Shot intent:   CLIP zero-shot classification
#
# Results are stored in the Shot model and used by:
#   - Pillar interaction logic (Phase 2 scoring) — different weights per intent
#   - Narrative diversity constraints (Phase 3 selection) — ensure variety
#   - Contact sheet annotations — show scale/movement icons per tile
#   - Manifest — explain why each shot was classified as it was
#
# All classification is deterministic given the same inputs.
# CLIP zero-shot is optional — falls back to rule-based if CLIP unavailable.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..models.job import MovementType, ShotScale, SceneType
from ..models.scores import FrameMetrics


# ---------------------------------------------------------------------------
# CLIP zero-shot label sets
# ---------------------------------------------------------------------------

# Scene type prompts — CLIP scores the frame against each description
SCENE_TYPE_PROMPTS = {
    SceneType.INTERIOR_DAY:   "a bright interior scene with natural or artificial daylight",
    SceneType.INTERIOR_NIGHT: "a dark interior scene at night with artificial lighting",
    SceneType.EXTERIOR_DAY:   "an outdoor exterior scene in daylight",
    SceneType.EXTERIOR_NIGHT: "an outdoor exterior scene at night",
}

# Shot intent prompts
INTENT_PROMPTS = {
    "intimate":     "an intimate close-up shot showing emotion or detail",
    "establishing": "a wide establishing shot showing environment or location",
    "action":       "a dynamic action shot with movement or tension",
    "dialogue":     "a medium coverage shot for dialogue or conversation",
    "transitional": "a transitional or connective shot between scenes",
}

# Shot scale prompts (used as fallback when YOLO has no person detection)
SCALE_PROMPTS = {
    ShotScale.EXTREME_CLOSE: "an extreme close-up shot of a face or object detail",
    ShotScale.CLOSE:         "a close-up shot showing a face or hands",
    ShotScale.MEDIUM_CLOSE:  "a medium close-up shot showing head and shoulders",
    ShotScale.MEDIUM:        "a medium shot showing a person from the waist up",
    ShotScale.MEDIUM_WIDE:   "a medium wide shot showing a full person",
    ShotScale.WIDE:          "a wide shot showing multiple people or an environment",
    ShotScale.EXTREME_WIDE:  "an extreme wide shot showing a landscape or large space",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify_shot(
    frame_metrics:  FrameMetrics,
    frame_path:     str,
    config:         Dict[str, Any],
    clip_model=None,
    clip_preprocess=None,
    clip_device:    str = "cpu",
) -> Dict[str, Any]:
    """
    Classify a shot's scale, movement type, scene type, and intent.

    Args:
        frame_metrics:   FrameMetrics for this frame (metrics + inference already run).
        frame_path:      Path to the frame image.
        config:          Full config dict.
        clip_model:      Loaded CLIP model (optional — pass in to avoid reloading).
        clip_preprocess: CLIP preprocess function.
        clip_device:     Device string.

    Returns:
        Dict with keys: shot_scale, movement_type, scene_type, shot_intent,
        and confidence scores for each.
    """
    result = {
        "shot_scale":    ShotScale.UNKNOWN.value,
        "movement_type": MovementType.UNKNOWN.value,
        "scene_type":    SceneType.UNKNOWN.value,
        "shot_intent":   "unknown",
        "scale_confidence":    0.0,
        "scene_confidence":    0.0,
        "intent_confidence":   0.0,
        "classification_method": "rules",
    }

    # --- shot scale ---
    scale, scale_conf, scale_method = _classify_scale(
        frame_metrics, frame_path, clip_model, clip_preprocess, clip_device
    )
    result["shot_scale"]         = scale.value
    result["scale_confidence"]   = scale_conf
    result["classification_method"] = scale_method

    # --- movement type ---
    movement = _classify_movement(frame_metrics)
    result["movement_type"] = movement.value

    # --- scene type + intent (CLIP zero-shot if available, else rules) ---
    if clip_model is not None:
        scene, scene_conf = _classify_scene_clip(
            frame_path, clip_model, clip_preprocess, clip_device
        )
        intent, intent_conf = _classify_intent_clip(
            frame_path, clip_model, clip_preprocess, clip_device
        )
        result["scene_type"]        = scene.value
        result["scene_confidence"]  = scene_conf
        result["shot_intent"]       = intent
        result["intent_confidence"] = intent_conf
        result["classification_method"] = "clip+rules"
    else:
        scene  = _classify_scene_rules(frame_metrics)
        result["scene_type"] = scene.value
        result["shot_intent"] = _classify_intent_rules(frame_metrics, scale)

    return result


def classify_scene_from_shots(
    shot_classifications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Aggregate per-frame classifications into a single shot-level classification
    by majority vote across all candidate frames.

    Args:
        shot_classifications: List of per-frame classification dicts.

    Returns:
        Single classification dict representing the shot as a whole.
    """
    if not shot_classifications:
        return {
            "shot_scale":    ShotScale.UNKNOWN.value,
            "movement_type": MovementType.UNKNOWN.value,
            "scene_type":    SceneType.UNKNOWN.value,
            "shot_intent":   "unknown",
        }

    def majority(values: List[str]) -> str:
        from collections import Counter
        if not values:
            return "unknown"
        return Counter(values).most_common(1)[0][0]

    return {
        "shot_scale":    majority([c["shot_scale"]    for c in shot_classifications]),
        "movement_type": majority([c["movement_type"] for c in shot_classifications]),
        "scene_type":    majority([c["scene_type"]    for c in shot_classifications]),
        "shot_intent":   majority([c["shot_intent"]   for c in shot_classifications]),
        "scale_confidence":  float(np.mean([c.get("scale_confidence",  0) for c in shot_classifications])),
        "scene_confidence":  float(np.mean([c.get("scene_confidence",  0) for c in shot_classifications])),
        "intent_confidence": float(np.mean([c.get("intent_confidence", 0) for c in shot_classifications])),
    }


# ---------------------------------------------------------------------------
# Shot scale classification
# ---------------------------------------------------------------------------

def _classify_scale(
    fm:          FrameMetrics,
    frame_path:  str,
    clip_model,
    clip_preprocess,
    clip_device: str,
) -> Tuple[ShotScale, float, str]:
    """
    Classify shot scale using YOLO person detection as primary signal.
    Falls back to CLIP zero-shot if no person detected.
    Falls back to rule-based if CLIP unavailable.
    """
    # primary: YOLO person detection
    detections = fm.inference.detections or []
    person_detections = [d for d in detections if d.get("label") == "person"]

    if person_detections:
        scale, conf = _scale_from_person_size(person_detections, fm)
        return scale, conf, "yolo"

    # face detection fallback (Haar cascade result in composition metrics)
    face_count = fm.composition.face_count or 0
    if face_count > 0 and fm.composition.face_placement is not None:
        scale = _scale_from_face_metrics(fm)
        return scale, 0.6, "face_metrics"

    # CLIP zero-shot fallback
    if clip_model is not None:
        scale, conf = _scale_from_clip(frame_path, clip_model, clip_preprocess, clip_device)
        return scale, conf, "clip"

    # rule-based fallback — use depth and occupancy as proxies
    scale = _scale_from_rules(fm)
    return scale, 0.3, "rules"


def _scale_from_person_size(
    detections: List[Dict[str, Any]],
    fm:         FrameMetrics,
) -> Tuple[ShotScale, float]:
    """
    Estimate shot scale from the largest detected person's bounding box
    relative to the frame area.
    """
    # find the largest person detection by area
    largest = max(
        detections,
        key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1])
    )
    x1, y1, x2, y2 = largest["bbox"]
    person_h = y2 - y1
    person_w = x2 - x1
    person_area = person_h * person_w

    # we need frame dimensions — approximate from composition metrics
    # COM values are normalised 0-1, so we can use area relative to frame
    # typical frame is 1920x1080 = 2,073,600 pixels
    # use a rough estimate based on person area alone
    person_h_pct = person_h / 1080.0   # normalised height estimate

    conf = float(largest.get("confidence", 0.7))

    if person_h_pct > 0.85:
        return ShotScale.EXTREME_CLOSE, conf
    elif person_h_pct > 0.65:
        return ShotScale.CLOSE, conf
    elif person_h_pct > 0.45:
        return ShotScale.MEDIUM_CLOSE, conf
    elif person_h_pct > 0.30:
        return ShotScale.MEDIUM, conf
    elif person_h_pct > 0.18:
        return ShotScale.MEDIUM_WIDE, conf
    elif person_h_pct > 0.08:
        return ShotScale.WIDE, conf
    else:
        return ShotScale.EXTREME_WIDE, conf


def _scale_from_face_metrics(fm: FrameMetrics) -> ShotScale:
    """
    Estimate scale from face placement score and composition metrics.
    Higher face placement score = face is more prominent = closer shot.
    """
    fp = fm.composition.face_placement or 0.0
    if fp > 85:
        return ShotScale.EXTREME_CLOSE
    elif fp > 70:
        return ShotScale.CLOSE
    elif fp > 50:
        return ShotScale.MEDIUM_CLOSE
    elif fp > 30:
        return ShotScale.MEDIUM
    else:
        return ShotScale.MEDIUM_WIDE


def _scale_from_clip(
    frame_path:  str,
    model,
    preprocess,
    device:      str,
) -> Tuple[ShotScale, float]:
    """CLIP zero-shot shot scale classification."""
    try:
        import torch
        from PIL import Image

        labels  = list(SCALE_PROMPTS.keys())
        prompts = list(SCALE_PROMPTS.values())

        import open_clip
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        tokens    = tokenizer(prompts).to(device)

        img    = Image.open(frame_path).convert("RGB")
        tensor = preprocess(img).unsqueeze(0).to(device)

        with torch.no_grad():
            img_feat  = model.encode_image(tensor)
            txt_feat  = model.encode_text(tokens)
            img_feat  = img_feat / img_feat.norm(dim=-1, keepdim=True)
            txt_feat  = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
            sims      = (img_feat @ txt_feat.T).squeeze(0)
            probs     = sims.softmax(dim=-1).cpu().numpy()

        best_idx  = int(np.argmax(probs))
        return labels[best_idx], float(probs[best_idx])

    except Exception:
        return ShotScale.UNKNOWN, 0.0


def _scale_from_rules(fm: FrameMetrics) -> ShotScale:
    """Rule-based scale fallback using depth separation and occupancy."""
    depth = fm.composition.depth_separation or 0.0
    occ   = fm.composition.occupancy_map_score or 0.0

    if depth > 60 and occ > 60:
        return ShotScale.CLOSE
    elif depth > 40 and occ > 40:
        return ShotScale.MEDIUM
    elif occ < 20:
        return ShotScale.EXTREME_WIDE
    else:
        return ShotScale.WIDE


# ---------------------------------------------------------------------------
# Movement type classification
# ---------------------------------------------------------------------------

def _classify_movement(fm: FrameMetrics) -> MovementType:
    """
    Classify movement type from optical flow metrics already computed.
    These are already in FrameMetrics.movement so no new computation needed.
    """
    mv = fm.movement

    flow_mean = mv.optical_flow_mean
    if flow_mean is None:
        # no previous frame — can still check motion blur as static indicator
        blur = mv.motion_blur_amount or 0.0
        if blur < 30:
            return MovementType.STATIC
        return MovementType.UNKNOWN

    if flow_mean < 0.5:
        return MovementType.STATIC

    # use movement_type if already classified by metrics engine
    if mv.movement_type and mv.movement_type != "unknown":
        try:
            return MovementType(mv.movement_type)
        except ValueError:
            pass

    # fallback classification from flow stats
    flow_std = mv.optical_flow_std or 0.0
    stab     = mv.stabilization or 100.0

    if flow_std > 2.0 and stab < 60:
        return MovementType.HANDHELD
    if flow_mean > 3.0:
        return MovementType.DOLLY
    if flow_mean > 1.0:
        return MovementType.PAN

    return MovementType.UNKNOWN


# ---------------------------------------------------------------------------
# Scene type classification
# ---------------------------------------------------------------------------

def _classify_scene_clip(
    frame_path:  str,
    model,
    preprocess,
    device:      str,
) -> Tuple[SceneType, float]:
    """CLIP zero-shot scene type classification."""
    try:
        import torch
        from PIL import Image
        import open_clip

        labels  = list(SCENE_TYPE_PROMPTS.keys())
        prompts = list(SCENE_TYPE_PROMPTS.values())

        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        tokens    = tokenizer(prompts).to(device)

        img    = Image.open(frame_path).convert("RGB")
        tensor = preprocess(img).unsqueeze(0).to(device)

        with torch.no_grad():
            img_feat = model.encode_image(tensor)
            txt_feat = model.encode_text(tokens)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
            sims     = (img_feat @ txt_feat.T).squeeze(0)
            probs    = sims.softmax(dim=-1).cpu().numpy()

        best_idx = int(np.argmax(probs))
        return labels[best_idx], float(probs[best_idx])

    except Exception:
        return SceneType.UNKNOWN, 0.0


def _classify_scene_rules(fm: FrameMetrics) -> SceneType:
    """
    Rule-based scene type classification from existing metrics.
    Uses color temperature and luminance as proxies.
    """
    temp  = fm.lighting.color_temp_kelvin or 5600.0
    mean  = fm.exposure.histogram_mean    or 128.0
    dr    = fm.lighting.dynamic_range_stops or 6.0

    # day vs night: night scenes tend to have lower mean luminance
    is_night = mean < 60.0

    # interior vs exterior:
    # - cool color temp (>6000K) suggests daylight / exterior
    # - warm color temp (<3500K) suggests tungsten / interior
    # - high dynamic range suggests exterior sunlight
    is_exterior = temp > 5500.0 or dr > 9.0

    if is_exterior and not is_night:
        return SceneType.EXTERIOR_DAY
    elif is_exterior and is_night:
        return SceneType.EXTERIOR_NIGHT
    elif not is_exterior and not is_night:
        return SceneType.INTERIOR_DAY
    else:
        return SceneType.INTERIOR_NIGHT


# ---------------------------------------------------------------------------
# Shot intent classification
# ---------------------------------------------------------------------------

def _classify_intent_clip(
    frame_path:  str,
    model,
    preprocess,
    device:      str,
) -> Tuple[str, float]:
    """CLIP zero-shot shot intent classification."""
    try:
        import torch
        from PIL import Image
        import open_clip

        labels  = list(INTENT_PROMPTS.keys())
        prompts = list(INTENT_PROMPTS.values())

        tokenizer = open_clip.get_tokenizer("ViT-B-32")
        tokens    = tokenizer(prompts).to(device)

        img    = Image.open(frame_path).convert("RGB")
        tensor = preprocess(img).unsqueeze(0).to(device)

        with torch.no_grad():
            img_feat = model.encode_image(tensor)
            txt_feat = model.encode_text(tokens)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
            sims     = (img_feat @ txt_feat.T).squeeze(0)
            probs    = sims.softmax(dim=-1).cpu().numpy()

        best_idx = int(np.argmax(probs))
        return labels[best_idx], float(probs[best_idx])

    except Exception:
        return "unknown", 0.0


def _classify_intent_rules(fm: FrameMetrics, scale: ShotScale) -> str:
    """
    Rule-based intent fallback using shot scale and movement type.
    Less accurate than CLIP but always available.
    """
    mv = fm.movement.optical_flow_mean or 0.0

    if scale in (ShotScale.EXTREME_CLOSE, ShotScale.CLOSE):
        return "intimate"
    elif scale in (ShotScale.EXTREME_WIDE, ShotScale.WIDE):
        return "establishing"
    elif mv > 2.0:
        return "action"
    elif scale in (ShotScale.MEDIUM, ShotScale.MEDIUM_CLOSE):
        return "dialogue"
    else:
        return "transitional"
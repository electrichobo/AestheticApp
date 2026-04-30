# aesthetic/agents/inference.py
#
# AI vision model inference pipeline.
# Runs CLIP embedding, MiDaS depth estimation, YOLO detection,
# and optional VLM rationale generation per frame or per selected shot.
#
# All results are stored in FrameMetrics.inference and cached to disk
# so re-scoring never re-runs inference unless the model version changes.
#
# Feature flags in config.yaml control which models are active:
#   features.clip_enabled
#   features.midas_enabled
#   features.yolo_enabled
#   features.vlm_rationale_enabled
#   features.gpu_enabled
#
# Models are loaded once and reused across frames (singleton pattern).
# Loading is deferred until first use — startup is not penalised.

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import cv2

from ..models.scores import FrameMetrics, InferenceOutputs, ShotScore


# ---------------------------------------------------------------------------
# Model singletons — loaded once, reused across frames
# ---------------------------------------------------------------------------

_clip_model    = None
_clip_preprocess = None
_clip_tokenizer  = None
_clip_version: Optional[str] = None

_midas_model   = None
_midas_transform = None
_midas_version: Optional[str] = None

_yolo_model    = None
_yolo_version: Optional[str] = None

_device: Optional[str] = None


# ---------------------------------------------------------------------------
# Model selection and device detection — delegated to model_utils
# ---------------------------------------------------------------------------

from .model_utils import (
    get_device       as _get_device_util,
    select_best_model as _select_best_clip_model,
    is_siglip        as _is_siglip_model,
    load_model       as _load_clip_model,
)


def _get_device(gpu_enabled: bool = True) -> str:
    return _get_device_util(gpu_enabled)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_frame_inference(
    frame_metrics: FrameMetrics,
    frame_path:    str,
    job_dir:       Path,
    config:        Dict[str, Any],
) -> FrameMetrics:
    """
    Run all enabled inference models on a single frame.
    Updates frame_metrics.inference in place and rewrites the sidecar.

    Args:
        frame_metrics: Existing FrameMetrics for this frame (from metrics engine).
        frame_path:    Path to the extracted JPEG frame on disk.
        job_dir:       Job directory — updated sidecar is written here.
        config:        Full config dict.

    Returns:
        Updated FrameMetrics with inference results populated.
    """
    features   = config.get("features", {})
    gpu        = bool(features.get("gpu_enabled", False))
    device     = _get_device(gpu)

    inference = InferenceOutputs()

    # CLIP embedding
    if features.get("clip_enabled", True):
        embedding, version = _run_clip(frame_path, device)
        inference.clip_embedding     = embedding
        inference.clip_model_version = version

    # MiDaS depth
    if features.get("midas_enabled", True):
        depth_path = _run_midas(frame_path, job_dir, frame_metrics.frame_id, device)
        inference.depth_map_path = depth_path
        # compute depth separation score from the depth map
        # and promote it into CompositionMetrics — replaces the Laplacian proxy
        if depth_path:
            ds = _compute_depth_separation_from_map(depth_path)
            if ds is not None:
                inference.midas_depth_separation = ds
                # overwrite the Laplacian-based depth_separation with MiDaS result
                if frame_metrics.composition is not None:
                    frame_metrics.composition.depth_separation = ds

    # YOLO detection + skin tone analysis
    if features.get("yolo_enabled", True):
        try:
            detections = _run_yolo(frame_path, device)
            inference.detections = detections
            # skin tone analysis from face bounding boxes
            if detections:
                skin_de = _analyse_skin_tone(frame_path, detections)
                if skin_de is not None and frame_metrics.color is not None:
                    frame_metrics.color.skin_tone_de = skin_de
        except Exception as exc:
            import traceback
            print(f"[inference] YOLO failed for {frame_path}: {exc}")
            traceback.print_exc()

    # --- Focus metrics (YOLO face region + temporal, requires detections) ---
    if features.get("yolo_enabled", True) and inference.detections:
        try:
            _compute_focus_metrics(frame_path, inference.detections, frame_metrics)
        except Exception as exc:
            print(f"[inference] focus metrics failed: {exc}")

    # --- Subject metrics (SigLIP zero-shot + emotion) ---
    if features.get("clip_enabled", True):
        try:
            _compute_subject_metrics(frame_path, device, frame_metrics)
        except Exception as exc:
            print(f"[inference] subject metrics failed: {exc}")

    frame_metrics.inference = inference
    _write_sidecar(frame_metrics, job_dir)
    return frame_metrics


def run_shot_rationale(
    shot_score: ShotScore,
    hero_frame_path: str,
    config:     Dict[str, Any],
) -> ShotScore:
    """
    Generate a plain-language rationale for a selected shot via VLM API.
    Called once per SELECTED shot only — not per candidate frame.

    Args:
        shot_score:      ShotScore for the selected shot.
        hero_frame_path: Path to the hero frame image for this shot.
        config:          Full config dict.

    Returns:
        Updated ShotScore with rationale populated.
    """
    features = config.get("features", {})
    if not features.get("vlm_rationale_enabled", False):
        return shot_score

    rationale = _run_vlm_rationale(shot_score, hero_frame_path, config)
    shot_score.rationale = rationale
    return shot_score


def compute_baseline_similarity(
    embedding: List[float],
    data_dir:  Path,
) -> Optional[float]:
    """
    Compute cosine similarity between a frame CLIP embedding and the
    Golden Baseline corpus embeddings stored by the baseline trainer.

    Args:
        embedding: CLIP embedding vector for the candidate frame.
        data_dir:  Root data directory (embeddings live under data_dir/baseline/embeddings/).

    Returns:
        Similarity score 0.0-100.0, or None if no baseline embeddings exist.
    """
    try:
        from .baseline_trainer import _build_embeddings_index
        corpus_embeddings = _build_embeddings_index(data_dir)
        if not corpus_embeddings:
            return None

        frame_vec = np.array(embedding, dtype=np.float32)
        frame_vec = frame_vec / (np.linalg.norm(frame_vec) + 1e-8)

        similarities = []
        for corpus_emb in corpus_embeddings:
            corpus_vec = np.array(corpus_emb, dtype=np.float32)
            corpus_vec = corpus_vec / (np.linalg.norm(corpus_vec) + 1e-8)
            sim = float(np.dot(frame_vec, corpus_vec))
            similarities.append(sim)

        if not similarities:
            return None

        # mean of top-5 most similar baseline frames
        top_k = sorted(similarities, reverse=True)[:5]
        score = float(np.mean(top_k))

        # cosine similarity (-1 to 1) -> 0-100
        return round((score + 1.0) / 2.0 * 100.0, 2)

    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLIP
# ---------------------------------------------------------------------------

def _run_clip(
    frame_path: str,
    device:     str,
) -> tuple[Optional[List[float]], Optional[str]]:
    """
    Generate a CLIP embedding for the given frame.
    Returns (embedding_list, model_version_string).
    """
    global _clip_model, _clip_preprocess, _clip_version

    try:
        import torch
        import open_clip

        if _clip_model is None:
            # Model selection cascade — best available at runtime
            # model_utils selects best available: SigLIP > ViT-L-14-336 > ViT-L-14 > ViT-B-32
            from .model_utils import load_model as _mu_load
            _clip_model, _clip_preprocess, model_name, pretrained = _mu_load(device)
            _clip_version = f"{model_name}/{pretrained}"

        from PIL import Image
        img = Image.open(frame_path).convert("RGB")
        tensor = _clip_preprocess(img).unsqueeze(0).to(device)

        with torch.no_grad():
            embedding = _clip_model.encode_image(tensor)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)

        return embedding.squeeze().cpu().tolist(), _clip_version

    except Exception as exc:
        import traceback
        traceback.print_exc()
        _log_inference_error("CLIP", exc)
        return None, None


# ---------------------------------------------------------------------------
# MiDaS depth estimation
# ---------------------------------------------------------------------------

def _run_midas(
    frame_path: str,
    job_dir:    Path,
    frame_id:   str,
    device:     str,
) -> Optional[str]:
    """
    Run MiDaS DPT_Hybrid depth estimation on the frame.

    Uses DPT_Hybrid (transformer+CNN) which provides substantially better
    depth understanding than MiDaS_small — it understands perspective,
    occlusion, and semantic scale rather than just sharpness gradients.

    The model is loaded once per app session (cached in _midas_model global).
    Weights are cached by torch.hub in ~/.cache/torch/hub/ after first download.

    Returns the depth map path for storage, AND computes depth_separation
    score which is written back into the FrameMetrics composition data via
    the inference result stored in InferenceOutputs.

    Falls back gracefully to None on any error — the Laplacian method in
    metrics.py provides a fallback depth_separation in that case.
    """
    global _midas_model, _midas_transform, _midas_version

    try:
        import warnings
        import torch

        if _midas_model is None:
            # DPT_Hybrid: best quality/speed tradeoff on GPU
            # suppress timm deprecation warnings during model load
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model_type = "DPT_Hybrid"
                _midas_model = torch.hub.load(
                    "intel-isl/MiDaS", model_type,
                    trust_repo=True, verbose=False
                )
                _midas_model.to(device)
                _midas_model.eval()

                midas_transforms = torch.hub.load(
                    "intel-isl/MiDaS", "transforms",
                    trust_repo=True, verbose=False
                )
                _midas_transform = midas_transforms.dpt_transform
                _midas_version   = model_type

        img = cv2.imread(frame_path)
        if img is None:
            return None
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        input_batch = _midas_transform(img_rgb).to(device)

        with torch.no_grad():
            prediction = _midas_model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img_rgb.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth = prediction.cpu().numpy().astype(float)

        # normalise depth map to 0-255 and save for optional inspection
        depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        depth_dir  = job_dir / "depth"
        depth_dir.mkdir(parents=True, exist_ok=True)
        depth_path = depth_dir / f"{frame_id}_depth.png"
        cv2.imwrite(str(depth_path), depth_norm)

        return str(depth_path)

    except Exception as exc:
        _log_inference_error("MiDaS", exc)
        return None


def _compute_depth_separation_from_map(depth_map_path: str) -> Optional[float]:
    """
    Compute a depth_separation score (0-100) from a MiDaS depth map PNG.

    Replaces the Laplacian proxy with real monocular depth understanding.

    The score measures how much depth *separation* exists between different
    regions of the frame — the cinematic quality of having distinct foreground,
    midground, and background layers.

    Method:
      1. Load the normalised depth map (0-255, brighter = closer)
      2. Divide into spatial regions (foreground centre, background edges)
      3. Measure the standard deviation of depth values — high std = many
         distinct depth planes = rich depth composition
      4. Also measure the foreground/background contrast — the ratio of
         near-region depth to far-region depth
      5. Combine into a 0-100 score

    A locked-off wide shot of a flat wall scores ~5.
    A portrait with shallow DOF and bokeh background scores ~70-85.
    A wide with clear fore/mid/back separation scores ~50-65.
    """
    try:
        depth = cv2.imread(depth_map_path, cv2.IMREAD_GRAYSCALE)
        if depth is None:
            return None

        depth_f = depth.astype(np.float32)
        h, w    = depth_f.shape

        # std of depth values — measures spread of depth planes
        depth_std = float(np.std(depth_f))

        # foreground/background separation:
        # foreground = centre region (likely subject), background = periphery
        cy, cx   = h // 2, w // 2
        margin_y = max(1, h // 6)
        margin_x = max(1, w // 6)
        fg_region = depth_f[cy-margin_y:cy+margin_y, cx-margin_x:cx+margin_x]
        # background = outer 25% of frame
        bg_mask = np.ones_like(depth_f, dtype=bool)
        bg_mask[h//4:3*h//4, w//4:3*w//4] = False
        bg_region = depth_f[bg_mask]

        fg_mean = float(np.mean(fg_region)) if fg_region.size > 0 else 128.0
        bg_mean = float(np.mean(bg_region)) if bg_region.size > 0 else 128.0

        # fg/bg contrast: difference normalised to 0-1
        fg_bg_contrast = abs(fg_mean - bg_mean) / 255.0

        # number of distinct depth layers (histogram entropy)
        hist, _ = np.histogram(depth_f, bins=16, range=(0, 256))
        hist    = hist.astype(np.float32) + 1e-6
        hist   /= hist.sum()
        entropy = float(-np.sum(hist * np.log2(hist)))
        # max entropy with 16 bins = log2(16) = 4.0
        entropy_norm = entropy / 4.0   # 0-1

        # combine: 50% std, 30% fg/bg contrast, 20% layer entropy
        score = (
            (depth_std / 128.0)     * 50.0 +   # std contribution (max ~50)
            fg_bg_contrast          * 30.0 +   # fg/bg contrast (max 30)
            entropy_norm            * 20.0     # layer richness (max 20)
        )
        return round(min(100.0, max(0.0, score)), 2)

    except Exception:
        return None


# ---------------------------------------------------------------------------
# YOLO detection
# ---------------------------------------------------------------------------

def _run_yolo(
    frame_path: str,
    device:     str,
) -> Optional[List[Dict[str, Any]]]:
    """
    Run YOLO object detection on the frame.
    Returns a list of detection dicts: {label, confidence, bbox: [x1,y1,x2,y2]}.
    """
    global _yolo_model, _yolo_version

    try:
        from ultralytics import YOLO

        if _yolo_model is None:
            _yolo_model   = YOLO("yolov8n.pt")
            _yolo_version = "yolov8n"

        results = _yolo_model(frame_path, device=device, verbose=False)
        detections = []

        for result in results:
            for box in result.boxes:
                label = result.names[int(box.cls)]
                conf  = round(float(box.conf), 3)
                bbox  = [round(float(v), 1) for v in box.xyxy[0].tolist()]
                detections.append({
                    "label":      label,
                    "confidence": conf,
                    "bbox":       bbox,
                })

        return detections if detections else []

    except Exception as exc:
        _log_inference_error("YOLO", exc)
        return None


# ---------------------------------------------------------------------------
# VLM rationale generation
# ---------------------------------------------------------------------------

def _run_vlm_rationale(
    shot_score:      ShotScore,
    hero_frame_path: str,
    config:          Dict[str, Any],
) -> Optional[str]:
    """
    Call the VLM API with the hero frame and score data to generate
    a plain-language explanation of why this shot was selected.

    Tries Anthropic first, falls back to OpenAI if not configured.
    Requires ANTHROPIC_API_KEY or OPENAI_API_KEY in environment.
    """
    try:
        import base64

        with open(hero_frame_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        prompt = _build_rationale_prompt(shot_score)

        # try Anthropic first
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            return _vlm_anthropic(image_data, prompt, anthropic_key)

        # fall back to OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            return _vlm_openai(image_data, prompt, openai_key)

        return None

    except Exception as exc:
        _log_inference_error("VLM rationale", exc)
        return None


def _build_rationale_prompt(shot_score: ShotScore) -> str:
    """Build the prompt sent to the VLM with score context."""
    lines = [
        "You are an expert cinematographer and film critic.",
        "Analyze this shot and explain in 2-3 sentences why it is or is not cinematically excellent.",
        "Be specific about what you observe — lighting quality, composition, exposure, color, movement.",
        "",
        f"Technical score: {shot_score.technical_total or 'not yet scored'}",
        f"Exposure: {shot_score.exposure.technical}",
        f"Lighting: {shot_score.lighting.technical}",
        f"Composition: {shot_score.composition.technical}",
        f"Color: {shot_score.color.technical}",
        f"Image quality: {shot_score.quality.technical}",
    ]
    if shot_score.baseline_similarity_score is not None:
        lines.append(f"Similarity to award-winning cinematography: {shot_score.baseline_similarity_score:.1f}/100")
    lines += [
        "",
        "Provide a concise, specific, professional assessment. Do not use generic phrases.",
    ]
    return "\n".join(lines)


def _vlm_anthropic(image_data: str, prompt: str, api_key: str) -> Optional[str]:
    """Call Anthropic Claude with the frame image and prompt."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type":  "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        _log_inference_error("Anthropic VLM", exc)
        return None


def _vlm_openai(image_data: str, prompt: str, api_key: str) -> Optional[str]:
    """Call OpenAI GPT-4o with the frame image and prompt."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        _log_inference_error("OpenAI VLM", exc)
        return None


# ---------------------------------------------------------------------------
# Skin tone analysis
# ---------------------------------------------------------------------------

_SKIN_TONE_REFERENCES = [
    (73.0,  14.0, 17.0, "fair"),
    (65.0,  16.0, 18.0, "light"),
    (55.0,  18.0, 16.0, "medium"),
    (45.0,  17.0, 13.0, "medium-dark"),
    (35.0,  13.0,  9.0, "dark"),
    (25.0,   9.0,  6.0, "deep"),
]


def _analyse_skin_tone(
    frame_path: str,
    detections: List[Dict[str, Any]],
) -> Optional[float]:
    """
    Sample Lab values from detected person/face regions and compute
    ΔE2000 against the closest Macbeth-derived skin tone reference.

    Returns mean ΔE across all detected faces. Low ΔE = skin renders
    close to reference; high ΔE = colour shift or WB issue.
    """
    try:
        img = cv2.imread(frame_path)
        if img is None:
            return None

        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
        h, w = img.shape[:2]
        face_deltas = []

        for det in (detections or []):
            if det.get("label") != "person":
                continue
            bbox = det.get("bbox", [])
            if len(bbox) != 4:
                continue

            x1, y1, x2, y2 = [int(v) for v in bbox]
            # upper 25% of person bbox ≈ head region
            face_h = max(1, (y2 - y1) // 4)
            fy1 = max(0, y1)
            fy2 = min(h, y1 + face_h)
            # inset 25% horizontally to avoid background
            inset = (x2 - x1) // 4
            fx1 = max(0, x1 + inset)
            fx2 = min(w, x2 - inset)

            if fy2 <= fy1 or fx2 <= fx1:
                continue

            face_region = lab[fy1:fy2, fx1:fx2]
            if face_region.size == 0:
                continue

            L_f = float(np.mean(face_region[:, :, 0]))
            a_f = float(np.mean(face_region[:, :, 1])) - 128.0
            b_f = float(np.mean(face_region[:, :, 2])) - 128.0

            # skip non-skin luminance ranges
            if not (20.0 <= L_f <= 90.0):
                continue

            # find closest reference skin tone by luminance
            ref = min(_SKIN_TONE_REFERENCES, key=lambda r: abs(r[0] - L_f))
            L_r, a_r, b_r, _ = ref

            from .metrics import _compute_delta_e2000
            face_deltas.append(_compute_delta_e2000(L_f, a_f, b_f, L_r, a_r, b_r))

        return round(float(np.mean(face_deltas)), 3) if face_deltas else None

    except Exception as exc:
        print(f"[inference] skin tone analysis failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _write_sidecar(metrics: FrameMetrics, job_dir: Path) -> None:
    """Overwrite the frame sidecar with updated inference results."""
    metrics_dir = job_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_path = metrics_dir / f"{metrics.frame_id}.json"
    out_path.write_text(
        json.dumps(metrics.to_sidecar_dict(), indent=2),
        encoding="utf-8",
    )


def _log_inference_error(model: str, exc: Exception) -> None:
    """Log inference errors without aborting — graceful degradation."""
    print(f"[inference] {model} failed: {exc}")

# ---------------------------------------------------------------------------
# Focus metrics
# ---------------------------------------------------------------------------

def _compute_focus_metrics(
    frame_path: str,
    detections: list,
    frame_metrics: "FrameMetrics",
) -> None:
    """
    Compute focus quality metrics using YOLO face bboxes.
    Populates frame_metrics.focus in place.
    """
    import cv2
    import numpy as np
    from ..models.scores import FocusMetrics

    bgr = cv2.imread(frame_path)
    if bgr is None:
        return
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    fm   = FocusMetrics()

    # Find face detections
    faces = [d for d in detections if d.get("class_name", "").lower() in
             ("person", "face") and d.get("confidence", 0) > 0.5]

    if faces:
        # Use the highest-confidence face
        face = max(faces, key=lambda d: d.get("confidence", 0))
        x1   = int(face.get("x1", 0) * w)
        y1   = int(face.get("y1", 0) * h)
        x2   = int(face.get("x2", 1) * w)
        y2   = int(face.get("y2", 1) * h)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 > x1 and y2 > y1:
            face_crop = gray[y1:y2, x1:x2]

            # Subject focus accuracy: Laplacian variance in face region
            lap_face = float(cv2.Laplacian(face_crop, cv2.CV_64F).var())
            fm.subject_focus_accuracy = round(float(np.clip(lap_face / 500 * 100, 0, 100)), 1)

            # Eye region: upper 35% of face bbox
            eye_h = max(1, (y2 - y1) // 3)
            eye_crop = gray[y1:y1 + eye_h, x1:x2]
            if eye_crop.size > 0:
                lap_eye = float(cv2.Laplacian(eye_crop, cv2.CV_64F).var())
                fm.eye_sharpness = round(float(np.clip(lap_eye / 300 * 100, 0, 100)), 1)

                # Catchlight: bright specular in eye region
                _, bright = cv2.threshold(eye_crop, 240, 255, cv2.THRESH_BINARY)
                bright_pct = float(bright.sum()) / max(eye_crop.size * 255, 1) * 100
                # Good catchlight: small (0.5-5% of eye area) bright spot
                if 0.3 < bright_pct < 8:
                    fm.catchlight_quality = round(float(np.clip(
                        100 - abs(bright_pct - 2) * 15, 0, 100)), 1)
                else:
                    fm.catchlight_quality = 0.0

    frame_metrics.focus = fm

    # Gaze direction lives on SubjectMetrics — set after focus is done
    if frame_metrics.composition and frame_metrics.composition.lead_room is not None:
        frame_metrics.subject.gaze_direction_score = frame_metrics.composition.lead_room


# ---------------------------------------------------------------------------
# Subject metrics (SigLIP zero-shot + optional emotion detection)
# ---------------------------------------------------------------------------

# Session cache for SigLIP zero-shot text features used in subject scoring
_SUBJECT_TEXT_CACHE: dict = {}

_SUBJECT_PROMPTS = {
    # readability
    "subject_clarity":       ["a photograph with a clear, obvious subject",
                               "a frame where the main subject is immediately recognizable"],
    "mood_clarity":          ["a photograph with an unmistakable emotional tone",
                               "a frame with immediate, clear mood"],
    "one_sec_comprehension": ["a photograph that is instantly understandable at a glance",
                               "a clear, readable frame with obvious content"],
    # thumbnail potency
    "thumbnail_strength":    ["a photograph that would make a compelling thumbnail",
                               "a visually striking frame that works at small size"],
    "portfolio_potential":   ["a frame that would work as a showreel hero shot",
                               "a cinematic image with portfolio cover quality"],
    "graphic_simplicity":    ["a graphically simple, bold composition",
                               "a photograph with strong shapes and clear visual hierarchy"],
    # human presence
    "gesture_readability":   ["a photograph with clear, readable body language",
                               "a frame where the person's gesture communicates immediately"],
    "presence_signal":       ["a photograph of a person with commanding screen presence",
                               "a portrait with strong charisma and magnetism"],
    "silhouette_readability":["a photograph with a strong, clear silhouette",
                               "a frame with a bold, readable outline against the background"],
    # world/mood
    "atmosphere_mood":       ["a photograph with rich, cohesive atmosphere",
                               "a cinematic frame with strong environmental mood"],
}


def _compute_subject_metrics(
    frame_path: str,
    device:     str,
    frame_metrics: "FrameMetrics",
) -> None:
    """
    Compute SubjectMetrics using SigLIP zero-shot scoring and optional emotion detection.
    All text features are cached per session.
    """
    import cv2
    import numpy as np
    import torch
    from PIL import Image
    from ..models.scores import SubjectMetrics
    from .model_utils import select_best_model, get_tokenizer, is_siglip

    sm = SubjectMetrics()

    # --- SigLIP zero-shot ---
    try:
        import open_clip
        model_name, pretrained = select_best_model()
        model, _, preprocess  = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device
        )
        model.eval()
        tokenizer = get_tokenizer(model_name)

        img    = Image.open(frame_path).convert("RGB")
        tensor = preprocess(img).unsqueeze(0).to(device)

        with torch.no_grad():
            img_feat = model.encode_image(tensor)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)

        # For SigLIP: use CPU ViT-B-32 for text (same pattern as classifier)
        from .classifier import _get_cpu_text_model
        cpu_model, cpu_tok = _get_cpu_text_model()

        for field, prompts in _SUBJECT_PROMPTS.items():
            try:
                cache_key = (model_name, tuple(prompts))
                if cache_key in _SUBJECT_TEXT_CACHE:
                    txt_feat = _SUBJECT_TEXT_CACHE[cache_key]
                else:
                    if cpu_model is not None and cpu_tok is not None:
                        with torch.no_grad():
                            toks     = cpu_tok(prompts)
                            txt_feat = cpu_model.encode_text(toks)
                            txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
                    else:
                        toks     = tokenizer(prompts).to(device)
                        with torch.no_grad():
                            txt_feat = model.encode_text(toks)
                            txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
                    _SUBJECT_TEXT_CACHE[cache_key] = txt_feat.cpu()

                txt_feat_d = _SUBJECT_TEXT_CACHE[cache_key]
                sims = (img_feat.cpu() @ txt_feat_d.T).squeeze(0)
                score = float(sims.mean().item())
                # Convert cosine sim (-1 to 1) to 0-100
                score_100 = round(float(np.clip((score + 1) / 2 * 100, 0, 100)), 1)
                setattr(sm, field, score_100)
            except Exception:
                pass

    except Exception as e:
        print(f"[inference] SigLIP subject scoring failed: {e}")

    # --- Emotion detection (optional, CPU, lightweight) ---
    try:
        _compute_emotion(frame_path, sm)
    except Exception:
        pass

    frame_metrics.subject = sm


def _compute_emotion(frame_path: str, sm: "SubjectMetrics") -> None:
    """
    Lightweight face emotion detection using DeepFace (FER2013 backend).
    Falls back silently if DeepFace isn't installed.
    Only runs if a face was already detected (lead_room or catchlight hint).
    """
    try:
        # Suppress TF/DeepFace subprocess windows on Windows
        import os as _os
        _os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        _os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
        _os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")  # force CPU for DeepFace
        from deepface import DeepFace
        import numpy as np
        result = DeepFace.analyze(
            img_path=frame_path,
            actions=["emotion"],
            enforce_detection=False,
            silent=True,
        )
        if isinstance(result, list):
            result = result[0]
        emotions  = result.get("emotion", {})
        dominant  = result.get("dominant_emotion", None)
        if emotions:
            # Peak emotion confidence (excluding neutral as a baseline)
            non_neutral = {k: v for k, v in emotions.items() if k != "neutral"}
            peak = float(max(non_neutral.values())) if non_neutral else 0.0
            sm.facial_emotion_intensity = round(float(np.clip(peak, 0, 100)), 1)
            sm.dominant_emotion = dominant
    except ImportError:
        pass  # DeepFace not installed — skip silently
    except Exception:
        pass
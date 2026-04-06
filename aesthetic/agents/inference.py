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


def _get_device(gpu_enabled: bool) -> str:
    global _device
    if _device is None:
        try:
            import torch
            _device = "cuda" if (gpu_enabled and torch.cuda.is_available()) else "cpu"
        except ImportError:
            _device = "cpu"
    return _device


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

    # YOLO detection
    if features.get("yolo_enabled", True):
        try:
            detections = _run_yolo(frame_path, device)
            inference.detections = detections
        except Exception as exc:
            import traceback
            print(f"[inference] YOLO failed for {frame_path}: {exc}")
            traceback.print_exc()

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
            model_name = "ViT-B-32"
            pretrained = "openai"
            _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
                model_name,
                pretrained=pretrained,
                device=device,
            )
            _clip_model.eval()
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
    Run MiDaS depth estimation on the frame.
    Saves the depth map as a greyscale PNG and returns the path.
    """
    global _midas_model, _midas_transform, _midas_version

    try:
        import torch

        if _midas_model is None:
            model_type = "MiDaS_small"
            _midas_model = torch.hub.load("intel-isl/MiDaS", model_type, trust_repo=True)
            _midas_model.to(device)
            _midas_model.eval()

            midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
            _midas_transform = midas_transforms.small_transform
            _midas_version = model_type

        img = cv2.imread(frame_path)
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

        depth = prediction.cpu().numpy()

        # normalise to 0-255 and save
        depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        depth_dir  = job_dir / "depth"
        depth_dir.mkdir(parents=True, exist_ok=True)
        depth_path = depth_dir / f"{frame_id}_depth.png"
        cv2.imwrite(str(depth_path), depth_norm)

        return str(depth_path)

    except Exception as exc:
        _log_inference_error("MiDaS", exc)
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
# aesthetic/agents/model_utils.py
#
# Shared model selection and device detection utilities.
# Single source of truth — all agents import from here.
#
# Model preference cascade (best → fallback):
#   SigLIP ViT-SO400M-14-384  (Google, 2023 — best zero-shot, 1152-dim)
#   SigLIP ViT-SO400M-14      (Google, 2023 — 1152-dim)
#   CLIP ViT-L-14-336         (OpenAI, 768-dim, high-res input)
#   CLIP ViT-L-14             (OpenAI, 768-dim — reliable baseline)
#   CLIP ViT-B-32             (OpenAI, 512-dim — last resort)
#
# NOTE ON EMBEDDING DIMENSIONS:
#   ViT-B-32  → 512-dim
#   ViT-L-14  → 768-dim
#   SigLIP SO400M → 1152-dim
#
# The baseline corpus stores embeddings. If you switch model families
# (e.g. ViT-B-32 → ViT-L-14) the stored embeddings are incompatible
# and the baseline must be rebuilt. The baseline_trainer reads the dim
# from the stored embeddings automatically.
#
# GPU detection:
#   Tries CUDA (any NVIDIA GPU) → MPS (Apple Silicon) → CPU
#   No specific GPU model is required or assumed.

from __future__ import annotations
from typing import Optional, Tuple
import warnings

# ---------------------------------------------------------------------------
# Model preference
# ---------------------------------------------------------------------------

CLIP_MODEL_PREFERENCE: list[Tuple[str, str]] = [
    # (model_name, pretrained_tag)
    ("ViT-SO400M-14-SigLIP-384", "webli"),   # SigLIP large — best
    ("ViT-SO400M-14-SigLIP",     "webli"),   # SigLIP base
    ("ViT-L-14-336",             "openai"),  # CLIP L high-res
    ("ViT-L-14",                 "openai"),  # CLIP L standard
    ("ViT-B-32",                 "openai"),  # CLIP B — last resort
]

# Embedding dimensions by model name prefix
EMBEDDING_DIMS: dict[str, int] = {
    "ViT-SO400M-14-SigLIP-384": 1152,
    "ViT-SO400M-14-SigLIP":     1152,
    "ViT-L-14-336":              768,
    "ViT-L-14":                  768,
    "ViT-B-32":                  512,
}

_selected_model: Optional[Tuple[str, str]] = None


def select_best_model() -> Tuple[str, str]:
    """
    Return (model_name, pretrained_tag) for the best CLIP/SigLIP model
    available in the installed open_clip. Cached after first call.
    """
    global _selected_model
    if _selected_model is not None:
        return _selected_model

    try:
        import open_clip
        available = {(m, p) for m, p in open_clip.list_pretrained()}
        for model_name, pretrained in CLIP_MODEL_PREFERENCE:
            if (model_name, pretrained) in available:
                _selected_model = (model_name, pretrained)
                print(f"[model_utils] selected model: {model_name} / {pretrained}")
                return _selected_model
    except Exception as e:
        print(f"[model_utils] model selection failed: {e}")

    _selected_model = ("ViT-L-14", "openai")
    return _selected_model


def get_model_dim(model_name: str) -> int:
    """Return embedding dimension for a given model name."""
    for key, dim in EMBEDDING_DIMS.items():
        if key.lower() in model_name.lower():
            return dim
    return 768  # safe default


def is_siglip(model_name: str) -> bool:
    """True if the model is a SigLIP variant (uses different tokenizer/similarity)."""
    return "siglip" in model_name.lower()


# SigLIP has a shorter context window than standard CLIP
_SIGLIP_CONTEXT_LENGTH = 64   # SigLIP max sequence length
_CLIP_CONTEXT_LENGTH   = 77   # standard CLIP max sequence length


def get_tokenizer(model_name: str):
    """
    Get the appropriate tokenizer for a model.
    Returns a callable that always produces tokens of the correct length.

    SigLIP uses 64-token sequences. Passing 77-token sequences to SigLIP
    causes a GPU index-out-of-bounds assertion that floods the console.

    We enforce the limit by passing context_length to the tokenizer call.
    open_clip tokenizers accept this as a keyword argument in all versions.
    """
    import open_clip
    ctx = _SIGLIP_CONTEXT_LENGTH if is_siglip(model_name) else _CLIP_CONTEXT_LENGTH

    try:
        tok = open_clip.get_tokenizer(model_name)
    except Exception:
        try:
            tok = open_clip.get_tokenizer("ViT-L-14")
        except Exception:
            tok = open_clip.get_tokenizer("ViT-B-32")

    class _SafeTokenizer:
        def __init__(self, base, context_length):
            self._base = base
            self._ctx  = context_length

        def __call__(self, texts):
            # Always tokenize first then hard-truncate.
            # Do NOT use context_length kwarg — open_clip's SigLIP tokenizer
            # accepts it without error but produces 77 tokens anyway (ignores it).
            # Tensor slicing is the only reliable way to enforce the limit.
            tokens = self._base(texts)
            if hasattr(tokens, 'shape') and len(tokens.shape) >= 2:
                return tokens[:, :self._ctx]
            return tokens

    return _SafeTokenizer(tok, ctx)


def load_model(device: str):
    """
    Load the best available CLIP/SigLIP model onto the given device.
    Returns (model, preprocess, model_name, pretrained_tag).
    """
    import open_clip
    model_name, pretrained = select_best_model()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device
        )
    model.eval()
    return model, preprocess, model_name, pretrained


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

# Cache per gpu_enabled state — a CPU-forced call never blocks later GPU calls
_device_cache: dict = {}


def get_device(gpu_enabled: bool = True) -> str:
    """
    Detect the best available compute device.

    Priority: CUDA (any NVIDIA GPU) → MPS (Apple Silicon) → CPU

    gpu_enabled=False forces CPU for that call only.
    Cached per gpu_enabled state so a CPU-forced call never poisons
    subsequent GPU-enabled calls.
    """
    global _device_cache
    key = bool(gpu_enabled)
    if key in _device_cache:
        return _device_cache[key]

    if not gpu_enabled:
        _device_cache[key] = "cpu"
    else:
        try:
            import torch
            if torch.cuda.is_available():
                _device_cache[key] = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                _device_cache[key] = "mps"
            else:
                _device_cache[key] = "cpu"
        except ImportError:
            _device_cache[key] = "cpu"

    print(f"[model_utils] compute device: {_device_cache[key]} (gpu_enabled={gpu_enabled})")
    return _device_cache[key]


def reset_device_cache() -> None:
    """Force re-detection of device on next call (useful for testing)."""
    global _device_cache, _selected_model
    _device_cache = {}
    _selected_model = None

# ---------------------------------------------------------------------------
# Runtime preset detection
# ---------------------------------------------------------------------------

def detect_preset() -> str:
    """
    Silently detect the appropriate runtime preset for this machine.

    Returns one of: 'fast', 'balanced', 'precision'

    Logic:
      - CUDA with ≥8GB VRAM  → balanced
      - CUDA with <8GB VRAM  → fast
      - MPS (Apple Silicon)  → balanced (unified memory)
      - CPU only             → fast

    This is the automatic default. Users can override via the UI preset
    dropdown — 'auto' always defers to this function.
    """
    try:
        import torch
        if torch.cuda.is_available():
            vram = torch.cuda.get_device_properties(0).total_memory
            vram_gb = vram / (1024 ** 3)
            preset = "balanced" if vram_gb >= 8 else "fast"
            print(f"[model_utils] preset auto-detected: {preset} "
                  f"(CUDA, {vram_gb:.1f}GB VRAM)")
            return preset
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            print("[model_utils] preset auto-detected: balanced (MPS)")
            return "balanced"
    except Exception:
        pass
    print("[model_utils] preset auto-detected: fast (CPU only)")
    return "fast"


# Preset definitions — all values override config.yaml defaults when active
PRESETS: dict = {
    "fast": {
        "description":        "Fastest pass — reduced sampling, no depth analysis",
        "per_scene_candidates": 5,
        "per_scene_keep_pct":   0.35,
        "shortlist_pct":        0.15,
        "midas_enabled":        False,
        "yolo_enabled":         True,
        "clip_enabled":         True,
        "subject_metrics":      False,   # skip SigLIP zero-shot per frame
        "top_k_multiplier":     1.0,
    },
    "balanced": {
        "description":        "Default — full pipeline, standard sampling",
        "per_scene_candidates": 9,
        "per_scene_keep_pct":   0.40,
        "shortlist_pct":        0.25,
        "midas_enabled":        True,
        "yolo_enabled":         True,
        "clip_enabled":         True,
        "subject_metrics":      True,
        "top_k_multiplier":     1.0,
    },
    "precision": {
        "description":        "Maximum quality — dense sampling, full depth analysis",
        "per_scene_candidates": 15,
        "per_scene_keep_pct":   0.50,
        "shortlist_pct":        0.40,
        "midas_enabled":        True,
        "yolo_enabled":         True,
        "clip_enabled":         True,
        "subject_metrics":      True,
        "top_k_multiplier":     1.5,    # allows selecting more shots
    },
}


def resolve_preset(user_choice: str = "auto") -> dict:
    """
    Resolve a user preset choice to a settings dict.
    'auto' → detect_preset() → look up PRESETS.
    Any named preset overrides auto-detection.
    Returns the preset dict merged — caller applies to config.
    """
    if user_choice == "auto" or user_choice not in PRESETS:
        name = detect_preset()
    else:
        name = user_choice
    result = {"name": name, **PRESETS[name]}
    return result
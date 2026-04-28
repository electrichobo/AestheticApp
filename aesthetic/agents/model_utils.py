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

_device: Optional[str] = None


def get_device(gpu_enabled: bool = True) -> str:
    """
    Detect the best available compute device.

    Priority: CUDA (any NVIDIA GPU) → MPS (Apple Silicon) → CPU

    Works with any CUDA-capable GPU — RTX 2060, 3090, 4080, 5080, etc.
    No specific GPU model is assumed or required.

    gpu_enabled=False forces CPU (useful for testing or low-memory situations).
    """
    global _device
    if _device is None:
        if not gpu_enabled:
            _device = "cpu"
        else:
            try:
                import torch
                if torch.cuda.is_available():
                    _device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    _device = "mps"
                else:
                    _device = "cpu"
            except ImportError:
                _device = "cpu"
        print(f"[model_utils] compute device: {_device}")
    return _device


def reset_device_cache() -> None:
    """Force re-detection of device on next call (useful for testing)."""
    global _device, _selected_model
    _device = None
    _selected_model = None
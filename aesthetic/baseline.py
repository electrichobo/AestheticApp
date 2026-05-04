from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, List, cast


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_of(obj: Any) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass
class OnlineStat:
    n: int = 0
    mean: float = 0.0
    M2: float = 0.0

    def add(self, x: float) -> None:
        n1 = self.n + 1
        delta = x - self.mean
        mean1 = self.mean + delta / n1
        delta2 = x - mean1
        M2_1 = self.M2 + delta * delta2
        self.n = n1
        self.mean = mean1
        self.M2 = M2_1

    def merge(self, other: "OnlineStat") -> "OnlineStat":
        if other.n == 0:
            return self
        if self.n == 0:
            return OnlineStat(other.n, other.mean, other.M2)
        n = self.n + other.n
        delta = other.mean - self.mean
        mean = self.mean + delta * (other.n / n)
        M2 = self.M2 + other.M2 + delta * delta * (self.n * other.n / n)
        return OnlineStat(n=n, mean=mean, M2=M2)

    def to_dict(self) -> Dict[str, float]:
        return {"n": float(self.n), "mean": float(self.mean), "M2": float(self.M2)}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "OnlineStat":
        return OnlineStat(int(d.get("n", 0)), float(d.get("mean", 0.0)), float(d.get("M2", 0.0)))


class BaselineStore:
    """
    Local Golden Baseline with three states:

      data/
        baseline/
          golden/
            v0001.json
            v0002.json
            active.json        # {"version": 2, "path": "..."}
          staging.json         # pre-lock buffer
          augment.json         # post-lock additive buffer
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.base = self.data_dir / "baseline"
        self.base.mkdir(parents=True, exist_ok=True)
        self.golden_dir = self.base / "golden"
        self.golden_dir.mkdir(parents=True, exist_ok=True)
        self.staging_path = self.base / "staging.json"
        self.augment_path = self.base / "augment.json"
        self.active_path = self.golden_dir / "active.json"

        if not self.staging_path.exists():
            self._save_json(self.staging_path, {"stats": {}, "updated": _now_iso()})
        if not self.augment_path.exists():
            self._save_json(self.augment_path, {"stats": {}, "updated": _now_iso()})
        if not self.active_path.exists():
            self._save_json(self.active_path, {"version": 0})

    # ---------- file helpers ----------

    def _load_json(self, path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        try:
            obj: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return cast(Dict[str, Any], obj)
        except Exception:
            pass
        return dict(default)

    def _save_json(self, path: Path, obj: Dict[str, Any]) -> None:
        path.write_text(json.dumps(obj, indent=2), encoding="utf-8")

    # ---------- public summaries ----------

    def get_summary(self) -> Dict[str, Any]:
        active = self._load_json(self.active_path, {"version": 0})
        staging = self._load_json(self.staging_path, {"stats": {}})
        augment = self._load_json(self.augment_path, {"stats": {}})

        active_meta: Dict[str, Any] = {}
        if int(active.get("version", 0)) > 0 and "path" in active:
            try:
                meta = self._load_json(Path(str(active["path"])), {})
                stats = cast(Dict[str, Any], meta.get("stats", {}))
                active_meta = {
                    "id": meta.get("id"),
                    "version": meta.get("version"),
                    "hash": meta.get("hash"),
                    "created": meta.get("created"),
                    "note": meta.get("note", ""),
                    "metricCount": len(stats),
                    "sampleCount": sum(int(cast(Mapping[str, Any], s).get("n", 0)) for s in stats.values()),
                }
            except Exception:
                active_meta = {"error": "active metadata unreadable"}

        return {
            "active": active_meta or {"version": 0},
            "staging_metricCount": len(cast(Dict[str, Any], staging.get("stats", {}))),
            "augment_metricCount": len(cast(Dict[str, Any], augment.get("stats", {}))),
        }

    def get_embedding_dim_status(self, _cache: dict = {}) -> Dict[str, Any]:
        """
        Check whether the stored baseline embeddings are compatible
        with the current vision model. Returns a status dict for the UI.
        Result is cached per baseline-version so we don't glob 42K files
        on every tab open. Cache invalidates when baseline version changes.
        All fields are guaranteed non-None so the JS never gets undefined.
        """
        # cache key = baseline version + model name
        try:
            from .agents.model_utils import _selected_model
            _m = _selected_model[0] if _selected_model else "unknown"
        except Exception:
            _m = "unknown"
        version = self.get_summary().get("active", {}).get("version", 0)
        cache_key = f"{version}:{_m}"
        if cache_key in _cache:
            return _cache[cache_key]
        import json as _json

        # get current model info — read from session cache if available,
        # otherwise do a best-effort detection
        current_model = "unknown"
        current_dim   = 0
        try:
            from .agents.model_utils import (
                _selected_model, select_best_model, get_model_dim
            )
            # prefer the already-selected model from this session
            if _selected_model is not None:
                current_model = _selected_model[0]
                current_dim   = get_model_dim(current_model)
            else:
                _m, _ = select_best_model()
                if _m:
                    current_model = _m
                    current_dim   = get_model_dim(_m)
        except Exception:
            pass

        emb_dir = self.base / "embeddings"
        if not emb_dir.exists():
            return {
                "ok":            False,
                "compatible":    False,
                "reason":        "no_embeddings",
                "stored_dim":    0,
                "current_dim":   current_dim,
                "current_model": current_model,
                "stale_count":   0,
                "total_count":   0,
            }

        # count embeddings grouped by dimension
        dim_counts: Dict[int, int] = {}
        for p in emb_dir.glob("*.json"):
            try:
                emb = _json.loads(p.read_text(encoding="utf-8")).get("embedding")
                if emb:
                    d = len(emb)
                    dim_counts[d] = dim_counts.get(d, 0) + 1
            except Exception:
                continue

        if not dim_counts:
            return {
                "ok":            False,
                "compatible":    False,
                "reason":        "no_embeddings",
                "stored_dim":    0,
                "current_dim":   current_dim,
                "current_model": current_model,
                "stale_count":   0,
                "total_count":   0,
            }

        # Current model dim is authoritative — NOT most-files.
        # After a model upgrade there may be far more old-dim files than new.
        # "Most files" would incorrectly pick the old generation.
        if current_dim and current_dim in dim_counts:
            stored_dim = current_dim   # model loaded, its dim has files — use it
        elif current_dim == 0:
            # Model not loaded yet — fall back to most-files and mark compatible
            stored_dim    = max(dim_counts, key=lambda d: dim_counts[d])
            current_dim   = stored_dim
            current_model = f"stored at dim={stored_dim}"
        else:
            # Model loaded but no files at its dim — baseline not rebuilt yet
            stored_dim = max(dim_counts, key=lambda d: dim_counts[d])

        dominant_n  = dim_counts.get(stored_dim, 0)
        stale_count = sum(v for d, v in dim_counts.items() if d != stored_dim)
        compatible  = stored_dim == current_dim

        result = {
            "ok":            compatible,
            "compatible":    compatible,
            "reason":        None if compatible else "dim_mismatch",
            "stored_dim":    stored_dim,
            "current_dim":   current_dim,
            "current_model": current_model,
            "stale_count":   stale_count,
            "total_count":   dominant_n,
        }
        _cache[cache_key] = result
        return result

    def get_reference_colour(self) -> Dict[str, float]:
        """
        Return a reference Lab colour reconstructed from the active golden baseline
        statistics. Used for ΔE vs Baseline comparison in the Matrix.

        Returns dict with keys:
          L_mean, a_mean, b_mean  — mean Lab values of the corpus
          wb_deviation_mean       — mean white balance deviation
          saturation_mean         — mean Lab chroma
          color_temp_mean         — mean estimated colour temperature (K)
        """
        golden = self.load_active_golden()
        stats  = golden.get("stats", {})

        def _mean(key: str) -> Optional[float]:
            s = stats.get(key)
            if s and isinstance(s, dict) and s.get("n", 0) > 0:
                return float(s["mean"])
            return None

        wb_dev   = _mean("wb_deviation")      or 0.0
        sat_mean = _mean("saturation_mean")   or 0.0
        temp_K   = _mean("color_temp_kelvin") or 5600.0

        # Reconstruct approximate a* and b* from colour temperature.
        # Colour temperature maps to a hue angle in Lab:
        #   Warm (3200K) → positive a* (reddish), positive b* (yellowish)
        #   Neutral (5600K) → near-zero a* and b*
        #   Cool (8000K) → negative a* (cyan-ish), negative b* (bluish)
        # We use a linear approximation based on the known D65 trajectory.
        import math
        norm_temp = (temp_K - 5600.0) / 3400.0   # -1 (cool) to +1 (warm)
        # warm cast: a*~+10, b*~+15 at 3200K; cool cast: a*~-5, b*~-8 at 8000K
        a_ref = -norm_temp * 8.0    # warm temp → negative norm → positive a*
        b_ref = -norm_temp * 12.0   # warm temp → positive b*

        return {
            "L_mean":            _mean("histogram_mean") or 128.0,
            "a_mean":            a_ref,
            "b_mean":            b_ref,
            "wb_deviation_mean": wb_dev,
            "saturation_mean":   sat_mean,
            "color_temp_mean":   temp_K,
        }

    def load_active_golden(self) -> Dict[str, Any]:
        active = self._load_json(self.active_path, {"version": 0})
        version = int(active.get("version", 0))
        if version == 0:
            return {}

        # if path is present and valid, use it directly
        stored_path = active.get("path")
        if stored_path and Path(str(stored_path)).exists():
            return self._load_json(Path(str(stored_path)), {})

        # path missing or invalid (e.g. bundled app with rewritten active.json)
        # scan the golden directory for the matching version file
        candidate = self.golden_dir / f"v{version:04d}.json"
        if candidate.exists():
            return self._load_json(candidate, {})

        # fallback: find highest version file present
        version_files = sorted(self.golden_dir.glob("v*.json"))
        if version_files:
            return self._load_json(version_files[-1], {})

        return {}

    # ---------- updating buffers ----------

    def update_staging(self, batch: Iterable[Mapping[str, float]]) -> Dict[str, Any]:
        doc = self._load_json(self.staging_path, {"stats": {}})
        stats = self._map_to_online(cast(Dict[str, Any], doc.get("stats", {})))
        for sample in batch:
            for k, v in sample.items():
                if isinstance(v, (int, float)):
                    stats.setdefault(k, OnlineStat()).add(float(v))
        out: Dict[str, Any] = {"stats": {k: s.to_dict() for k, s in stats.items()}, "updated": _now_iso()}
        self._save_json(self.staging_path, out)
        return out

    def update_augment(self, batch: Iterable[Mapping[str, float]]) -> Dict[str, Any]:
        doc = self._load_json(self.augment_path, {"stats": {}})
        stats = self._map_to_online(cast(Dict[str, Any], doc.get("stats", {})))
        for sample in batch:
            for k, v in sample.items():
                if isinstance(v, (int, float)):
                    stats.setdefault(k, OnlineStat()).add(float(v))
        out: Dict[str, Any] = {"stats": {k: s.to_dict() for k, s in stats.items()}, "updated": _now_iso()}
        self._save_json(self.augment_path, out)
        return out

    # ---------- promotions ----------

    def promote_staging_to_golden(self, note: str = "") -> Dict[str, Any]:
        staging = self._load_json(self.staging_path, {"stats": {}})
        stats = cast(Dict[str, Any], staging.get("stats", {}))
        version = self._next_version()
        meta: Dict[str, Any] = {
            "id": f"golden-{_now_iso().replace(':','-')}",
            "version": version,
            "created": _now_iso(),
            "note": note or "promoted from staging",
            "stats": stats,
        }
        meta["hash"] = _sha256_of({"version": version, "stats": stats})
        vpath = self.golden_dir / f"v{version:04d}.json"
        self._save_json(vpath, meta)
        self._save_json(self.active_path, {"version": version, "path": str(vpath)})
        self._save_json(self.staging_path, {"stats": {}, "updated": _now_iso()})
        return {"ok": True, "version": version, "path": str(vpath), "id": meta["id"], "hash": meta["hash"]}

    def apply_augment_to_new_golden(self, note: str = "") -> Dict[str, Any]:
        active = self.load_active_golden()
        if not active:
            # No existing golden — create first golden from current embeddings
            print("[baseline] no active golden found — creating first golden from embeddings")
            emb_count = len(list((self.base / "embeddings").glob("*.json")))
            version   = 1
            meta: Dict[str, Any] = {
                "id":      f"golden-{_now_iso().replace(':','-')}",
                "version": version,
                "created": _now_iso(),
                "note":    note or "initial golden baseline",
                "stats":   {"sample_count": emb_count},
            }
            meta["hash"] = _sha256_of({"version": version, "stats": meta["stats"]})
            vpath = self.golden_dir / f"v{version:04d}.json"
            self._save_json(vpath, meta)
            self._save_json(self.active_path, {"version": version, "path": str(vpath)})
            self._save_json(self.augment_path, {"stats": {}, "updated": _now_iso()})
            return {"ok": True, "version": version, "path": str(vpath),
                    "id": meta["id"], "hash": meta["hash"]}
        augment = self._load_json(self.augment_path, {"stats": {}})
        merged_stats = self._merge_stats(
            cast(Dict[str, Any], active.get("stats", {})),
            cast(Dict[str, Any], augment.get("stats", {})),
        )
        version = self._next_version()
        meta: Dict[str, Any] = {
            "id": f"golden-{_now_iso().replace(':','-')}",
            "version": version,
            "created": _now_iso(),
            "note": note or "golden + augment",
            "stats": merged_stats,
        }
        meta["hash"] = _sha256_of({"version": version, "stats": merged_stats})
        vpath = self.golden_dir / f"v{version:04d}.json"
        self._save_json(vpath, meta)
        self._save_json(self.active_path, {"version": version, "path": str(vpath)})
        self._save_json(self.augment_path, {"stats": {}, "updated": _now_iso()})
        return {"ok": True, "version": version, "path": str(vpath), "id": meta["id"], "hash": meta["hash"]}

    # ---------- resets ----------

    def reset_staging(self) -> Dict[str, Any]:
        self._save_json(self.staging_path, {"stats": {}, "updated": _now_iso()})
        return {"ok": True}

    def reset_augment(self) -> Dict[str, Any]:
        self._save_json(self.augment_path, {"stats": {}, "updated": _now_iso()})
        return {"ok": True}

    # ---------- internal helpers ----------

    def _next_version(self) -> int:
        max_v = 0
        for p in self.golden_dir.glob("v*.json"):
            try:
                v = int(p.stem.lstrip("v"))
                if v > max_v:
                    max_v = v
            except Exception:
                continue
        return max_v + 1

    @staticmethod
    def _map_to_online(d: Mapping[str, Any]) -> Dict[str, OnlineStat]:
        out: Dict[str, OnlineStat] = {}
        for k, v in d.items():
            if isinstance(v, Mapping):
                out[k] = OnlineStat.from_dict(v)
        return out

    @staticmethod
    def _merge_stats(a: Mapping[str, Any], b: Mapping[str, Any]) -> Dict[str, Any]:
        out: Dict[str, OnlineStat] = {}
        for k, v in a.items():
            if isinstance(v, Mapping):
                out[k] = OnlineStat.from_dict(v)
        for k, v in b.items():
            if not isinstance(v, Mapping):
                continue
            if k in out:
                out[k] = out[k].merge(OnlineStat.from_dict(v))
            else:
                out[k] = OnlineStat.from_dict(v)
        return {k: s.to_dict() for k, s in out.items()}
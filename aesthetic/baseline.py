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

    def load_active_golden(self) -> Dict[str, Any]:
        active = self._load_json(self.active_path, {"version": 0})
        if int(active.get("version", 0)) == 0 or "path" not in active:
            return {}
        return self._load_json(Path(str(active["path"])), {})

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
            return {"ok": False, "error": "no active golden to augment"}
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

# aesthetic/agents/feedback_store.py
#
# Persistent feedback event store using SQLite.
#
# Design:
#   - All feedback from thumbs up / thumbs down is written here.
#   - Neutral (rating=0) deletions are also recorded as events so the
#     training pipeline can see retracted signals.
#   - Pairwise preferences are derived automatically: when a thumbs-up
#     shot ranked lower than a thumbs-down shot in the same job, that is
#     an implicit preference inversion and is stored as a pairwise pair.
#   - The schema is intentionally flat and forward-compatible — new columns
#     can be added without migrating old data.
#
# Schema:
#   feedback_events  — one row per user interaction
#   pairwise_prefs   — derived A-beats-B pairs for reranker training

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import DATA_DIR

DB_PATH = DATA_DIR / "feedback.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS feedback_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_ts        REAL    NOT NULL,           -- unix timestamp
    job_id          TEXT    NOT NULL,
    shot_id         TEXT    NOT NULL,
    rating          INTEGER NOT NULL,           -- 1=up, -1=down, 0=retracted
    rank            INTEGER,                    -- shot rank within job (1=best)
    total_score     REAL,
    technical_total REAL,
    creative_total  REAL,
    subjective_total REAL,
    scene_id        INTEGER,
    start_time      REAL,
    end_time        REAL,
    duration_sec    REAL,
    movement_type   TEXT,
    shot_scale      TEXT,
    scene_type      TEXT,
    shot_intent     TEXT,
    -- snapshot of category scores (JSON string)
    scores_json     TEXT,
    -- snapshot of metric detail averages (JSON string)
    metric_detail_json TEXT,
    -- embedding vector at time of feedback (JSON array string)
    -- stored so reranker training does not need to re-run inference
    embedding_json  TEXT,
    -- source video info
    source_file     TEXT,
    video_width     INTEGER,
    video_height    INTEGER,
    video_fps       REAL,
    color_primaries TEXT,
    color_trc       TEXT,
    is_log_encoded  INTEGER  -- 0/1
);

CREATE INDEX IF NOT EXISTS idx_fe_job    ON feedback_events(job_id);
CREATE INDEX IF NOT EXISTS idx_fe_shot   ON feedback_events(shot_id);
CREATE INDEX IF NOT EXISTS idx_fe_rating ON feedback_events(rating);
CREATE INDEX IF NOT EXISTS idx_fe_ts     ON feedback_events(event_ts);

CREATE TABLE IF NOT EXISTS pairwise_prefs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    derived_ts      REAL    NOT NULL,
    job_id          TEXT    NOT NULL,
    -- winner: the shot the user preferred (thumbs up)
    winner_shot_id  TEXT    NOT NULL,
    winner_rank     INTEGER,
    winner_score    REAL,
    -- loser: the shot the user rejected (thumbs down)
    loser_shot_id   TEXT    NOT NULL,
    loser_rank      INTEGER,
    loser_score     REAL,
    -- confidence: 1.0 = explicit up vs down pair, 0.7 = rank inversion pair
    confidence      REAL    NOT NULL DEFAULT 1.0,
    pair_type       TEXT    NOT NULL DEFAULT 'explicit'
    -- pair_type: 'explicit' = same job up+down, 'inversion' = rank inversion
);

CREATE INDEX IF NOT EXISTS idx_pp_job    ON pairwise_prefs(job_id);
CREATE INDEX IF NOT EXISTS idx_pp_winner ON pairwise_prefs(winner_shot_id);
CREATE INDEX IF NOT EXISTS idx_pp_loser  ON pairwise_prefs(loser_shot_id);
"""

# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_feedback_event(
    job_id:       str,
    shot_id:      str,
    rating:       int,
    shot_context: Optional[Dict[str, Any]] = None,
    job_context:  Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Persist a feedback event.

    shot_context: the full shot dict from the UI (scores, metrics, etc.)
    job_context:  VideoMeta fields from the job

    Only thumbs up (1) and thumbs down (-1) generate training signal.
    Neutral (0 = retracted) is recorded for completeness but excluded
    from pairwise derivation.

    Returns True on success.
    """
    sc = shot_context or {}
    jc = job_context  or {}

    scores = sc.get("scores", {})
    scores_json       = json.dumps(scores)            if scores else None
    metric_detail     = sc.get("metricDetail", {})
    metric_detail_json= json.dumps(metric_detail)     if metric_detail else None
    embedding         = sc.get("clip_embedding")
    embedding_json    = json.dumps(embedding)         if embedding else None

    try:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO feedback_events (
                event_ts, job_id, shot_id, rating,
                rank, total_score, technical_total, creative_total, subjective_total,
                scene_id, start_time, end_time, duration_sec,
                movement_type, shot_scale, scene_type, shot_intent,
                scores_json, metric_detail_json, embedding_json,
                source_file, video_width, video_height, video_fps,
                color_primaries, color_trc, is_log_encoded
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?
            )
        """, (
            time.time(), job_id, shot_id, rating,
            sc.get("id"),
            sc.get("totalScore"),
            sc.get("technicalTotal"),
            sc.get("creativeTotal"),
            sc.get("subjectiveTotal"),
            sc.get("scene_id"),
            sc.get("start"),
            sc.get("end"),
            sc.get("duration"),
            sc.get("movement_type"),
            sc.get("shot_scale"),
            sc.get("scene_type"),
            sc.get("shot_intent"),
            scores_json,
            metric_detail_json,
            embedding_json,
            jc.get("source_file"),
            jc.get("width"),
            jc.get("height"),
            jc.get("fps"),
            jc.get("color_primaries"),
            jc.get("color_trc"),
            int(bool(jc.get("is_log_encoded", False))),
        ))
        conn.commit()

        # derive pairwise preferences for this job
        if rating != 0:
            _update_pairwise(conn, job_id)

        conn.close()
        return True
    except Exception as exc:
        print(f"[feedback_store] save failed: {exc}")
        return False


def get_feedback_for_job(job_id: str) -> Dict[str, int]:
    """Return {shot_id: rating} for the most recent event per shot in a job."""
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT shot_id, rating FROM feedback_events
            WHERE job_id = ?
            ORDER BY event_ts DESC
        """, (job_id,)).fetchall()
        conn.close()

        # latest event per shot wins
        seen: Dict[str, int] = {}
        for row in rows:
            if row["shot_id"] not in seen:
                seen[row["shot_id"]] = row["rating"]
        # exclude neutral
        return {k: v for k, v in seen.items() if v != 0}
    except Exception:
        return {}


def get_all_feedback(
    min_rating: Optional[int] = None,
    limit: int = 10_000,
) -> List[Dict[str, Any]]:
    """
    Return all feedback events, optionally filtered by rating.
    Used by the feature export pipeline for reranker training.
    Only returns explicit signals (rating != 0) by default.
    """
    try:
        conn  = _get_conn()
        query = "SELECT * FROM feedback_events WHERE rating != 0"
        params: list = []
        if min_rating is not None:
            query  += " AND rating >= ?"
            params.append(min_rating)
        query += f" ORDER BY event_ts DESC LIMIT {limit}"
        rows  = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_pairwise_prefs(limit: int = 50_000) -> List[Dict[str, Any]]:
    """Return all derived pairwise preferences for reranker training."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            f"SELECT * FROM pairwise_prefs ORDER BY derived_ts DESC LIMIT {limit}"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_feedback_stats() -> Dict[str, Any]:
    """Return summary statistics for display in the UI."""
    try:
        conn = _get_conn()
        total  = conn.execute("SELECT COUNT(*) FROM feedback_events WHERE rating != 0").fetchone()[0]
        ups    = conn.execute("SELECT COUNT(*) FROM feedback_events WHERE rating = 1").fetchone()[0]
        downs  = conn.execute("SELECT COUNT(*) FROM feedback_events WHERE rating = -1").fetchone()[0]
        pairs  = conn.execute("SELECT COUNT(*) FROM pairwise_prefs").fetchone()[0]
        jobs   = conn.execute("SELECT COUNT(DISTINCT job_id) FROM feedback_events WHERE rating != 0").fetchone()[0]
        conn.close()
        return {
            "total_events":   total,
            "thumbs_up":      ups,
            "thumbs_down":    downs,
            "pairwise_pairs": pairs,
            "jobs_with_feedback": jobs,
            "reranker_ready": pairs >= 50,   # minimum useful training set
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Pairwise derivation
# ---------------------------------------------------------------------------

def _update_pairwise(conn: sqlite3.Connection, job_id: str) -> None:
    """
    Derive pairwise preferences for a job after each feedback event.

    Two types:
    1. explicit — a thumbs-up shot AND a thumbs-down shot exist in the same job.
       Every (up, down) combination is a pairwise preference.
    2. inversion — a thumbs-up shot ranked BELOW a thumbs-down shot in the same
       job (the user overrode the model's ranking). Lower confidence (0.7).

    Existing pairs for this job are replaced to stay current.
    """
    try:
        # get latest rating per shot for this job
        rows = conn.execute("""
            SELECT shot_id, rating, rank, total_score
            FROM feedback_events
            WHERE job_id = ? AND rating != 0
            ORDER BY event_ts DESC
        """, (job_id,)).fetchall()

        # latest event per shot
        shots: Dict[str, Dict] = {}
        for row in rows:
            if row["shot_id"] not in shots:
                shots[row["shot_id"]] = dict(row)

        ups   = [s for s in shots.values() if s["rating"] ==  1]
        downs = [s for s in shots.values() if s["rating"] == -1]

        if not ups or not downs:
            return

        now = time.time()

        # clear existing derived pairs for this job to avoid duplicates
        conn.execute("DELETE FROM pairwise_prefs WHERE job_id = ?", (job_id,))

        pairs: List[Tuple] = []

        # explicit pairs: all (up, down) combinations
        for u in ups:
            for d in downs:
                pairs.append((
                    now, job_id,
                    u["shot_id"], u.get("rank"), u.get("total_score"),
                    d["shot_id"], d.get("rank"), d.get("total_score"),
                    1.0, "explicit",
                ))

        # inversion pairs: up shot ranked BELOW down shot
        for u in ups:
            for d in downs:
                u_rank = u.get("rank") or 9999
                d_rank = d.get("rank") or 9999
                if u_rank > d_rank:   # up ranked worse than down = inversion
                    pairs.append((
                        now, job_id,
                        u["shot_id"], u.get("rank"), u.get("total_score"),
                        d["shot_id"], d.get("rank"), d.get("total_score"),
                        0.7, "inversion",
                    ))

        conn.executemany("""
            INSERT INTO pairwise_prefs (
                derived_ts, job_id,
                winner_shot_id, winner_rank, winner_score,
                loser_shot_id,  loser_rank,  loser_score,
                confidence, pair_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, pairs)

    except Exception as exc:
        print(f"[feedback_store] pairwise derivation failed: {exc}")

# aesthetic/agents/scoring.py
#
# Pillar interaction logic and intent-aware score harmonisation.
#
# The problem with simple weighted averaging:
#   A shot scoring 45 technical / 92 creative / 80 subjective
#   averages to ~66 and loses to a 70/70/70 shot.
#   But the first shot is genuinely excellent cinematography that
#   happens to be technically unconventional. It should win.
#
# The harmony model solves this in three steps:
#
#   Step 1 — Intent-aware category weighting
#   Different shot intents call for different metric emphasis.
#   A handheld intimate close-up should not be penalised for
#   stabilisation. An establishing wide should not be penalised
#   for low face placement score.
#
#   Step 2 — Creative+Subjective alignment bonus
#   When Creative and Subjective both agree a shot is excellent,
#   that consensus overrides a low Technical score up to a cap.
#   The cap prevents intentionally unconventional shots from
#   gaming the system, but rewards genuine excellence.
#
#   Step 3 — Technical floor
#   A shot that is technically catastrophic (severe clipping,
#   camera shake, heavy compression) cannot be rescued by
#   Creative alignment alone. There is a minimum technical floor.
#
# All thresholds are configurable in config.yaml under scoring.

from __future__ import annotations

from typing import Any, Dict, Optional

from ..models.scores import ShotScore, CategoryScore


# ---------------------------------------------------------------------------
# Intent-aware category weights
# ---------------------------------------------------------------------------

# For each shot intent, we adjust which category scores matter most
# when computing the Technical pillar subtotal.
# Values are relative weights — they are normalised internally.
# Categories not listed use the global config weights.

INTENT_CATEGORY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "intimate": {
        # close-up emotional shot: composition and lighting matter most,
        # movement stability less important (some handheld is acceptable)
        "exposure":    1.2,
        "lighting":    1.4,
        "composition": 1.3,
        "movement":    0.6,   # reduced — intentional handheld is fine
        "color":       1.1,
        "quality":     1.0,
        "narrative":   1.2,
    },
    "establishing": {
        # wide shot showing environment: composition and color dominate,
        # movement very important (a shaky wide shot is distracting)
        "exposure":    1.1,
        "lighting":    1.0,
        "composition": 1.4,
        "movement":    1.3,
        "color":       1.3,
        "quality":     1.1,
        "narrative":   0.8,
    },
    "action": {
        # dynamic shot: movement quality is the primary signal,
        # composition less critical (some asymmetry is acceptable)
        "exposure":    1.0,
        "lighting":    0.9,
        "composition": 0.8,   # reduced — dynamic framing is acceptable
        "movement":    1.5,   # elevated — movement is the whole point
        "color":       1.0,
        "quality":     1.1,
        "narrative":   1.0,
    },
    "dialogue": {
        # medium coverage shot: everything matters evenly,
        # slight emphasis on exposure and lighting consistency
        "exposure":    1.2,
        "lighting":    1.2,
        "composition": 1.1,
        "movement":    1.0,
        "color":       1.0,
        "quality":     1.0,
        "narrative":   0.9,
    },
    "transitional": {
        # connective shot: quality and movement smoothness matter,
        # composition less critical
        "exposure":    1.0,
        "lighting":    0.9,
        "composition": 0.8,
        "movement":    1.2,
        "color":       1.1,
        "quality":     1.2,
        "narrative":   0.7,
    },
    "unknown": {
        # no classification — use equal weights
        "exposure":    1.0,
        "lighting":    1.0,
        "composition": 1.0,
        "movement":    1.0,
        "color":       1.0,
        "quality":     1.0,
        "narrative":   1.0,
    },
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_harmonised_score(
    score:      ShotScore,
    shot_intent: str,
    config:     Dict[str, Any],
) -> ShotScore:
    """
    Apply pillar interaction logic to produce the final harmonised total score.

    This replaces the simple weighted average with a model that:
    1. Re-weights Technical category scores based on shot intent
    2. Applies a Creative+Subjective alignment bonus when both pillars agree
    3. Enforces a minimum Technical floor to prevent gaming

    Args:
        score:       ShotScore with technical_total and optionally creative_total.
        shot_intent: Shot intent string from classifier (intimate/establishing/etc.)
        config:      Full config dict.

    Returns:
        Updated ShotScore with harmonised total_score.
    """
    scoring_cfg = config.get("scoring", {})
    weights     = config.get("weights", {})

    w_tech = float(weights.get("technical",  0.50))
    w_creat= float(weights.get("creative",   0.30))
    w_subj = float(weights.get("subjective", 0.20))

    # Step 1 — intent-aware technical score
    intent_tech = _intent_adjusted_technical(score, shot_intent)

    # Step 2 — baseline: weighted average of available pillars
    parts, wts = [], []
    if intent_tech is not None:
        parts.append(intent_tech * w_tech)
        wts.append(w_tech)
    if score.creative_total is not None:
        parts.append(score.creative_total * w_creat)
        wts.append(w_creat)
    if score.subjective_total is not None:
        parts.append(score.subjective_total * w_subj)
        wts.append(w_subj)

    if not wts:
        return score

    baseline_total = sum(parts) / sum(wts)

    # Step 3 — alignment bonus
    # When Creative and Subjective both agree a shot is excellent,
    # apply a bonus that partially overrides a low Technical score
    alignment_bonus_cap = float(scoring_cfg.get("alignment_bonus_cap", 12.0))
    alignment_threshold  = float(scoring_cfg.get("alignment_threshold",  72.0))

    bonus = 0.0
    creative  = score.creative_total
    subjective= score.subjective_total

    if (creative is not None and creative >= alignment_threshold and
        subjective is not None and subjective >= alignment_threshold):
        # both pillars agree this is excellent
        # bonus proportional to how much both exceed the threshold
        creative_excess  = creative   - alignment_threshold
        subjective_excess= subjective - alignment_threshold
        raw_bonus = (creative_excess + subjective_excess) / 2.0 * 0.3
        bonus = min(alignment_bonus_cap, raw_bonus)

    # Step 4 — technical floor
    # Even with a perfect creative alignment, a shot cannot score above
    # floor_cap if its technical score is below technical_floor
    technical_floor = float(scoring_cfg.get("technical_floor",    25.0))
    floor_cap       = float(scoring_cfg.get("technical_floor_cap", 72.0))

    harmonised = baseline_total + bonus

    if intent_tech is not None and intent_tech < technical_floor:
        # catastrophic technical failure — cap the total score
        harmonised = min(harmonised, floor_cap)

    harmonised = round(min(100.0, max(0.0, harmonised)), 2)

    # store the intent-adjusted technical score for transparency
    score.technical_total = round(intent_tech, 2) if intent_tech is not None else score.technical_total
    score.total_score     = harmonised

    return score


# ---------------------------------------------------------------------------
# Step 1 — intent-adjusted technical score
# ---------------------------------------------------------------------------

def _intent_adjusted_technical(
    score:       ShotScore,
    shot_intent: str,
) -> Optional[float]:
    """
    Re-compute the Technical pillar subtotal using intent-specific category weights.

    For example, an intimate close-up has reduced movement weight
    so handheld camera is not a significant penalty.
    An action shot has elevated movement weight so unstable camera
    is penalised more severely.
    """
    intent_key = shot_intent if shot_intent in INTENT_CATEGORY_WEIGHTS else "unknown"
    iw         = INTENT_CATEGORY_WEIGHTS[intent_key]

    category_scores = {
        "exposure":    score.exposure.technical,
        "lighting":    score.lighting.technical,
        "composition": score.composition.technical,
        "movement":    score.movement.technical,
        "color":       score.color.technical,
        "quality":     score.quality.technical,
        "narrative":   score.narrative.technical,
    }

    weighted_sum = 0.0
    weight_sum   = 0.0

    for cat, val in category_scores.items():
        if val is not None:
            w = iw.get(cat, 1.0)
            weighted_sum += val * w
            weight_sum   += w

    if weight_sum == 0:
        return score.technical_total

    return round(weighted_sum / weight_sum, 2)


# ---------------------------------------------------------------------------
# Utility — apply harmonisation to a list of ShotScores
# ---------------------------------------------------------------------------

def harmonise_scores(
    scores:       list,
    classifications: Dict[str, Dict],
    config:       Dict[str, Any],
) -> list:
    """
    Apply harmonised scoring to a list of ShotScore objects.

    Args:
        scores:          List of ShotScore models.
        classifications: Dict of scene_id -> classification dict.
        config:          Full config dict.

    Returns:
        Updated list of ShotScore models with harmonised total scores.
    """
    updated = []
    for score in scores:
        cls    = classifications.get(score.scene_id, {})
        intent = cls.get("shot_intent", "unknown")
        updated.append(compute_harmonised_score(score, intent, config))
    return updated
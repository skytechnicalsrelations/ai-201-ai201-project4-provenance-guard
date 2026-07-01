"""Confidence scorer -- turns two independent signal scores into one verdict.

This is the only place the two signals meet. It implements the spec exactly:

    confidence  = 0.6 * llm_score + 0.4 * stylometric_score      (LLM-weighted)

    likely_human : confidence < 0.35
    uncertain    : 0.35 <= confidence < 0.70
    likely_ai    : confidence >= 0.70

The false-positive hedge lives in the thresholds (AI band starts high at 0.70),
not in the combination. All four numbers come from config so calibration has a
single source of truth.
"""

from dataclasses import dataclass

from config import AI_THRESHOLD, HUMAN_THRESHOLD, LLM_WEIGHT, STYLOMETRIC_WEIGHT


@dataclass
class ScoreResult:
    confidence: float
    attribution: str  # "likely_ai" | "uncertain" | "likely_human"


def combine_confidence(llm_score: float, stylometric_score: float) -> float:
    """Weighted average of the two signals (LLM-weighted)."""
    return LLM_WEIGHT * llm_score + STYLOMETRIC_WEIGHT * stylometric_score


def attribution_band(confidence: float) -> str:
    """Map a confidence (AI-likelihood) to its attribution band."""
    if confidence < HUMAN_THRESHOLD:
        return "likely_human"
    if confidence < AI_THRESHOLD:
        return "uncertain"
    return "likely_ai"


def classify(llm_score: float, stylometric_score: float, is_short: bool = False) -> ScoreResult:
    """Blend both signals into a confidence + attribution band.

    Edge case #3: when `is_short`, the structural signal is unreliable, so we
    refuse to emit a confident verdict -- any band that would have been a
    confident call (`likely_ai`/`likely_human`) is downgraded to `uncertain`.
    The confidence number is left untouched so the raw estimate stays inspectable.
    """
    confidence = combine_confidence(llm_score, stylometric_score)
    attribution = attribution_band(confidence)
    if is_short and attribution != "uncertain":
        attribution = "uncertain"
    return ScoreResult(confidence=round(confidence, 3), attribution=attribution)

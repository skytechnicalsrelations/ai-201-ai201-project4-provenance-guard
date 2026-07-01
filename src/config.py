"""Central configuration for Provenance Guard.

Keeping the model name, log path, and scoring constants in one place mirrors the
reference starter's config.py and means M4/M5 tune numbers here, not in the code.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Groq / LLM (Signal 1) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.3-70b-versatile"

# --- Storage ---
LOG_FILE = "logs/audit.jsonl"

# --- Confidence scoring (wired up in M4; defined here so there is one source of truth) ---
# confidence = LLM_WEIGHT * llm_score + STYLOMETRIC_WEIGHT * stylometric_score
LLM_WEIGHT = 0.6
STYLOMETRIC_WEIGHT = 0.4

# --- Attribution band thresholds (applied in M4) ---
#   confidence < HUMAN_THRESHOLD            -> likely_human
#   HUMAN_THRESHOLD <= confidence < AI_THRESHOLD -> uncertain
#   confidence >= AI_THRESHOLD              -> likely_ai
HUMAN_THRESHOLD = 0.35
AI_THRESHOLD = 0.70

VALID_ATTRIBUTIONS = {"likely_ai", "uncertain", "likely_human"}

# --- Signal 2 normalization bounds (M4 calibration knobs) ---
# Each raw metric is mapped to a 0-1 AI-likelihood. These bounds are the dials
# M4 calibration turns if a reference input lands in the wrong band -- change the
# numbers here, never the scoring formula or the band thresholds above.
#
# Sentence-length variance: AI text is uniform (low std). std >= this => fully human.
VAR_STD_MAX = 8.0
# Type-token ratio: higher TTR (smoothly diverse vocab) trends AI; lower (repetition) trends human.
# Bounds calibrated (M4) to the reference set, whose short texts all cluster at TTR ~0.86-0.90;
# the original 0.40/0.80 bounds saturated every input to 1.0 and discriminated nothing.
# CAVEAT: TTR is length-sensitive -- longer texts have naturally lower TTR, so these
# short-text bounds won't generalize to long essays. Documented limitation for this scope.
TTR_MIN = 0.85  # at/below => human-like (0.0)
TTR_MAX = 0.95  # at/above => AI-like (1.0)
# Punctuation: expressive marks (!, ?, ellipses, dashes, ALL-CAPS) per word.
# More expressive => more human. ratio >= this => fully human.
PUNCT_EXPRESSIVE_MAX = 0.12

# --- Short-input guard (edge case #3) ---
# Below either threshold, variance/TTR are statistical noise, so we refuse to
# emit a confident verdict and bias the result to `uncertain`.
MIN_WORDS = 25
MIN_SENTENCES = 3

# --- Rate limiting (M5) ---
# Default rate limit across all endpoints (per-client, per-day/hour)
RATE_LIMIT_DEFAULT = "200 per day; 50 per hour"
# Specific limit on POST /submit (per-client)
# Prevents Groq API budget abuse from script floods while allowing normal creator usage
RATE_LIMIT_SUBMIT = "10 per minute; 100 per day"

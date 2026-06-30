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

"""Detection signals.

Signal 1 (LLM classifier, this milestone) and Signal 2 (stylometric heuristics,
M4) both take the same raw text and independently produce a 0.0-1.0 AI-likelihood
score. They never consume each other's output -- they only meet at the confidence
scorer -- which is what makes them independent signals rather than a chain.
"""

import json
import re
import statistics
from dataclasses import dataclass

from groq import Groq

from config import (
    GROQ_API_KEY,
    LLM_MODEL,
    MIN_SENTENCES,
    MIN_WORDS,
    PUNCT_EXPRESSIVE_MAX,
    TTR_MAX,
    TTR_MIN,
    VAR_STD_MAX,
)

_client = Groq(api_key=GROQ_API_KEY)


@dataclass
class LLMResult:
    """Output shape of Signal 1.

    llm_score: AI-likelihood in [0.0, 1.0]  (0.0 = clearly human, 1.0 = clearly AI)
    rationale: one-line explanation, stored in the audit log for appeals reviewers
    """

    llm_score: float
    rationale: str


# Neutral result returned when the API call or parsing fails. 0.5 keeps a broken
# call from silently pushing a submission toward either band.
_FALLBACK = LLMResult(llm_score=0.5, rationale="LLM signal unavailable; defaulted to neutral.")

_SYSTEM_PROMPT = (
    "You are a text-provenance analyst. Judge how AI-written a passage reads, based "
    "on holistic, semantic cues: coherence, phrasing, tonal consistency, and the "
    "presence of the bland, hedge-heavy 'assistant voice' (even pacing, balanced "
    "'on one hand / on the other' framing, transition words like 'Furthermore', "
    "and reluctance to take a sharp stance). Human writing carries idiosyncratic "
    "voice, uneven emphasis, opinions, and topic-specific knowledge an LLM smooths "
    "over.\n\n"
    "Return ONLY a JSON object with exactly these keys:\n"
    '  "llm_score": a number from 0.0 to 1.0 (0.0 = clearly human, 1.0 = clearly AI)\n'
    '  "rationale": a single concise sentence explaining the score\n'
    "Do not include any other text."
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def run_llm_signal(text: str) -> LLMResult:
    """Send `text` to Groq and return an LLMResult.

    Uses JSON mode so the model is forced to emit parseable {llm_score, rationale}.
    Any failure (network, malformed JSON, out-of-range score) falls back to a
    neutral 0.5 rather than raising into the request path.
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)  # type: ignore
        score = _clamp01(float(data["llm_score"]))
        rationale = str(data["rationale"]).strip()
        return LLMResult(llm_score=score, rationale=rationale)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return _FALLBACK
    except Exception:
        # Groq SDK / network errors -- keep the request path alive with a neutral score.
        return _FALLBACK


# ---------------------------------------------------------------------------
# Signal 2 -- Stylometric heuristics (pure Python, no network, deterministic)
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_WORD = re.compile(r"[A-Za-z0-9']+")
# Expressive punctuation/markers that trend human (the spec's "bursty" cues).
_EXPRESSIVE = re.compile(r"[!?]|\.\.\.|…|--|—|–")


@dataclass
class StylometricResult:
    """Output shape of Signal 2.

    stylometric_score: AI-likelihood in [0.0, 1.0], the equal-weight mean of the
        three normalized sub-metrics below.
    The sub-metrics and counts are kept for transparency / M4 calibration -- when
    a reference input lands in the wrong band, print these to see which dial to turn.
    is_short: True when the input is too small for variance/TTR to be meaningful
        (edge case #3); the scorer biases these to `uncertain`.
    """

    stylometric_score: float
    norm_sentence_length_variance: float
    norm_type_token_ratio: float
    norm_punctuation: float
    word_count: int
    sentence_count: int
    is_short: bool


def run_stylometric_signal(text: str) -> StylometricResult:
    """Score `text` on three structural properties; higher = more AI-like.

    1. Sentence-length variance -- AI is uniform (low spread)  -> low variance = AI.
    2. Type-token ratio         -- smoothly diverse vocab trends AI; repetition trends human.
    3. Punctuation expressiveness -- even/standard punctuation trends AI; quirky trends human.
    Each is normalized to 0-1 against the bounds in config, then equal-weight averaged.
    """
    words = _WORD.findall(text)
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    word_count = len(words)
    sentence_count = len(sentences)

    # 1. Sentence-length variance (std of words-per-sentence). Needs >=2 sentences.
    sent_word_counts = [len(_WORD.findall(s)) for s in sentences]
    std = statistics.pstdev(sent_word_counts) if len(sent_word_counts) >= 2 else 0.0
    norm_variance = 1.0 - _clamp01(std / VAR_STD_MAX)  # low spread -> AI

    # 2. Type-token ratio (vocabulary diversity).
    ttr = len({w.lower() for w in words}) / word_count if word_count else 0.0
    norm_ttr = _clamp01((ttr - TTR_MIN) / (TTR_MAX - TTR_MIN))  # high TTR -> AI

    # 3. Punctuation expressiveness per word (incl. ALL-CAPS shouting).
    expressive = len(_EXPRESSIVE.findall(text))
    expressive += sum(1 for w in words if len(w) > 1 and w.isupper())
    expressive_ratio = expressive / word_count if word_count else 0.0
    norm_punct = 1.0 - _clamp01(expressive_ratio / PUNCT_EXPRESSIVE_MAX)  # plain -> AI

    stylometric_score = statistics.mean([norm_variance, norm_ttr, norm_punct])
    is_short = word_count < MIN_WORDS or sentence_count < MIN_SENTENCES

    return StylometricResult(
        stylometric_score=stylometric_score,
        norm_sentence_length_variance=norm_variance,
        norm_type_token_ratio=norm_ttr,
        norm_punctuation=norm_punct,
        word_count=word_count,
        sentence_count=sentence_count,
        is_short=is_short,
    )

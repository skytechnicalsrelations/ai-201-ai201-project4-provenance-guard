"""Detection signals.

Signal 1 (LLM classifier, this milestone) and Signal 2 (stylometric heuristics,
M4) both take the same raw text and independently produce a 0.0-1.0 AI-likelihood
score. They never consume each other's output -- they only meet at the confidence
scorer -- which is what makes them independent signals rather than a chain.
"""

import json
from dataclasses import dataclass

from groq import Groq

from config import GROQ_API_KEY, LLM_MODEL

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
_FALLBACK = LLMResult(
    llm_score=0.5, rationale="LLM signal unavailable; defaulted to neutral."
)

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

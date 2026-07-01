# Provenance Guard — AI Content Attribution Backend

**AI201 Project 4**

Provenance Guard is a backend system that any creative-sharing platform can plug into to classify submitted text as human- or AI-written, score confidence in that classification, surface a plain-language transparency label to readers, and handle appeals from creators who believe they've been misclassified. It does not try to "solve" AI detection — it acknowledges uncertainty honestly and gives creators a path to contest a verdict.

---

## Setup

1. Clone this repo locally
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Mac/Linux
   # or: .venv\Scripts\activate       # Windows (Command Prompt)
   ```

3. Install dependencies: `pip install -r requirements.txt`
4. Create a `.env` file in the repo root and add your Groq API key (never commit it):

   ```
   GROQ_API_KEY=your_key_here
   ```

5. Run the app: `python app.py`

---

## What to Implement

| Milestone | Component | Description |
|-----------|-----------|-------------|
| 3 | `POST /submit` + signal 1 (Groq LLM) | ✅ Done — accepts text, runs Signal 1 live, returns structured response |
| 3 | Audit log + `GET /log` | ✅ Done — structured entry per submission; recent entries exposed |
| 4 | Signal 2 (stylometric heuristics) + confidence scoring | ✅ Done — second signal added, combined into one calibrated score |
| 5 | Transparency label | ⏳ Not started — map confidence score to one of three label variants |
| 5 | `POST /appeal` | ⏳ Not started — capture creator reasoning, set status `under_review`, log it |
| 5 | Rate limiting | ⏳ Not started — apply Flask-Limiter to `/submit` with documented limits |

Read `planning.md` (written before implementation) for the full spec, architecture diagram, and AI tool plan.

---

## API Surface

| Endpoint | Method | Accepts | Returns |
|----------|--------|---------|---------|
| `/submit` | POST | `{ "text": ..., "creator_id": ... }` | `content_id`, `attribution`, `confidence`, `label` |
| `/appeal` | POST | `{ "content_id": ..., "creator_id": ..., "creator_reasoning": ... }` | confirmation; status → `under_review` |
| `/appeals` | GET | — | reviewer queue: items `under_review` with original decision + appeal reasoning |
| `/content/<id>` | GET | — | current folded state for one submission (status + decision) |
| `/log` | GET | — | most recent structured audit entries |
| `/docs` | GET | — | interactive Swagger UI for trying the API in a browser |
| `/openapi.json` | GET | — | machine-readable OpenAPI 3 spec backing `/docs` |

Storage is an **append-only JSONL audit log** (`logs/audit.jsonl`) — the log is the source of truth, and a submission's current status is the most recent event for its `content_id`. Full contract and field shapes in [planning.md](planning.md#api-surface).

---

## Architecture Overview

A creator sends their text to **`POST /submit`** with a `text` and `creator_id`. The request first passes the **rate limiter** (Flask-Limiter), which rejects floods with a `429` before any detection runs. The text then enters the **detection pipeline**, which runs two independent signals: **Signal 1**, a Groq LLM classifier (`llama-3.3-70b-versatile`) that judges the text's human-vs-AI "feel" semantically, and **Signal 2**, pure-Python stylometric heuristics (sentence-length variance, type-token ratio, punctuation density) that measure structural uniformity. Both scores flow into the **confidence scorer**, which combines them into one calibrated confidence value and an attribution band (`likely_ai` / `uncertain` / `likely_human`). The **label generator** maps that band to one of three plain-language **transparency label** variants — the text a reader actually sees. Every decision is written to the **audit log** (keyed by a unique `content_id`), and `/submit` returns `content_id`, attribution, confidence, and label.

**Appeal flow:** a creator calls **`POST /appeal`** with their `content_id` and `creator_reasoning`. The endpoint sets that content's status to `under_review`, logs the appeal alongside the original decision so a human reviewer sees both sides, and confirms receipt. **`GET /log`** exposes recent audit entries as JSON. See [planning.md](planning.md) for the full narrative and architecture diagram.

---

## Detection Signals

The pipeline uses two genuinely independent signals: one **semantic**, one **structural**. They fail in different ways, which is why combining them beats either alone. (Full analysis in [planning.md](planning.md#detection-signals).)

### Signal 1 — LLM classifier (Groq, `llama-3.3-70b-versatile`)

- **Measures:** a holistic, semantic read of how human- or AI-written the text *sounds* — coherence, phrasing, the bland hedge-heavy "assistant voice." Returns a `0.0–1.0` AI-likelihood score plus a one-line rationale (the rationale is stored in the audit log for appeals review).
- **Why it differs:** instruction-tuned models converge on recognizable habits — even pacing, balanced framing, transition words ("Furthermore," "It is important to note"), reluctance to take a stance. Human writing carries idiosyncratic voice, uneven emphasis, and topic-specific knowledge the model smooths over.
- **Blind spot:** it's a probabilistic judgment, not proof of provenance, and it's gameable and run-to-run unstable. Lightly edited AI can read as human; a non-native or deliberately formal human can read as AI — the key **false positive**. It captures *plausibility of voice*, not where the text actually came from.

### Signal 2 — Stylometric heuristics (pure Python)

One structural score blended from three measurable properties — deterministic, no model, no network:

1. **Sentence-length variance** — spread of word counts across sentences.
2. **Type-token ratio** — vocabulary diversity (unique words ÷ total).
3. **Punctuation density** — punctuation marks per word, including the variety of marks used.

- **Why it differs:** AI prose trends toward **uniformity** (similar sentence lengths, evenly distributed vocabulary, "correct" even punctuation); human writing is **bursty** (short sentences beside long ones, repetition or narrow vocabulary, expressive punctuation like "…", "—", "!!").
- **Blind spot:** it measures *form, not meaning*. Short inputs are too small for stable statistics, and it misclassifies whole genres — a repetitive, simple-vocabulary poem or a polished human essay both look "uniform" and get flagged AI, while AI prompted to write "casually" can mimic human stylometrics.

**Why this pairing:** one signal is semantic, one is structural — independent where it matters, so Signal 1 can be right about voice when Signal 2 is fooled by form, and vice versa. Their *shared* weakness — both can flag formal or non-native humans as AI — is the false-positive risk the confidence thresholds and appeal path are designed to hedge.

---

## Confidence Scoring

The two signals combine as a fixed, LLM-weighted average:

```
confidence = 0.6 * llm_score + 0.4 * stylometric_score
```

`stylometric_score` is itself an equal-weight average of three normalized 0–1 sub-metrics (sentence-length variance, type-token ratio, punctuation expressiveness — see `scoring.py` / `signals.py`). The combined `confidence` then maps to a band via fixed thresholds (`< 0.35` human, `< 0.70` uncertain, `≥ 0.70` AI) — see [Transparency Label](#transparency-label) below. Uncertainty is represented by where the score sits, not a separate number: `0.667` and `0.95` both round toward "AI" colloquially, but only `0.95` clears the AI threshold — `0.667` stays `uncertain`.

A **short-input guard** (edge case #3) forces the band to `uncertain` whenever the text is under 25 words or 3 sentences — at that size, sentence-variance and TTR are statistical noise, so the system declines to issue a confident verdict regardless of the raw score.

### Calibration (Milestone 4)

The four reference inputs were run through the live pipeline to validate the bands. The first calibration attempt **failed one case**: `type-token ratio` was normalized against bounds (`0.40–0.80`) tuned for long-form text, but all four ~40–55 word reference inputs had a raw TTR of `0.86–0.90` — every input saturated the metric to `1.0`, so it contributed nothing and inflated every score. Re-centering the TTR bounds to `0.85–0.95` (where short-text TTR actually clusters) fixed it without touching the weights or band thresholds, which the spec freezes. Final results:

| Input | Signal 1 (llm) | Signal 2 (stylometric) | Confidence | Attribution |
|-------|:--:|:--:|:--:|------|
| Clear AI | 0.90 | 0.49 | **0.735** | `likely_ai` ✅ |
| Clear human | 0.10 | 0.36 | **0.205** | `likely_human` ✅ |
| Formal human (false-positive test) | 0.80 | 0.47 | **0.669** | `uncertain` ✅ |
| Lightly-edited AI | 0.70 | 0.62 | **0.667** | `uncertain` ✅ |

The critical test — formal human writing — lands `uncertain` at `0.669`, just under the `0.70` AI threshold, by the scoring math itself (not the short-input guard). This is the asymmetry the spec calls for: a real human's measured, formal register doesn't get accused of being AI.

### Do the two signals agree?

Running both signals standalone on the same four inputs shows *where* they diverge — which is more informative than either score alone:

| Input | Signal 1 (llm) | Signal 2 (sty) | Gap | What the divergence says |
|-------|:--:|:--:|:--:|------|
| Clear AI | 0.90 | 0.49 | 0.41 | LLM commits hard; stylometrics only leans, because short text gives it little to measure |
| Clear human | 0.10 | 0.36 | 0.26 | Stylometrics *over-reads* casual writing as somewhat AI-ish; the LLM correctly nails the voice |
| Formal human | 0.80 | 0.47 | 0.33 | Here the **LLM** is the false-positive driver, not stylometrics — and stylometrics *pulls the blend back* toward `uncertain` |
| Lightly-edited AI | 0.70 | 0.62 | 0.08 | Closest agreement; both lean AI |

Two takeaways:

1. **Signal 2 stays compressed (0.36–0.62) — it never commits strongly.** All four reference inputs are short (~40–55 words), exactly where stylometrics is weakest, so it hovers near the middle while Signal 1 ranges 0.10–0.90. This *validates the spec's LLM-weighting* (`0.6/0.4`): the less reliable signal correctly gets less weight.
2. **The signals fail in different directions, which is the whole point.** On casual human writing, stylometrics is the one that leans AI (0.36 vs 0.10). On formal human writing, the LLM is the one that leans AI (0.80 vs 0.47) and stylometrics drags it back. Because neither dominates the same way twice, combining them is more robust than trusting either — and the appeal path covers the case where they're *both* wrong (formal/non-native writing, their shared blind spot).

These agreements/divergences, plus the band and scoring assertions, are checked in `test_signals.py`.

---

## Transparency Label

The label shown to readers is plain-language and non-accusatory, with a band-relative percentage so the number always points *toward* the stated verdict (a "human-written" label never shows a low number). The label varies by confidence band — the exact text each variant displays:

| Variant | Confidence range | Label text (verbatim) |
|---------|------------------|------------------------|
| **High-confidence AI** | `confidence ≥ 0.70` | 🤖 **Likely AI-generated — about {ai_pct}% confidence**<br>Our analysis suggests this text was probably created with significant AI assistance. This is an automated estimate, not a certainty. |
| **High-confidence human** | `confidence < 0.35` | ✍️ **Likely human-written — about {human_pct}% confidence**<br>Our analysis found no strong signs of AI generation in this text. |
| **Uncertain** | `0.35 ≤ confidence < 0.70` | ❔ **Attribution uncertain — about {ai_pct}% likely AI**<br>We couldn't confidently tell whether this was written by a person or AI, so we're not making a call. Treat the result as inconclusive. |

Percentages are filled at response time: `ai_pct = round(confidence × 100)`, `human_pct = round((1 − confidence) × 100)`. The `/submit` response returns the fully-rendered label string with numbers already substituted.

> A false positive (labeling a human's work as AI-generated) is worse than a false negative on a writing platform. The AI band starts high (≥ 0.70) and the AI label hedges ("probably," "an estimate, not a certainty") to reflect that asymmetry.

---

## Appeals Workflow

The appeal path is for the error that matters most: a human creator labeled (or leaned) AI. It routes a contested decision to a human — there is **no automated re-classification**.

- **Who:** the original creator only. The appeal includes `creator_id`, checked against the original submission's `creator_id` (`403` on mismatch). With no real auth here, this is a light ownership check, not a security boundary.
- **What they provide:** `content_id`, `creator_id`, and free-text `creator_reasoning`.
- **What the system does:** looks up the content (`404` if unknown), verifies ownership (`403`), rejects a second appeal (`409` — one appeal per content), then appends an `under_review` event to the audit log carrying the appeal reasoning. The original `classified` event is never overwritten, so the full history survives. No score is recomputed.
- **What a reviewer sees:** `GET /appeals` returns the queue of everything `under_review`, each entry placing the original machine decision (attribution, confidence, both signal scores, LLM rationale) **side-by-side** with the creator's reasoning and both timestamps.

---

## Rate Limiting

<!-- The limits you chose and your specific reasoning. Include the 429 evidence
     from the rapid-fire test. -->

**Limits:** _TODO (e.g. `10 per minute; 100 per day`)_

**Reasoning:** _TODO: realistic creator usage vs. abuse prevention._

**Evidence (12 rapid requests):**

```
TODO: paste status-code output — 200 × 10 then 429 × 2
```

---

## Audit Log

Four entries from `GET /log`, one per Milestone 4 reference input (appeal entry to be added in Milestone 5):

```json
{
  "content_id": "028d8d25-2af4-4cea-9949-5f42544b5558",
  "creator_id": "creator-ai-demo",
  "timestamp": "2026-06-30T23:53:23.814045+00:00",
  "event": "classified",
  "status": "classified",
  "llm_score": 0.9,
  "llm_rationale": "The passage exhibits a balanced and hedged tone, typical of AI-generated text, with transitional phrases like 'Furthermore' and a reluctance to take a sharp stance.",
  "stylometric_score": 0.488,
  "confidence": 0.735,
  "attribution": "likely_ai"
}
{
  "content_id": "0b6f10d1-8d90-4338-812c-d414cdd3dfbc",
  "creator_id": "creator-human-demo",
  "timestamp": "2026-06-30T23:53:24.221419+00:00",
  "event": "classified",
  "status": "classified",
  "llm_score": 0.1,
  "llm_rationale": "The passage has an informal tone, uses colloquial expressions, and expresses a clear personal opinion, indicating a human-written text.",
  "stylometric_score": 0.361,
  "confidence": 0.205,
  "attribution": "likely_human"
}
{
  "content_id": "c3766511-894f-4e8c-8606-412b5f23fc30",
  "creator_id": "creator-formal-demo",
  "timestamp": "2026-06-30T23:53:24.549945+00:00",
  "event": "classified",
  "status": "classified",
  "llm_score": 0.8,
  "llm_rationale": "The passage exhibits a formal and balanced tone, typical of AI-generated content, with a lack of personal opinion or unique perspective.",
  "stylometric_score": 0.472,
  "confidence": 0.669,
  "attribution": "uncertain"
}
{
  "content_id": "1e125230-452e-48eb-8ae9-35290d7b1d3e",
  "creator_id": "creator-edited-demo",
  "timestamp": "2026-06-30T23:53:24.995350+00:00",
  "event": "classified",
  "status": "classified",
  "llm_score": 0.7,
  "llm_rationale": "The passage exhibits a balanced and neutral tone, with a structured 'on one hand / on the other' framing, which is characteristic of AI-generated text.",
  "stylometric_score": 0.618,
  "confidence": 0.667,
  "attribution": "uncertain"
}
```

---

## Known Limitations

**Repetitive, simple-vocabulary poetry.** A villanelle or refrain-heavy poem has low sentence-length variance, low type-token ratio, and even punctuation by design — all three stylometric sub-metrics read "AI" for reasons that have nothing to do with provenance. Signal 1 may rescue it if it recognizes the craft, but if it doesn't, a genuine poem can land in `uncertain` or worse. This is Signal 2's "form, not meaning" blind spot.

**Formal or non-native-English human writing.** This is the *shared* blind spot: both signals read measured, hedge-heavy, uniformly-polished prose as "AI." The LLM-weighted average can't rescue this case because the signals agree with each other, not because either is wrong on its own. It's the entire reason the `likely_ai` band starts at `0.70` rather than `0.5`, and why the appeal path exists.

**Type-token ratio is length-sensitive.** The TTR normalization bounds (`0.85–0.95`) were calibrated against the ~40–55 word reference inputs, where TTR naturally clusters high. A long, multi-paragraph essay has a structurally lower TTR regardless of who wrote it (more words means more repeated function words), so the same bounds would likely under-score a long human essay's "AI-ness" on this sub-metric and over-score a long AI essay's "human-ness." A length-normalized measure (e.g. MTLD, or TTR computed over a fixed sliding window) would generalize better — out of scope for this project's calibration set.

**Very short submissions (haiku, micro-posts).** Under 25 words or 3 sentences, sentence-variance and TTR are statistical noise rather than signal. Mitigated by a hard guard: short inputs are always forced to `uncertain` regardless of the raw score, rather than reporting a confident verdict built on noise.

---

## Spec Reflection

**Where the spec helped directly:** `planning.md`'s exact formula (`confidence = 0.6*llm + 0.4*stylometric`) and fixed thresholds (`0.35` / `0.70`) meant there was never ambiguity about *what* to implement in `scoring.py` — only about getting the inputs to those formulas right. Having the four reference inputs with their *expected* bands pre-written (not just "test it") is what surfaced the TTR-saturation bug — without a concrete "formal-human must not exceed 0.70" assertion to check against, a plausible-but-wrong normalization would have shipped silently.

**Where implementation diverged from the spec:** `planning.md` calls the `0.6/0.4` weights and the stylometric sub-metric weighting "initial values, calibrated in Milestone 4." In practice, M4 calibration never touched the weights or thresholds — they were correct as written. The actual divergence was one level deeper: the **per-metric normalization bounds** (not mentioned as a specific number in the spec) needed adjustment, because TTR's hard-coded `0.40–0.80` range assumed longer text than the reference inputs actually contain. The spec anticipated *that* calibration would be needed; it just turned out to live in the normalization layer rather than the weights.

---

## AI Usage

**Instance 1 — Signal 1 (Groq LLM classifier).** Directed the AI to generate `run_llm_signal()` from the `## Detection Signals` (Signal 1) and `## API Surface` sections of `planning.md`, specifying JSON-mode output and a typed `LLMResult` dataclass. The first draft was used close to as-generated, but I required two things the spec demanded that a default implementation wouldn't include on its own: a clamped `0.0–1.0` score (`_clamp01`) and a neutral `0.5` fallback on any parse/network failure, so a broken Groq call can't silently bias a verdict toward either band.

**Instance 2 — Signal 2 + confidence scoring (this milestone).** Directed the AI to generate `run_stylometric_signal()` and the scoring/threshold logic from the `## Detection Signals` (Signal 2), `## Confidence Scoring`, and `## Uncertainty Representation` sections. Per the spec's own M4 verification plan, I checked the generated thresholds against the spec **exactly** (asserted `0.6/0.4` weights and `0.35`/`0.70` bounds in code, not by eye) and ran the four reference inputs end-to-end. This caught a real bug the AI introduced silently: the generated TTR normalization bounds (`0.40–0.80`) saturated every reference input to `1.0`, since real short-text TTR sits at `0.86–0.90` — the metric was contributing nothing while inflating every score. I revised the bounds to `0.85–0.95` based on the actual measured values, documented the length-sensitivity caveat in `config.py`, and re-ran the calibration set to confirm all four inputs land in their intuitive bands before wiring it into `/submit`.

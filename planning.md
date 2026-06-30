# Provenance Guard — Planning

## Architecture Narrative

This is the plain-English path a single piece of text takes from the moment a creator submits it to the transparency label a reader eventually sees, naming every component it touches and what each one does.

A creator (or the platform acting on their behalf) sends their text to the **`POST /submit` endpoint**, the system's front door. The request carries the raw `text` and a `creator_id`. Before any work happens, the request passes through the **rate limiter** (Flask-Limiter), which checks how many submissions this client has made recently. If they're over the limit, the request is rejected with a `429` and never reaches the detection pipeline; this protects the system from a script flooding it and protects the Groq budget from abuse.

Once past the limiter, the endpoint hands the text to the **detection pipeline**, which runs two independent signals:

1. **Signal 1 — LLM classifier (Groq, `llama-3.3-70b-versatile`).** The text is sent to the Groq API with a prompt that asks the model to assess how human- or AI-written the text reads. This captures holistic, semantic cues — coherence, phrasing, the "feel" of the prose — and returns a score (roughly 0 = human, 1 = AI).
2. **Signal 2 — Stylometric heuristics (pure Python).** The same text is analyzed locally for measurable structural properties (e.g. sentence-length variance, type-token ratio, punctuation density). AI text tends to be more uniform; human writing is more variable. This produces its own score from the math alone — no network call, no model.

Both scores flow into the **confidence scorer**, the component that turns two separate signals into one number. It combines them according to the weighting defined in this spec and produces a single **calibrated confidence score** plus an **attribution verdict** in one of three bands: `likely_ai`, `uncertain`, or `likely_human`. This is where uncertainty is represented honestly — a score near the middle stays "uncertain" rather than being forced into a binary AI/human flip.

The confidence score is then passed to the **label generator**, which maps the score's band to one of three pre-written **transparency label** variants (high-confidence AI, high-confidence human, uncertain). This is the plain-language text a non-technical reader would actually see on the platform. The thresholds are deliberately cautious about calling a human's work AI, because a false positive is the most damaging outcome on a writing platform.

Before the response goes back, every decision is written to the **audit log** (structured JSON / SQLite). The entry records the `content_id` (a unique ID minted for this submission), `creator_id`, timestamp, attribution verdict, the combined confidence, both individual signal scores, and a `status` of `classified`. The `content_id` is the thread that ties everything together later — appeals reference it, and the log is keyed on it.

Finally, the **`/submit` endpoint** returns a structured JSON response to the caller containing the `content_id`, attribution result, confidence score, and the transparency label text. That label text is the end of the submission journey — it's what the reader sees.

**Appeal flow.** If a creator believes they were misclassified, they call the **`POST /appeal` endpoint** with the `content_id` from their original response and their `creator_reasoning`. The endpoint looks up the original decision, updates that content's **status** to `under_review`, and writes a new **audit log** entry capturing the appeal reasoning alongside the original classification — so a human reviewer opening the appeal queue sees both the machine's verdict and the creator's side. It returns a confirmation that the appeal was received. (Automated re-classification is intentionally out of scope; the appeal routes a contested case to a human.)

**`GET /log`** exposes the most recent audit entries as JSON, so the full history of classifications and appeals is inspectable.

## Architecture

Two flows. **Submission** (top): raw text enters `/submit`, passes the rate limiter, runs through both detection signals, gets combined into a calibrated confidence score, mapped to a transparency label, written to the audit log, and returned to the caller. **Appeal** (bottom): a creator references the `content_id` from their submission, the system appends an `under_review` event to the same audit log, and confirms receipt. Each arrow is labeled with what passes between components.

```
SUBMISSION FLOW
  1. Creator
        | raw text + creator_id
        v
  2. POST /submit
        | check client quota
        v
  3. Rate limiter (Flask-Limiter)  -> 429 Too Many Requests if over limit
        | raw text (fan-out to both signals)
        v
  4. Signal 1: Groq LLM classifier  -> llm_score 0-1 + one-line rationale
     Signal 2: Stylometric heuristics -> stylometric_score 0-1
        | both scores
        v
  5. Confidence scorer              -> combined confidence 0-1 + attribution band
        | confidence + attribution
        v
  6. Label generator               -> transparency label text
        | label text + confidence + scores
        v
  7. Audit log (logs/audit.jsonl)  -> writes 'classified' event
        |
        v
  8. Response  -> content_id, attribution, confidence, label

APPEAL FLOW
  1. Creator
        | content_id + creator_reasoning
        v
  2. POST /appeal                  -> 404 if content_id unknown
        | append event
        v
  3. Audit log (logs/audit.jsonl)  -> appends 'under_review' event + appeal_reasoning
        | status now under_review
        v
  4. Response  -> content_id, status=under_review, confirmation message
```

> Note the fan-out at step 4: the rate limiter passes the same raw text to **both** signals independently — Signal 2 does not consume Signal 1's output. They run separately (one semantic, one structural) and only meet at the confidence scorer, which is what makes them independent signals rather than a chain.

### Components at a glance

| Component | Responsibility |
|-----------|----------------|
| `POST /submit` endpoint | Front door; accepts text + creator_id, orchestrates the pipeline, returns the response |
| Rate limiter (Flask-Limiter) | Throttles submissions per client; rejects floods with `429` before any detection runs |
| Signal 1 — Groq LLM classifier | Semantic/holistic human-vs-AI assessment → score |
| Signal 2 — Stylometric heuristics | Structural/statistical text properties → score (pure Python) |
| Confidence scorer | Combines both signal scores into one calibrated confidence + attribution band |
| Label generator | Maps confidence band → one of three transparency label variants |
| Audit log (JSON/SQLite) | Records every classification and appeal as a structured entry, keyed by content_id |
| `POST /appeal` endpoint | Sets status → `under_review`, logs appeal alongside original decision |
| `GET /log` endpoint | Surfaces recent audit entries as JSON |

## Detection Signals

The pipeline uses two genuinely independent signals: one **semantic** (an LLM reads the text the way a person would) and one **structural** (math over the text's surface statistics). They fail in different ways, which is exactly why combining them is more informative than either alone.

### Signal 1 — LLM classifier (Groq, `llama-3.3-70b-versatile`)

- **What it measures.** A holistic, semantic judgment of how human- or AI-written the text *reads* — coherence, phrasing, tonal consistency, the presence of the bland, hedge-heavy "assistant voice." The text is sent to Groq with a prompt that asks for a `0.0–1.0` AI-likelihood score (0 = clearly human, 1 = clearly AI) **plus a one-line rationale**. The score feeds the confidence scorer; the rationale is stored in the audit log so a human appeals reviewer can see *why* the model decided what it did.
- **Why the property differs between human and AI.** Models trained on instruction-following converge on recognizable habits: even pacing, balanced "on one hand / on the other hand" framing, transition words ("Furthermore," "It is important to note"), and a reluctance to take a sharp stance. Human writing carries idiosyncratic voice, uneven emphasis, opinions, and topic-specific knowledge an LLM tends to smooth over. The model has internalized these patterns from vast text, so it can pick up on the *gestalt* that no single hand-coded rule captures.
- **Blind spot.** It is a probabilistic judgment, not a detector, and it is gameable and unstable: lightly edited AI text (the "I've been thinking about remote work" case) can read as human, while a non-native English speaker or a deliberately formal human can read as AI — the classic **false positive**. It can also be inconsistent run-to-run (temperature, prompt sensitivity), it has no ground truth, and it can be defeated by anyone who prompts an LLM to "write casually." It captures *plausibility of voice*, not provenance.

### Signal 2 — Stylometric heuristics (pure Python)

A single structural score combined from three measurable properties. No model, no network — just arithmetic over the text, which makes it deterministic and independent of Signal 1.

- **What it measures.**
  1. **Sentence-length variance** — the spread (standard deviation / variance) of word counts across sentences.
  2. **Type-token ratio (TTR)** — vocabulary diversity: unique words ÷ total words.
  3. **Punctuation density** — punctuation marks per word (or per sentence), including the *variety* of marks used.
  These three are normalized and blended into one `0.0–1.0` AI-likelihood score.
- **Why the property differs between human and AI.** AI prose tends toward **uniformity**: sentences cluster around a similar length, vocabulary is broad but evenly distributed, and punctuation is "correct" and even. Human writing is **bursty and variable**: short punchy sentences next to long ones (high variance), repetition or narrow vocabulary in casual writing (lower TTR), and expressive punctuation — ellipses, dashes, "!!", ALL CAPS, missing periods. So low variance + even punctuation + smoothly diverse vocabulary trends "AI"; high variance + quirky punctuation trends "human."
- **Blind spot.** It measures *form, not meaning*, so it is fooled by form that doesn't match its assumptions. Short inputs (a few sentences) have too little data for variance/TTR to be stable — the numbers are noisy. It **misclassifies whole genres**: a repetitive, simple-vocabulary poem or a terse listicle looks "uniform" → flagged AI (false positive); a long, polished, carefully-edited human essay also looks uniform → flagged AI; conversely, AI text prompted to be "casual and varied" can mimic human stylometrics. It has zero understanding of whether the content is coherent or true — only how it's shaped.

### Why this pairing

The two signals are independent along the axis that matters: Signal 1 can be right about *voice* when Signal 2 is fooled by *form* (e.g., a varied-but-AI-voiced paragraph), and Signal 2 stays stable when Signal 1 wobbles run-to-run. Their **shared** weakness — both can flag a formal or non-native human as AI — is the false-positive risk the confidence scoring and label thresholds are designed to hedge against, and the appeal path exists precisely for when they're both wrong.

## Confidence Scoring

### What the score means
The system produces **one** combined score: `confidence` ∈ `[0, 1]`, interpreted as **AI-likelihood** (P the text is AI-generated).

- `0.0` → reads as clearly human
- `~0.5` → genuinely uncertain (the signals don't agree, or both are weak)
- `1.0` → reads as clearly AI

There is no separate "certainty" number — uncertainty is represented by the score sitting near the middle, which is what makes a `0.51` produce a different label than a `0.95`.

### How the two signals combine
A weighted average, **LLM-weighted** because the semantic signal is more reliable than the structural one (which misclassifies whole genres):

```
confidence = 0.6 * llm_score + 0.4 * stylometric_score
```

These weights are **initial values, calibrated in Milestone 4** against the four reference inputs (clear-AI, clear-human, formal-human, lightly-edited-AI). If a clearly-human input scores too high, the stylometric weight comes down.

### How the three stylometric metrics roll up
Each metric is normalized to `0–1` (higher = more AI-like), then **equal-weight averaged** into `stylometric_score`:

```
stylometric_score = mean(norm_sentence_length_variance,
                         norm_type_token_ratio,
                         norm_punctuation_density)
```

Equal weighting keeps it transparent and easy to document; per-metric weighting is a possible M4 refinement if one metric proves noisy.

### False-positive asymmetry → lives in the thresholds
We chose LLM-weighted averaging rather than disagreement-aware blending, so the hedge against the worst error (calling a human's work AI) is **not** in the combination — it is in **where the band thresholds sit** (below).

## Uncertainty Representation

### What a given score means
The thresholds turn the continuous `confidence` (AI-likelihood) into three attribution bands:

```
0.0          0.35              0.70          1.0
 |--HUMAN-----|----UNCERTAIN----|-----AI------|

likely_human : confidence < 0.35
uncertain    : 0.35 <= confidence < 0.70
likely_ai    : confidence >= 0.70
```

- **`0.6` → `uncertain`.** It sits in the *upper* part of the uncertain band: the text leans AI, but the system is **not confident enough to accuse**. The label says "we're not sure," not "this is AI." This is the deliberate consequence of the false-positive asymmetry.
- The **uncertain band is wide (0.35–0.70)** on purpose. The "likely AI" band starts *high* (`≥ 0.70`) so the system is reluctant to call a human's work AI; the cost of a false "uncertain" (mild) is far lower than a false "likely AI" (damaging to a real creator).
- The bands are **not symmetric around 0.5** — there is no clean midpoint flip. That is what makes a `0.51` ("uncertain") read very differently to a user than a `0.95` ("likely AI").

### How raw outputs become a calibrated score
1. Each stylometric metric is normalized to `0–1` (higher = more AI-like) and equal-weight averaged → `stylometric_score`.
2. `confidence = 0.6 * llm_score + 0.4 * stylometric_score`.
3. **Empirical calibration (Milestone 4):** run the four reference inputs (clear-AI, clear-human, formal-human, lightly-edited-AI) through the pipeline and confirm each lands in its intuitively-correct band. If not, adjust the signal weights and/or the stylometric normalization bounds — *not* the prose — until the scores match intuition, and document the adjustment. The thresholds above stay fixed; calibration moves the scores, not the bands.

## Transparency Label Design

Plain-language, non-accusatory tone, with a percentage so the reader has a sense of strength without raw jargon. The label varies by attribution band. Tone deliberately hedges the AI verdict (it's the damaging one).

**Percentage shown is band-relative** so the number always points *toward the stated verdict*:
- `likely_ai` → `ai_pct = round(confidence * 100)`
- `likely_human` → `human_pct = round((1 - confidence) * 100)` (a reader should never see a low number next to "human-written")
- `uncertain` → `ai_pct = round(confidence * 100)`, framed as a lean, not a call (lands 35–69%)

### The three variants (exact text)

**High-confidence AI** (`confidence >= 0.70`):
> 🤖 **Likely AI-generated — about {ai_pct}% confidence**
> Our analysis suggests this text was probably created with significant AI assistance. This is an automated estimate, not a certainty.

**High-confidence human** (`confidence < 0.35`):
> ✍️ **Likely human-written — about {human_pct}% confidence**
> Our analysis found no strong signs of AI generation in this text.

**Uncertain** (`0.35 <= confidence < 0.70`):
> ❔ **Attribution uncertain — about {ai_pct}% likely AI**
> We couldn't confidently tell whether this was written by a person or AI, so we're not making a call. Treat the result as inconclusive.

`{ai_pct}` / `{human_pct}` are filled at response time from the computed `confidence`. The label string returned by `/submit` is the fully-rendered text (numbers already substituted).

## Storage

**Backend: append-only JSONL audit log** (`logs/audit.jsonl`). Each line is one structured event. There is no separate database — the log *is* the source of truth.

- A `/submit` writes one `classified` event.
- An `/appeal` appends one `under_review` event referencing the same `content_id`.
- **The current status / decision for a `content_id` is the most recent event for it** ("latest event wins"). Status is *derived* by folding the log, not stored as a mutable field. Any reader (`GET /content/<id>`, the appeal lookup) must apply this rule consistently.

This keeps the log immutable and auditable (you can see the full history of a contested decision) at the cost of having to reduce events to get "current state." Acceptable for this project's scale; a production system would likely move to SQLite for indexed lookups.

## API Surface

The contract every other component implements. Three required endpoints plus one convenience lookup.

### `POST /submit`
Accepts a piece of text for attribution analysis; runs the full pipeline.

```jsonc
// request
{ "text": "string (required)", "creator_id": "string (required)" }

// 200 response  (lean — internal scores live in the audit log, not here)
{
  "content_id":  "uuid string",
  "attribution": "likely_ai | uncertain | likely_human",
  "confidence":  0.0,            // float 0–1
  "label":       "transparency label text shown to readers"
}
```
Errors: `400` missing `text`/`creator_id`; `429` rate limit exceeded.

### `POST /appeal`
Lets a creator contest a classification. Appends an `under_review` event for the content.

```jsonc
// request
{ "content_id": "string (required)", "creator_reasoning": "string (required)" }

// 200 response
{ "content_id": "...", "status": "under_review", "message": "Appeal received; the content is now under review." }
```
Errors: `400` missing fields; `404` unknown `content_id`.

### `GET /content/<content_id>`
Convenience lookup of a single submission's current (folded) state. Not required by the rubric; useful for testing appeals.

```jsonc
// 200 response
{
  "content_id":  "...",
  "creator_id":  "...",
  "attribution": "likely_ai | uncertain | likely_human",
  "confidence":  0.0,
  "status":      "classified | under_review"   // latest event wins
}
```
Errors: `404` unknown `content_id`.

### `GET /log`
Returns recent audit entries as JSON (for documentation / grading visibility; would require auth in production).

```jsonc
// optional query: ?limit=N
{
  "entries": [
    {
      "content_id":        "...",
      "creator_id":        "...",
      "timestamp":         "ISO-8601 UTC",
      "event":             "classified | under_review",
      "attribution":       "likely_ai | uncertain | likely_human",
      "confidence":        0.0,
      "llm_score":         0.0,         // signal 1
      "stylometric_score": 0.0,         // signal 2
      "llm_rationale":     "one-line model rationale",
      "appeal_reasoning":  "present only on under_review events",
      "status":            "classified | under_review"
    }
  ]
}
```

### Rate limiting
Applied to `POST /submit` only (Flask-Limiter). Specific limits and reasoning decided in Milestone 5.

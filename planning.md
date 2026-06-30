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

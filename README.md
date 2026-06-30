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
| 3 | `POST /submit` + signal 1 (Groq LLM) | Accept text, run first detection signal, return structured response |
| 3 | Audit log + `GET /log` | Write a structured entry per submission; expose recent entries |
| 4 | Signal 2 (stylometric heuristics) + confidence scoring | Add second signal, combine into one calibrated score |
| 5 | Transparency label | Map confidence score to one of three label variants |
| 5 | `POST /appeal` | Capture creator reasoning, set status `under_review`, log it |
| 5 | Rate limiting | Apply Flask-Limiter to `/submit` with documented limits |

Read `planning.md` (written before implementation) for the full spec, architecture diagram, and AI tool plan.

---

## API Surface

| Endpoint | Method | Accepts | Returns |
|----------|--------|---------|---------|
| `/submit` | POST | `{ "text": ..., "creator_id": ... }` | `content_id`, `attribution`, `confidence`, `label` |
| `/appeal` | POST | `{ "content_id": ..., "creator_reasoning": ... }` | confirmation; status → `under_review` |
| `/content/<id>` | GET | — | current folded state for one submission (status + decision) |
| `/log` | GET | — | most recent structured audit entries |

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

<!-- How you combined the two signals into one score, how you validated it's
     meaningful, and how you handle uncertainty (0.51 vs 0.95 must differ). -->

_TODO: explain the combination/weighting and calibration approach._

**Example submissions** (from Milestone 4 testing):

| Input | Signal 1 | Signal 2 | Confidence | Label |
|-------|----------|----------|------------|-------|
| _High-confidence case_ | — | — | — | — |
| _Lower-confidence case_ | — | — | — | — |

---

## Transparency Label

<!-- The exact verbatim text shown to a reader for each of the three variants. -->

| Variant | Confidence range | Label text |
|---------|------------------|------------|
| High-confidence AI | _TODO_ | _TODO: verbatim text_ |
| High-confidence human | _TODO_ | _TODO: verbatim text_ |
| Uncertain | _TODO_ | _TODO: verbatim text_ |

> A false positive (labeling a human's work as AI-generated) is worse than a false negative on a writing platform — the labels and thresholds are designed to reflect that asymmetry.

---

## Appeals Workflow

<!-- Who can appeal, what they provide, what the system does (status change +
     logging), and what a human reviewer sees in the appeal queue. -->

_TODO: describe the appeal flow and what gets logged._

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

<!-- At least 3 structured entries: timestamp, content_id, attribution,
     confidence, both signal scores, status / appeal. -->

```json
TODO: paste at least 3 entries from GET /log, including one appeal
```

---

## Known Limitations

<!-- At least one specific content type your system would likely misclassify,
     tied to a property of your signals — not a generic "needs more data." -->

_TODO: e.g. a repetitive, simple-vocabulary poem that stylometrics may flag as AI._

---

## Spec Reflection

_TODO: one way planning.md helped guide implementation, and one way the implementation diverged from it and why._

---

## AI Usage

_TODO: at least 2 specific instances — what you directed the AI to do, what it produced, and what you revised or overrode._

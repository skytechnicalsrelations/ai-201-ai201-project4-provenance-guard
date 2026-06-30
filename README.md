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
| `/log` | GET | — | most recent structured audit entries |

---

## Architecture Overview

<!-- The path a submission takes from input to transparency label.
     POST /submit → signal 1 (Groq) → signal 2 (stylometrics) → confidence
     scoring → transparency label → audit log → response.
     See planning.md for the full diagram. -->

_TODO: describe the submission and appeal flows end-to-end._

---

## Detection Signals

<!-- For each signal: what property it measures, why that property differs
     between human and AI writing, and what it can't capture (its blind spot). -->

1. **LLM-based classification (Groq, `llama-3.3-70b-versatile`)** — _TODO: what it captures (semantic/stylistic coherence) and its blind spot._
2. **Stylometric heuristics (pure Python)** — _TODO: which metrics (sentence-length variance, type-token ratio, punctuation density), why they differ, and the blind spot._

_Why this pairing: one signal is semantic, one is structural — genuinely independent, so the combination is more informative than either alone._

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

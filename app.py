"""Provenance Guard -- Flask API.

M3 scope: the POST /submit front door runs Signal 1 (LLM classifier) live and
writes a `classified` event to the audit log; GET /log surfaces recent events.
Confidence, attribution band, and the transparency label are M4/M5 work and are
returned as explicit `None` placeholders so the response shape is honest about
what is not computed yet.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from auditor import AuditEvent, append_event, read_events
from signals import run_llm_signal

app = Flask(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/submit")
def submit():
    """Accept text for attribution analysis and run the detection pipeline.

    M3: Signal 1 is live; confidence/attribution/label are placeholders.
    """
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    creator_id = body.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "Both 'text' and 'creator_id' are required."}), 400

    content_id = str(uuid.uuid4())

    # --- Signal 1 (live) ---
    llm = run_llm_signal(text)

    # --- M4/M5 placeholders (not yet computed) ---
    confidence = None
    attribution = None
    label = "(transparency label generated in M5)"

    append_event(
        AuditEvent(
            content_id=content_id,
            creator_id=creator_id,
            timestamp=_utc_now(),
            event="classified",
            status="classified",
            llm_score=llm.llm_score,
            llm_rationale=llm.rationale,
            # stylometric_score / confidence / attribution filled in M4
        )
    )

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
        }
    )


@app.get("/log")
def get_log():
    """Return recent audit entries as JSON. Optional ?limit=N."""
    limit = request.args.get("limit", type=int)
    return jsonify({"entries": read_events(limit=limit)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)

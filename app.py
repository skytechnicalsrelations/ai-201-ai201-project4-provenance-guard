"""Provenance Guard -- Flask API.

M3 scope: the POST /submit front door runs Signal 1 (LLM classifier) live and
writes a `classified` event to the audit log; GET /log surfaces recent events.
Confidence, attribution band, and the transparency label are M4/M5 work and are
returned as explicit `None` placeholders so the response shape is honest about
what is not computed yet.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request

from apidocs import OPENAPI_SPEC, SWAGGER_HTML
from auditor import AuditEvent, append_event, read_events
from config import AI_THRESHOLD, HUMAN_THRESHOLD
from signals import run_llm_signal

app = Flask(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attribution_band(score: float) -> str:
    """Map a 0-1 AI-likelihood score to an attribution band.

    M3: fed the Signal 1 score alone (provisional). M4 feeds the blended
    confidence here instead; the thresholds themselves stay fixed.
    """
    if score < HUMAN_THRESHOLD:
        return "likely_human"
    if score < AI_THRESHOLD:
        return "uncertain"
    return "likely_ai"


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

    # --- Provisional results from Signal 1 only ---
    # M4 replaces `confidence` with the blended 0.6*llm + 0.4*stylometric score;
    # the band mapping and the label text (M5) stay placeholders until then.
    confidence = round(llm.llm_score, 3)
    attribution = _attribution_band(confidence)
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
            confidence=confidence,
            attribution=attribution,
            # stylometric_score filled in M4
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


@app.get("/openapi.json")
def openapi_spec():
    """Machine-readable OpenAPI 3 spec consumed by the Swagger UI page."""
    return jsonify(OPENAPI_SPEC)


@app.get("/docs")
def docs():
    """Interactive Swagger UI for trying the API in the browser."""
    return Response(SWAGGER_HTML, mimetype="text/html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)

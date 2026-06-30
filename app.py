"""Provenance Guard -- Flask API.

POST /submit runs both detection signals (Signal 1 LLM classifier + Signal 2
stylometric heuristics), blends them into a calibrated confidence + attribution
band, and writes a `classified` event to the audit log. GET /log surfaces recent
events. The transparency label is M5 work and stays a placeholder for now.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request

from apidocs import OPENAPI_SPEC, SWAGGER_HTML
from auditor import AuditEvent, append_event, read_events
from scoring import classify
from signals import run_llm_signal, run_stylometric_signal

app = Flask(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/submit")
def submit():
    """Accept text for attribution analysis and run the detection pipeline.

    Signals 1 + 2 are live and combined; the transparency label is an M5 placeholder.
    """
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    creator_id = body.get("creator_id")

    if not text or not creator_id:
        return jsonify({"error": "Both 'text' and 'creator_id' are required."}), 400

    content_id = str(uuid.uuid4())

    # --- Detection pipeline: two independent signals, fanned out from the same text ---
    llm = run_llm_signal(text)  # Signal 1 (semantic)
    sty = run_stylometric_signal(text)  # Signal 2 (structural)

    # --- Confidence scorer: 0.6*llm + 0.4*stylometric, with the short-input guard ---
    score = classify(llm.llm_score, sty.stylometric_score, is_short=sty.is_short)
    confidence = score.confidence
    attribution = score.attribution
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
            stylometric_score=round(sty.stylometric_score, 3),
            confidence=confidence,
            attribution=attribution,
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

"""Provenance Guard -- Flask API.

POST /submit runs both detection signals (Signal 1 LLM classifier + Signal 2
stylometric heuristics), blends them into a calibrated confidence + attribution
band, and writes a `classified` event to the audit log. Rate-limited to 10 per
minute, 100 per day. GET /log surfaces recent events. POST /appeal files appeals
(checked against original creator_id, one appeal per content). GET /appeals
returns the queue of content under_review with original decision and reasoning.
GET /content/<content_id> returns a single submission's current state.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from apidocs import OPENAPI_SPEC, SWAGGER_HTML
from auditor import AuditEvent, append_event, read_events
from config import RATE_LIMIT_DEFAULT, RATE_LIMIT_SUBMIT
from labels import generate_label
from scoring import classify
from signals import run_llm_signal, run_stylometric_signal

app = Flask(__name__)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/submit")
@limiter.limit(RATE_LIMIT_SUBMIT)
def submit():
    """Accept text for attribution analysis and run the detection pipeline.

    Signals 1 + 2 are live and combined; returns confidence score, attribution
    band, and generated transparency label (M5). Rate-limited per client.
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
    label = generate_label(confidence, attribution)

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


@app.post("/appeal")
def appeal():
    """File an appeal against a classification decision."""
    body = request.get_json(silent=True) or {}
    content_id = body.get("content_id")
    creator_id = body.get("creator_id")
    creator_reasoning = body.get("creator_reasoning")

    if not content_id or not creator_id or not creator_reasoning:
        return (
            jsonify(
                {
                    "error": (
                        "Fields 'content_id', 'creator_id', and "
                        "'creator_reasoning' are required."
                    )
                }
            ),
            400,
        )

    events = read_events()
    content_events = [e for e in events if e.get("content_id") == content_id]

    if not content_events:
        return jsonify({"error": "Content not found."}), 404

    original_creator_id = content_events[0].get("creator_id")
    if creator_id != original_creator_id:
        return (
            jsonify(
                {"error": ("Unauthorized: creator_id does not match the " "original submission.")}
            ),
            403,
        )

    current_status = content_events[-1].get("status")
    if current_status == "under_review":
        return (
            jsonify(
                {
                    "error": (
                        "This content is already under review. "
                        "Only one appeal per content is allowed."
                    )
                }
            ),
            409,
        )

    appeal_event = AuditEvent(
        content_id=content_id,
        creator_id=creator_id,
        timestamp=_utc_now(),
        event="under_review",
        status="under_review",
        appeal_reasoning=creator_reasoning,
    )
    append_event(appeal_event)

    return (
        jsonify(
            {
                "content_id": content_id,
                "status": "under_review",
                "message": "Appeal received; the content is now under review.",
            }
        ),
        200,
    )


@app.get("/appeals")
def get_appeals():
    events = read_events()
    under_review_events = [e for e in events if e.get("status") == "under_review"]

    appeals = []
    for appeal_event in under_review_events:
        content_id = appeal_event.get("content_id")
        content_events = [e for e in events if e.get("content_id") == content_id]
        original_event = content_events[0]

        appeals.append(
            {
                "content_id": content_id,
                "creator_id": appeal_event.get("creator_id"),
                "submitted_at": original_event.get("timestamp"),
                "appealed_at": appeal_event.get("timestamp"),
                "original_decision": {
                    "attribution": original_event.get("attribution"),
                    "confidence": original_event.get("confidence"),
                    "llm_score": original_event.get("llm_score"),
                    "stylometric_score": original_event.get("stylometric_score"),
                    "llm_rationale": original_event.get("llm_rationale"),
                },
                "appeal_reasoning": appeal_event.get("appeal_reasoning"),
                "status": appeal_event.get("status"),
            }
        )

    return jsonify({"appeals": appeals})


@app.get("/content/<content_id>")
def get_content(content_id):
    events = read_events()
    content_events = [e for e in events if e.get("content_id") == content_id]

    if not content_events:
        return jsonify({"error": "Content not found."}), 404

    latest_event = content_events[-1]

    return jsonify(
        {
            "content_id": content_id,
            "creator_id": latest_event.get("creator_id"),
            "attribution": latest_event.get("attribution"),
            "confidence": latest_event.get("confidence"),
            "status": latest_event.get("status"),
        }
    )


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

"""OpenAPI spec + Swagger UI page for Provenance Guard.

Kept out of app.py so the route handlers stay readable. The spec describes every
endpoint that actually exists, so the docs never advertise something that 404s.
"""

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Provenance Guard API",
        "version": "0.5.0",
        "description": (
            "Text-provenance attribution service. Submit text, get an AI-vs-human "
            "attribution with a calibrated confidence score and transparency label, "
            "backed by an append-only audit log. Creators can appeal a decision, "
            "which moves the content into a review queue.\n\n_M5: Signal 1 (LLM "
            "classifier) and Signal 2 (stylometric heuristics) are both live and "
            "blended (0.6 LLM + 0.4 stylometric, with a short-input guard)._"
        ),
    },
    "tags": [
        {"name": "submission", "description": "Submit text for attribution analysis"},
        {"name": "audit", "description": "Inspect the audit log"},
        {"name": "appeals", "description": "File and review appeals against decisions"},
        {"name": "content", "description": "Look up the state of a submission"},
    ],
    "paths": {
        "/submit": {
            "post": {
                "tags": ["submission"],
                "summary": "Submit text for attribution analysis",
                "description": (
                    "Runs the detection pipeline and writes a `classified` event to "
                    "the audit log. Returns a freshly minted `content_id` (save it — "
                    "the appeal endpoint needs it)."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/SubmitRequest"},
                            "example": {
                                "text": (
                                    "The sun dipped below the horizon, painting the sky "
                                    "in hues of amber and rose. I sat on the porch, "
                                    "coffee in hand, watching the neighborhood slowly go "
                                    "quiet."
                                ),
                                "creator_id": "test-user-1",
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Classification result",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SubmitResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": "Missing `text` or `creator_id`",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                    "429": {
                        "description": (
                            "Rate limit exceeded (10 per minute, 100 per day per client)"
                        )
                    },
                },
            }
        },
        "/log": {
            "get": {
                "tags": ["audit"],
                "summary": "Recent audit log entries",
                "description": (
                    "Returns audit events oldest-first. " "In production this would require auth."
                ),
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "description": "Return only the last N entries",
                        "schema": {"type": "integer", "minimum": 1},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Audit entries",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LogResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/appeal": {
            "post": {
                "tags": ["appeals"],
                "summary": "File an appeal against a classification",
                "description": (
                    "Files an appeal for a previously classified submission and moves "
                    "it to `under_review`. The `creator_id` must match the original "
                    "submitter, and only one appeal per content is allowed."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AppealRequest"},
                            "example": {
                                "content_id": "00000000-0000-0000-0000-000000000000",
                                "creator_id": "test-user-1",
                                "creator_reasoning": (
                                    "This is my original writing; the classifier "
                                    "misjudged my style."
                                ),
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Appeal received; content now under review",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AppealResponse"}
                            }
                        },
                    },
                    "400": {
                        "description": (
                            "Missing `content_id`, `creator_id`, or `creator_reasoning`"
                        ),
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                    "403": {
                        "description": "`creator_id` does not match the original submission",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                    "404": {
                        "description": "Content not found",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                    "409": {
                        "description": "Content is already under review (one appeal per content)",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                },
            }
        },
        "/appeals": {
            "get": {
                "tags": ["appeals"],
                "summary": "List content currently under review",
                "description": (
                    "Returns the queue of appealed submissions, each with its original "
                    "decision, reasoning, and the creator's appeal reasoning."
                ),
                "responses": {
                    "200": {
                        "description": "Appeal queue",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AppealsResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/content/{content_id}": {
            "get": {
                "tags": ["content"],
                "summary": "Get a single submission's current state",
                "description": (
                    "Returns the latest known state for a content_id, including its "
                    "attribution, confidence, and status."
                ),
                "parameters": [
                    {
                        "name": "content_id",
                        "in": "path",
                        "required": True,
                        "description": "The content_id returned by /submit",
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Current content state",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ContentResponse"}
                            }
                        },
                    },
                    "404": {
                        "description": "Content not found",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
                        },
                    },
                },
            }
        },
    },
    "components": {
        "schemas": {
            "SubmitRequest": {
                "type": "object",
                "required": ["text", "creator_id"],
                "properties": {
                    "text": {"type": "string", "description": "Raw text to analyze"},
                    "creator_id": {
                        "type": "string",
                        "description": "Identifier of the submitter",
                    },
                },
            },
            "SubmitResponse": {
                "type": "object",
                "properties": {
                    "content_id": {"type": "string", "format": "uuid"},
                    "attribution": {
                        "type": "string",
                        "enum": ["likely_ai", "uncertain", "likely_human"],
                        "nullable": True,
                    },
                    "confidence": {
                        "type": "number",
                        "format": "float",
                        "nullable": True,
                    },
                    "label": {"type": "string"},
                },
            },
            "AuditEvent": {
                "type": "object",
                "properties": {
                    "content_id": {"type": "string"},
                    "creator_id": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "event": {"type": "string", "enum": ["classified", "under_review"]},
                    "status": {
                        "type": "string",
                        "enum": ["classified", "under_review"],
                    },
                    "llm_score": {"type": "number", "nullable": True},
                    "llm_rationale": {"type": "string", "nullable": True},
                    "stylometric_score": {"type": "number", "nullable": True},
                    "confidence": {"type": "number", "nullable": True},
                    "attribution": {"type": "string", "nullable": True},
                    "appeal_reasoning": {"type": "string", "nullable": True},
                },
            },
            "LogResponse": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/AuditEvent"},
                    }
                },
            },
            "AppealRequest": {
                "type": "object",
                "required": ["content_id", "creator_id", "creator_reasoning"],
                "properties": {
                    "content_id": {
                        "type": "string",
                        "format": "uuid",
                        "description": "The content_id returned by /submit",
                    },
                    "creator_id": {
                        "type": "string",
                        "description": "Must match the original submitter",
                    },
                    "creator_reasoning": {
                        "type": "string",
                        "description": "Why the creator is contesting the decision",
                    },
                },
            },
            "AppealResponse": {
                "type": "object",
                "properties": {
                    "content_id": {"type": "string", "format": "uuid"},
                    "status": {"type": "string", "enum": ["under_review"]},
                    "message": {"type": "string"},
                },
            },
            "Appeal": {
                "type": "object",
                "properties": {
                    "content_id": {"type": "string", "format": "uuid"},
                    "creator_id": {"type": "string"},
                    "submitted_at": {"type": "string", "format": "date-time"},
                    "appealed_at": {"type": "string", "format": "date-time"},
                    "original_decision": {
                        "type": "object",
                        "properties": {
                            "attribution": {"type": "string", "nullable": True},
                            "confidence": {"type": "number", "nullable": True},
                            "llm_score": {"type": "number", "nullable": True},
                            "stylometric_score": {"type": "number", "nullable": True},
                            "llm_rationale": {"type": "string", "nullable": True},
                        },
                    },
                    "appeal_reasoning": {"type": "string"},
                    "status": {"type": "string", "enum": ["under_review"]},
                },
            },
            "AppealsResponse": {
                "type": "object",
                "properties": {
                    "appeals": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Appeal"},
                    }
                },
            },
            "ContentResponse": {
                "type": "object",
                "properties": {
                    "content_id": {"type": "string", "format": "uuid"},
                    "creator_id": {"type": "string"},
                    "attribution": {
                        "type": "string",
                        "enum": ["likely_ai", "uncertain", "likely_human"],
                        "nullable": True,
                    },
                    "confidence": {"type": "number", "format": "float", "nullable": True},
                    "status": {
                        "type": "string",
                        "enum": ["classified", "under_review"],
                    },
                },
            },
            "Error": {
                "type": "object",
                "properties": {"error": {"type": "string"}},
            },
        }
    },
}


SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Provenance Guard API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: "/openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
        tryItOutEnabled: true,
      });
    };
  </script>
</body>
</html>
"""

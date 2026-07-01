"""OpenAPI spec + Swagger UI page for Provenance Guard.

Kept out of app.py so the route handlers stay readable. The spec describes only
the endpoints that actually exist (M3: /submit, /log); M5 endpoints get added
here when they land, so the docs never advertise something that 404s.
"""

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Provenance Guard API",
        "version": "0.3.0",
        "description": (
            "Text-provenance attribution service. Submit text, get an AI-vs-human "
            "attribution with a transparency label, backed by an append-only audit "
            "log.\n\n_M3: Signal 1 (LLM classifier) is live; confidence/attribution "
            "are provisional from Signal 1 alone, and the label is a placeholder "
            "until M5._"
        ),
    },
    "tags": [
        {"name": "submission", "description": "Submit text for attribution analysis"},
        {"name": "audit", "description": "Inspect the audit log"},
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
                    "429": {"description": "Rate limit exceeded (added in M5)"},
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

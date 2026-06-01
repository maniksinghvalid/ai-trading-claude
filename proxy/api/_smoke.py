"""Zero-dependency smoke endpoint for Vercel-deploy debugging.

If `POST /api/_smoke` returns 200 but every other endpoint returns
FUNCTION_INVOCATION_FAILED, the issue is somewhere in our import chain
(app.py → _lib → api/*.py → pydantic / pinecone). If even this returns
FUNCTION_INVOCATION_FAILED, the issue is in the Vercel deploy config or
the @vercel/python runtime itself.

This file is in `api/` so Vercel picks it up as its own serverless function
(separate from app.py). NOT routed via app.py's WSGI dispatcher — Vercel
maps `/api/_smoke` directly to this file.
"""

from http.server import BaseHTTPRequestHandler
import json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "ok": True,
            "note": "smoke endpoint — proves Vercel can run a Python function",
            "deploy_marker": "fresh-build-after-vendored-schemas",
        }).encode("utf-8"))

    def do_GET(self):
        self.do_POST()

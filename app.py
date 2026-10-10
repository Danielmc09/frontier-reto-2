"""
app.py - Transporte ASGI minimo. No decide nada: mueve bytes.

Control-plane (definido por el contrato del entrypoint):
    GET  /health   -> 200 (readiness, sin auth)
    POST /__reset  -> reinicia estado SOLO con el token de reset;
                      con token malo o sin token cae a respond() (como el original)

Todo lo demas -> model.respond() (superficie replicada del original).

Correr local:  RESET_TOKEN=... uvicorn app:app --host 0.0.0.0 --port 8000
"""
import os
from model import initial_state, respond

RESET_TOKEN = os.environ.get("RESET_TOKEN", "changeme-reset-token")

STATE = initial_state()


async def _read_body(receive) -> bytes:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body", False):
            break
    return body


async def app(scope, receive, send):
    if scope["type"] != "http":
        return

    method = scope["method"]
    path = scope["path"]
    query = scope.get("query_string", b"").decode("latin-1")
    headers = {k.decode("latin-1").lower(): v.decode("latin-1")
               for k, v in scope.get("headers", [])}
    body = await _read_body(receive)

    global STATE

    if method == "GET" and path == "/health":
        status, resp_headers, resp_body = (
            200, [(b"content-type", b"application/json")], b'{"status":"ok"}')
    elif (method == "POST" and path == "/__reset"
          and headers.get("authorization") == f"Bearer {RESET_TOKEN}"):
        STATE = initial_state()
        status, resp_headers, resp_body = (
            200, [(b"content-type", b"application/json")], b'{"ok":true}')
    else:
        (status, resp_headers, resp_body), STATE = respond(
            method, path, query, headers, body, STATE)

    await send({"type": "http.response.start",
                "status": status, "headers": resp_headers})
    await send({"type": "http.response.body", "body": resp_body})

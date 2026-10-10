"""
app.py - Transporte ASGI minimo. No decide nada: mueve bytes.

Contrato del entrypoint (Reto 2):
- GET /health          -> 200 (readiness, SIN auth)
- Authorization: Bearer <token del equipo> en el resto de las llamadas.
  Con otro token o sin token: responde "como el original" (TODO forense).
- POST /__reset        -> reinicia el estado (con el token del equipo).
                          Lo llaman antes de cada test.
- cualquier otra ruta  -> model.respond() (superficie replicada del original).

El token del equipo se pasa por la variable de entorno TEAM_TOKEN (configurada
en Railway, NUNCA en el repo). RESET_TOKEN sirve como token alterno para pruebas
locales. Si no hay ninguno configurado, se acepta cualquier Bearer no vacio (dev).
"""
import os
from model import initial_state, respond

TEAM_TOKEN = os.environ.get("TEAM_TOKEN", "")
RESET_TOKEN = os.environ.get("RESET_TOKEN", "")

STATE = initial_state()


def _auth_ok(auth: str) -> bool:
    toks = [t for t in (TEAM_TOKEN, RESET_TOKEN) if t]
    if toks:
        return any(auth == f"Bearer {t}" for t in toks)
    # dev (sin tokens configurados): aceptar cualquier Bearer no vacio
    return auth.startswith("Bearer ") and len(auth) > len("Bearer ")


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
    auth = headers.get("authorization", "")

    global STATE

    if method == "GET" and path == "/health":
        status, resp_headers, resp_body = (
            200, [(b"content-type", b"application/json")], b'{"ok":true}')

    elif not _auth_ok(auth):
        # Confirmado por fuzzing: el original responde 401 E001 ante token malo/ausente.
        status, resp_headers, resp_body = (
            401, [(b"content-type", b"application/json")],
            '{"error":"E001","mensaje":"no autorizado"}'.encode("utf-8"))

    elif method == "POST" and path == "/__reset":
        STATE = initial_state()
        # TODO(forense): replicar el cuerpo/status exacto del /__reset del original.
        status, resp_headers, resp_body = (
            200, [(b"content-type", b"application/json")], b'{"ok":true}')

    else:
        (status, resp_headers, resp_body), STATE = respond(
            method, path, query, headers, body, STATE)

    await send({"type": "http.response.start",
                "status": status, "headers": resp_headers})
    await send({"type": "http.response.body", "body": resp_body})

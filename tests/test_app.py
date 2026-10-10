"""app.py: orden ruta / auth (incidente.py entrada). Uso: python -m tests.test_app"""
import asyncio
import os

os.environ["TEAM_TOKEN"] = "t"
import httpx
from app import app

E001 = (401, {"error": "E001", "mensaje": "no autorizado"})
E404 = (404, {"error": "E404", "mensaje": "ruta desconocida"})
CASOS = [  # (metodo, ruta, token, esperado)
    ("GET", "/nope", None, E404),           # ruta antes que auth (confirmado v2)
    ("GET", "/nope", "t", E404),
    ("POST", "/__reset", None, E001),       # ruta conocida: ahi si exige token
    ("POST", "/__reset", "malo", E001),
    ("POST", "/msg", None, E001),
    ("GET", "/health", None, E001),         # el original exige token tambien aqui (v2)
    ("GET", "/health", "t", (200, {"ok": True})),
]


async def main():
    fallos = 0
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        for metodo, ruta, tok, (st, body) in CASOS:
            h = {"Authorization": f"Bearer {tok}"} if tok else {}
            r = await c.request(metodo, ruta, headers=h, json={"m": "PING;64"} if ruta == "/msg" else None)
            if (r.status_code, r.json()) != (st, body):
                fallos += 1
                print(f"FALLA {metodo} {ruta} token={tok}: {r.status_code} {r.text} (esperado {st} {body})")
    print(f"{len(CASOS) - fallos}/{len(CASOS)} casos de app.py")
    assert not fallos


asyncio.run(main())

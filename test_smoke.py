"""Smoke test del contrato del entrypoint, sin levantar servidor (ASGITransport)."""
import asyncio
import httpx
from app import app  # usa RESET_TOKEN del entorno


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        h = await c.get("/health")
        print("GET /health         ->", h.status_code, h.text)

        rb = await c.post("/__reset", headers={"Authorization": "Bearer testreset"})
        print("POST /__reset (ok)  ->", rb.status_code, rb.text)

        rbad = await c.post("/__reset", headers={"Authorization": "Bearer WRONG"})
        print("POST /__reset (bad) ->", rbad.status_code, rbad.text, "(cae a respond/original)")

        n = await c.get("/ruta-inexistente")
        print("GET /ruta-inexist.  ->", n.status_code, n.text)


asyncio.run(main())

"""
differential.py - Test diferencial: mismas secuencias al ORIGINAL (red) y al
REEMPLAZO (in-process, via ASGITransport), comparando status + cuerpo con la
regla del evaluador. Cada secuencia arranca con /__reset en ambos.

Es el banco de pruebas REAL: hay que llegar a divergencia ~0 en local ANTES de
gastar una validacion del set. Headers NO se comparan.

Uso:  TOKEN=<token> RESET_TOKEN=<reset> python differential.py
"""
import os
import asyncio
import httpx

from compare import resp_equal
from app import app  # replica in-process

ORIG = os.environ.get("ORIG_URL", "https://caja-negra-production-c64f.up.railway.app").rstrip("/")
TOKEN = os.environ.get("TOKEN", "")
RESET_TOKEN = os.environ.get("RESET_TOKEN", "testreset")

# Secuencias de prueba. Ampliar / generar aleatorias para cazar divergencias.
SEQS = [
    ["PING;64"],
    ["ALTA;Ana;0", "CONSULTA;AC-0001;0", "DEPOSITO;AC-0001;500;0", "CONSULTA;AC-0001;0"],
    ["CONSULTA;AC-9999;0"],
    ["ZZZ;1", "ALTA;a;b;c;0"],
]


async def run(seqs):
    orig = httpx.Client(
        base_url=ORIG,
        headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}, timeout=10.0)
    transport = httpx.ASGITransport(app=app)
    total = div = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://repl") as repl:
        for i, seq in enumerate(seqs):
            orig.post("/__reset")
            await repl.post("/__reset", headers={"Authorization": f"Bearer {RESET_TOKEN}"})
            for m in seq:
                total += 1
                ro = orig.post("/msg", json={"m": m})
                rr = await repl.post("/msg", json={"m": m})
                if not resp_equal(ro.status_code, ro.content, rr.status_code, rr.content):
                    div += 1
                    print(f"DIVERGE seq{i} m={m!r}")
                    print(f"   orig {ro.status_code} {ro.text}")
                    print(f"   repl {rr.status_code} {rr.text}")
    print(f"{total - div}/{total} pasos iguales")
    orig.close()


if __name__ == "__main__":
    asyncio.run(run(SEQS))

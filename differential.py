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
import time
import httpx

from compare import resp_equal
from app import app  # replica in-process
from model import _checksum
from tabla import encabezado, fila, regla, resumen

ORIG = os.environ.get("ORIG_URL", "https://caja-negra-production-c64f.up.railway.app").rstrip("/")
TOKEN = os.environ.get("TOKEN", "")
RESET_TOKEN = os.environ.get("RESET_TOKEN", "testreset")

GAP = 0.15  # < 10 req/s por token; mas rapido el original responde 429 de infra


def c(payload):
    """Mensaje con su control correcto, para pasar la integridad y probar el comando."""
    return f"{payload};{_checksum(payload.upper())}"


# Secuencias de prueba. Ampliar / generar aleatorias para cazar divergencias.
SEQS = [
    ["PING;64"],
    ["PING;0", "PING;XX", "ZZZ"],  # PING valida control? / mensaje sin ';'
    [c("ALTA;Ana"), c("CONSULTA;AC-0001"), c("DEPOSITO;AC-0001;500"), c("CONSULTA;AC-0001")],
    [c("CONSULTA;AC-9999"), "CONSULTA;AC-0001;0"],
    ["ZZZ;1", "ALTA;a;b;c;0"],
    [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;1000"),
     c("TRANSFER;AC-0001;AC-0002;300"), c("ANULA;OP-0002"), c("ANULA;OP-0002"),
     c("CONSULTA;AC-0002"), c("TRANSFER;AC-0002;AC-0001;5")],
]


COLS = (("SEQ", 4), ("#", 2), ("MENSAJE", 32), ("RESPUESTA", 56), ("RESULTADO", 9))


def _resumen(r):
    try:
        return resumen(r.status_code, r.json())
    except Exception:
        return resumen(r.status_code, r.text)


async def run(seqs):
    orig = httpx.Client(
        base_url=ORIG,
        headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}, timeout=10.0)
    transport = httpx.ASGITransport(app=app)
    print(f"Original : {ORIG}\nReemplazo: app.py in-process\n"
          f"Cada secuencia arranca con /__reset en los dos. Se compara status + cuerpo.\n"
          f"RESPUESTA es la del original; si el reemplazo difiere, va abajo.\n")
    print(encabezado(COLS))
    total = div = 0
    difs = []
    async with httpx.AsyncClient(
            transport=transport, base_url="http://repl",
            headers={"Authorization": f"Bearer {RESET_TOKEN}"}) as repl:
        for i, seq in enumerate(seqs):
            if i:
                print(regla(COLS))
            time.sleep(GAP)
            orig.post("/__reset")
            await repl.post("/__reset")
            for j, m in enumerate(seq, 1):
                time.sleep(GAP)
                ro = orig.post("/msg", json={"m": m})
                if ro.headers.get("X-Frontier-Infra") == "rate-limit":
                    # no llego al servicio: tampoco se manda al repl, los estados siguen iguales
                    print(fila(COLS, f"s{i}", j, m, "429 rate-limit de infra (no llega al servicio)", "SKIP"))
                    continue
                total += 1
                rr = await repl.post("/msg", json={"m": m})
                igual = resp_equal(ro.status_code, ro.content, rr.status_code, rr.content)
                if igual:
                    print(fila(COLS, f"s{i}", j, m, _resumen(ro), "OK"))
                else:
                    div += 1
                    difs.append((f"s{i}", j, m, ro, rr))
                    print(fila(COLS, f"s{i}", j, m, "original : " + _resumen(ro), "DIFERENTE"))
                    print(fila(COLS, "", "", "", "reemplazo: " + _resumen(rr), ""))
    print(regla(COLS))
    print(f"\n{total - div}/{total} pasos iguales")
    # la tabla corta los textos largos: las diferencias van completas abajo
    for sq, j, m, ro, rr in difs:
        print(f"\nDIFERENTE {sq} #{j} {m!r}")
        print(f"  original : {ro.status_code} {ro.text}")
        print(f"  reemplazo: {rr.status_code} {rr.text}")
    orig.close()


if __name__ == "__main__":
    asyncio.run(run(SEQS))

"""
harness.py - Captura de la fase forense contra el ORIGINAL.

POST /msg con pacer (bajo el limite de 10 req/s; presupuesto 8.000/dia por token).
Log en el formato experimentos.jsonl: id, seq, x_req, hipotesis, request, status,
response, conclusion. Las respuestas con header `X-Frontier-Infra: rate-limit` son
de INFRAESTRUCTURA, no del servicio: se marcan y NO se modelan.

Uso:  TOKEN=<tu token> python harness.py
"""
import os
import sys
import json
import time
import itertools
import httpx

BASE_URL = os.environ.get("BASE_URL", "https://caja-negra-production-c64f.up.railway.app").rstrip("/")
TOKEN = os.environ.get("TOKEN", "")
RPS = float(os.environ.get("RPS", "8"))           # < 10/s
LOG_PATH = os.environ.get("LOG_PATH", "experimentos.jsonl")


class Pacer:
    def __init__(self, rps):
        self.gap = 1.0 / rps if rps > 0 else 0.0
        self.last = 0.0

    def wait(self):
        dt = time.monotonic() - self.last
        if dt < self.gap:
            time.sleep(self.gap - dt)
        self.last = time.monotonic()


PACER = Pacer(RPS)
_log = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
# id = numero de linea del log (unico): seguir desde la ultima, no desde 1
_counter = itertools.count(sum(1 for _ in open(LOG_PATH, encoding="utf-8")) + 1)
_client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {},
    timeout=10.0,
)


def reset():
    PACER.wait()
    return _client.post("/__reset")


def msg(m, hipotesis="", seq="s1", conclusion=""):
    PACER.wait()
    r = _client.post("/msg", json={"m": m})
    infra = r.headers.get("X-Frontier-Infra") == "rate-limit"
    try:
        resp = r.json()
    except Exception:
        resp = r.text
    rec = {
        "id": next(_counter), "seq": seq, "x_req": r.headers.get("X-Req"),
        "hipotesis": hipotesis, "request": {"m": m},
        "status": r.status_code, "response": resp, "conclusion": conclusion,
    }
    if infra:
        rec["infra"] = "rate-limit"   # NO es del servicio
    _log.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if infra:
        time.sleep(1.0)
    return rec


def barrer_control(prefijo, rng=range(0, 100), seq="sweep"):
    """Barre el ultimo campo 0..99 para hallar el control valido de un mensaje.
    Valido = la respuesta NO es E201/E202. Base para reversar el checksum."""
    validos = []
    for c in rng:
        rec = msg(f"{prefijo};{c}", hipotesis=f"barrido control {prefijo}", seq=seq)
        err = rec["response"].get("error") if isinstance(rec["response"], dict) else None
        if err not in ("E201", "E202"):
            validos.append(c)
    return validos


if __name__ == "__main__":
    if not TOKEN:
        print("Set TOKEN (y opcional BASE_URL).", file=sys.stderr)
        sys.exit(1)
    reset()
    # Ejemplo: el control valido de "ALTA;Lucia" deberia ser 82 (ver ejemplos).
    print("control(es) valido(s) de ALTA;Lucia:", barrer_control("ALTA;Lucia"))

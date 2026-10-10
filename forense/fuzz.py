"""
fuzz.py - Fase forense contra el ORIGINAL (Reto 2).

Escribe:
  - experimentos.jsonl : el log entregable (append, con timestamp)
  - controles.jsonl    : pares (payload -> control valido) para reversar el checksum

Respeta el rate limit: pacer < 10 req/s; presupuesto 8.000/dia por token.
Las respuestas con header `X-Frontier-Infra: rate-limit` son de INFRA, no del
servicio: se marcan y NO se modelan.

Uso:
  pip install -r requirements-dev.txt        # necesita httpx
  TOKEN=<tu token> python -m forense.fuzz            # corre todo
  TOKEN=<tu token> python -m forense.fuzz checksum   # una sola fase: meta | ejemplos | checksum

Re-correlo despues de las 15:30 y compara experimentos.jsonl: el diff te dice
exactamente que cambio en el servicio.
"""
import os
import sys
import json
import time
import itertools
import httpx

BASE_URL = os.environ.get("BASE_URL", "https://caja-negra-production-c64f.up.railway.app").rstrip("/")
TOKEN = os.environ.get("TOKEN", "")
RPS = float(os.environ.get("RPS", "8"))
LOG = os.environ.get("LOG_PATH", "datos/experimentos.jsonl")
CTRL = os.environ.get("CTRL_PATH", "datos/controles.jsonl")
EX = os.environ.get("EX", "pruebas/ejemplos.jsonl")

if not TOKEN:
    print("Falta TOKEN en el entorno:  TOKEN=<tu token> python -m forense.fuzz", file=sys.stderr)
    sys.exit(1)

_gap = 1.0 / RPS if RPS > 0 else 0.0
_last = [0.0]


def _pace():
    dt = time.monotonic() - _last[0]
    if dt < _gap:
        time.sleep(_gap - dt)
    _last[0] = time.monotonic()


_client = httpx.Client(base_url=BASE_URL,
                       headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10.0)
_logf = open(LOG, "a", buffering=1, encoding="utf-8")
# id = numero de linea del log (unico): seguir desde la ultima, no desde 1
_id = itertools.count(sum(1 for _ in open(LOG, encoding="utf-8")) + 1)
_count = [0]


def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return r.text


def _log(seq, m, status, resp, x_req, hipotesis, conclusion="", infra=False, extra=None):
    rec = {"id": next(_id), "seq": seq, "x_req": x_req, "hipotesis": hipotesis,
           "request": ({"m": m} if m is not None else None),
           "status": status, "response": resp, "conclusion": conclusion, "ts": time.time()}
    if infra:
        rec["infra"] = "rate-limit"
    if extra:
        rec.update(extra)
    _logf.write(json.dumps(rec, ensure_ascii=False) + "\n")


def reset():
    _pace()
    return _client.post("/__reset")


def send(m, seq="s", hipotesis="", conclusion="", headers=None):
    _pace()
    _count[0] += 1
    r = _client.post("/msg", json={"m": m}, headers=headers)
    infra = r.headers.get("X-Frontier-Infra") == "rate-limit"
    resp = _safe_json(r)
    _log(seq, m, r.status_code, resp, r.headers.get("X-Req"), hipotesis, conclusion, infra)
    if infra:
        time.sleep(1.0)
    return r.status_code, resp, r.headers


def _err(resp):
    return resp.get("error") if isinstance(resp, dict) else None


def control_valido(payload, rng=range(0, 100)):
    """Primer control valido (respuesta != E201/E202) para `payload`. Early-stop."""
    for c in rng:
        _, resp, _h = send(f"{payload};{c}", seq="checksum",
                           hipotesis=f"barrido control de '{payload}'")
        if _err(resp) not in ("E201", "E202"):
            return c
    return None


# ---------------- fases ----------------

def meta():
    print("== META: auth, rutas y /__reset ==")
    r = reset()
    print("  POST /__reset (token ok):", r.status_code, r.text[:160])
    _log("meta", None, r.status_code, _safe_json(r), r.headers.get("X-Req"),
         "respuesta de /__reset del original", extra={"ruta": "POST /__reset"})

    for label, hdr in [("sin token", {"Authorization": ""}),
                       ("token malo", {"Authorization": "Bearer XXINVALIDXX"})]:
        _pace()
        rr = _client.post("/msg", json={"m": "PING;1"}, headers=hdr)
        print(f"  /msg PING ({label}):", rr.status_code, rr.text[:160])
        _log("meta-auth", "PING;1", rr.status_code, _safe_json(rr), rr.headers.get("X-Req"),
             f"auth: {label}", extra={"auth": label})

    for method, path in [("GET", "/"), ("GET", "/nope"), ("POST", "/nope"), ("GET", "/msg")]:
        _pace()
        rr = _client.request(method, path)
        print(f"  {method} {path}:", rr.status_code, rr.text[:160])
        _log("meta-ruta", None, rr.status_code, _safe_json(rr), rr.headers.get("X-Req"),
             f"ruta {method} {path}", extra={"ruta": f"{method} {path}"})


def ejemplos():
    from compare import bodies_equal
    print("== EJEMPLOS: replay contra el original (detecta si cambio) ==")
    reset()
    lines = [json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()]
    ok = 0
    for rec in lines:
        m = rec["request"]["m"]
        st, resp, _h = send(m, seq="ejemplos", hipotesis=f"replay ejemplo {rec['n']}")
        same = (st == rec["status"]) and bodies_equal(
            json.dumps(resp).encode(), json.dumps(rec["response"]).encode())
        ok += bool(same)
        if not same:
            print(f"  DIFF n={rec['n']} m={m!r}: hoy {st} {resp} | manana {rec['status']} {rec['response']}")
    print(f"  {ok}/{len(lines)} iguales al ejemplo de la manana")


# familia disenada para aislar la formula del checksum
FAMILIA = [
    # confirmar ejemplos (esperado: Lucia=82, Mateo=3, AC-0001=14, AC-0002=11, AC-0009=87)
    "ALTA;Lucia", "ALTA;Mateo",
    "CONSULTA;AC-0001", "CONSULTA;AC-0002", "CONSULTA;AC-0009",
    # ultimo caracter = digito, sobre prefijo fijo -> peso de la ultima posicion
    "CONSULTA;AAA0", "CONSULTA;AAA1", "CONSULTA;AAA2", "CONSULTA;AAA3", "CONSULTA;AAA4",
    "CONSULTA;AAA5", "CONSULTA;AAA6", "CONSULTA;AAA7", "CONSULTA;AAA8", "CONSULTA;AAA9",
    # ultimo caracter = letra
    "CONSULTA;AAAA", "CONSULTA;AAAB", "CONSULTA;AAAC",
    # mover un caracter de posicion -> peso por posicion
    "CONSULTA;A000", "CONSULTA;0A00", "CONSULTA;00A0", "CONSULTA;000A",
    # longitud
    "CONSULTA;A", "CONSULTA;AA", "CONSULTA;AAAAA",
    # mismo arg, distinto comando (misma aridad 2) -> contribucion del comando
    "ALTA;AAAA", "ANULA;AAAA",
]


def checksum():
    print("== CHECKSUM: barrido de control (payload -> control valido) ==")
    reset()
    ctrlf = open(CTRL, "a", buffering=1, encoding="utf-8")
    tabla = []
    for payload in FAMILIA:
        c = control_valido(payload)
        tabla.append((payload, c))
        ctrlf.write(json.dumps({"payload": payload, "control": c}, ensure_ascii=False) + "\n")
        print(f"  {payload:<26} -> {c}")
    print("\n== TABLA (pegasela a Claude para reversar la formula) ==")
    for p, c in tabla:
        print(f"{p}\t{c}")


PHASES = {"meta": meta, "ejemplos": ejemplos, "checksum": checksum}

if __name__ == "__main__":
    sel = sys.argv[1] if len(sys.argv) > 1 else "all"
    est = len(FAMILIA)
    print(f"Presupuesto aprox: meta ~12, ejemplos ~20, checksum <= {est*100} "
          f"(early-stop, ~{est*50} tipico). Pacer {RPS} req/s. Tope diario: 8000.\n")
    if sel in ("all", "meta"):
        meta()
    if sel in ("all", "ejemplos"):
        ejemplos()
    if sel in ("all", "checksum"):
        checksum()
    print(f"\nTotal requests enviados: {_count[0]}  (log: {LOG} | controles: {CTRL})")

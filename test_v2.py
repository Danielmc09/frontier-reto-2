"""El modelo contra respuestas grabadas de la v2 (incidente FR-0153).

  - pruebas/ejemplos_v2.jsonl: los 20 ejemplos contra la v2 (regresion de las 16:01).
  - bordes_v2.jsonl: 110 pasos de casos borde contra la v2 (bordes.py de las 15:58).
  - limite de TRANSFER: 50000 pasa, 50001 da E506 (incidente.py, umbral).

Uso:  python test_v2.py
"""
import json
from collections import defaultdict
import model
from compare import bodies_equal


def correr(pasos):
    """pasos = [(body_bytes, status, response)] desde el estado inicial. Devuelve los fallos."""
    st, fallos = model.initial_state(), []
    for body, exp_st, exp in pasos:
        try:
            (got_st, _h, got), st = model.respond("POST", "/msg", "", {}, body, st)
            got = json.loads(got)
        except Exception as e:
            got_st, got = 500, f"{type(e).__name__}: {e}"
        if got_st != exp_st or not bodies_equal(json.dumps(got).encode(), json.dumps(exp).encode()):
            fallos.append(f"{body.decode()!r}\n    v2    : {exp_st} {exp}\n    modelo: {got_st} {got}")
    return fallos


def m(texto):
    return json.dumps({"m": texto}).encode()


fallos = []

ej = [json.loads(l) for l in open("pruebas/ejemplos_v2.jsonl", encoding="utf-8")]
fallos += correr([(m(r["request"]["m"]), r["status"], r["response"]) for r in ej])

casos = defaultdict(list)
for l in open("bordes_v2.jsonl", encoding="utf-8"):
    r = json.loads(l)
    # los casos body-* mandaron el cuerpo crudo, el resto {"m": request}
    body = r["request"].encode() if r["caso"].startswith("body-") else m(r["request"])
    casos[r["caso"]].append((body, r["status"], r["response"]))
for pasos in casos.values():
    fallos += correr(pasos)

base = [(m(f"{p};{model._checksum(p)}"), s, r) for p, s, r in [
    ("ALTA;Ana", 201, {"cuentaId": "AC-0001"}),
    ("ALTA;Beto", 201, {"cuentaId": "AC-0002"}),
    ("DEPOSITO;AC-0001;999999", 200, {"status": "recieved", "operacionId": "OP-0001"}),
    ("TRANSFER;AC-0001;AC-0002;50000", 200, {"status": "recieved", "operacionId": "OP-0002"}),
    ("TRANSFER;AC-0001;AC-0002;50001", 422, {"error": "E506", "mensaje": "límite excedido"}),
]]
fallos += correr(base)

total = len(ej) + sum(len(p) for p in casos.values()) + len(base)
for f in fallos:
    print("FALLA", f)
print(f"{total - len(fallos)}/{total} pasos como la v2")
assert not fallos

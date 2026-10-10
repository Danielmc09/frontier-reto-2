"""
aleatorio.py - Diferencial aleatorio en flujo continuo: original vs model.py.

Un solo /__reset y una tira de requests al azar; el modelo recibe la misma tira en
paralelo y con el mismo estado, asi cada request prueba algo y las secuencias largas
quedan cubiertas. Ante una diferencia la anota, resetea los dos lados y sigue.
Se corta solo ante el rate-limit de infra. Todo se loguea en experimentos.jsonl.

  N=300 SEED=1 TOKEN=<token> python -m forense.aleatorio
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python -m forense.aleatorio"
"""
import json
import os
import random
from collections import Counter

from forense.fuzz import reset, send
import model
from compare import bodies_equal
from forense.tabla import encabezado, fila, regla, resumen

N = int(os.environ.get("N", "300"))
SEED = int(os.environ.get("SEED", "1"))
rnd = random.Random(SEED)

NOMBRES = ["Ana", "Beto", "José", "Ana Maria", "123", "x" * 40, "ñandu", "A-1", "lucia"]
MONTOS = ["1", "5", "99", "100", "1000", "25000", "49999", "50000", "50001", "120000",
          "999999", "0", "-1", "1e3", "10 ", "99999999999999999999", "+5", "１"]


def _cuenta(st):
    existentes = list(st["cuentas"])
    return rnd.choice(existentes * 4 + ["AC-9999", "ac-0001", "AC-1", " AC-0001", "AC-00001"]) \
        if existentes else rnd.choice(["AC-0001", "AC-9999"])


def _op(st):
    existentes = list(st["ops"])
    return rnd.choice(existentes * 3 + ["OP-9999", "op-0001", "OP-1"]) if existentes else "OP-0001"


def generar(st):
    """Un mensaje al azar, sesgado a lo que tiene sentido en el estado actual."""
    cmd = rnd.choices(["ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA", "PING", "OTRO"],
                      weights=[14, 16, 22, 26, 12, 4, 6])[0]
    if cmd == "ALTA":
        args = [rnd.choice(NOMBRES)]
    elif cmd == "CONSULTA":
        args = [_cuenta(st)]
    elif cmd == "DEPOSITO":
        args = [_cuenta(st), rnd.choice(MONTOS)]
    elif cmd == "TRANSFER":
        args = [_cuenta(st), _cuenta(st), rnd.choice(MONTOS)]
    elif cmd == "ANULA":
        args = [_op(st)]
    elif cmd == "PING":
        return rnd.choice(["PING;64", "PING;0", "PING;XX", "PING"])
    else:
        cmd, args = rnd.choice(["SALDOS", "BORRAR", "Ping", "altas"]), [_cuenta(st)]
    if rnd.random() < 0.04:          # aridad incorrecta
        args = args[:-1] if args and rnd.random() < 0.5 else args + ["x"]
    if rnd.random() < 0.3:           # comando en minusculas o mixto
        cmd = rnd.choice([cmd.lower(), cmd.capitalize()])
    payload = ";".join([cmd] + args)
    ctrl = model._checksum(payload)
    r = rnd.random()
    if r < 0.08:
        ctrl = (ctrl + 1) % 100      # control invalido
    elif r < 0.11:
        ctrl = rnd.choice(["7X", "100", ""])
    return f"{payload};{ctrl}"


def _modelo(m, st):
    try:
        (s, _h, b), st = model.respond("POST", "/msg", "", {}, json.dumps({"m": m}).encode(), st)
        return s, json.loads(b), st
    except Exception as e:
        return 500, f"Internal Server Error ({type(e).__name__})", st


def _err(resp):
    return resp.get("error") if isinstance(resp, dict) else None


if __name__ == "__main__":
    cols = (("#", 4), ("MENSAJE", 36), ("ORIGINAL", 40), ("MODELO", 40))
    print(f"Diferencial aleatorio: {N} requests, semilla {SEED}. Solo se listan las diferencias.\n")
    print(encabezado(cols))
    reset()
    st = model.initial_state()
    difs, usados, previos = [], 0, []
    for i in range(1, N + 1):
        m = generar(st)
        so, ro, h = send(m, seq=f"aleatorio-s{SEED}",
                         hipotesis="diferencial aleatorio: el original responde como model.py")
        usados += 1
        if h.get("X-Frontier-Infra") == "rate-limit":
            print(f"\nRATE-LIMIT de infra en el request {i}: se corta para no seguir gastando.")
            break
        sm, rm, st2 = _modelo(m, st)
        if so == sm and bodies_equal(json.dumps(ro).encode(), json.dumps(rm).encode()):
            st = st2
            previos.append(m)
            continue
        difs.append({"i": i, "m": m, "previos": previos[-6:], "orig": (so, ro), "modelo": (sm, rm)})
        print(fila(cols, i, m, resumen(so, ro), resumen(sm, rm)))
        reset()                      # resincronizar: el estado de los dos lados ya difiere
        usados += 1
        st, previos = model.initial_state(), []
    print(regla(cols))

    print(f"\nRequests usados: {usados} (incluye resets) | diferencias: {len(difs)}")
    tipos = Counter((m["m"].split(";")[0].upper(), _err(m["orig"][1]) or m["orig"][0],
                     _err(m["modelo"][1]) or m["modelo"][0]) for m in difs)
    if tipos:
        print("\nAgrupadas (comando, original, modelo):")
        for (cmd, o, md), n in tipos.most_common():
            print(f"  {n:>3}x  {cmd:<9} original={o!s:<6} modelo={md}")
    # detalle con los pasos previos: hace falta para reproducir lo que depende del estado
    for d in difs:
        print(f"\n#{d['i']} {d['m']!r}   (previos desde el ultimo reset: {d['previos']})")
        print(f"  original: {d['orig'][0]} {json.dumps(d['orig'][1], ensure_ascii=False)}")
        print(f"  modelo  : {d['modelo'][0]} {json.dumps(d['modelo'][1], ensure_ascii=False)}")

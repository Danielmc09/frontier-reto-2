"""
incidente.py - Sondas del incidente FR-0153 (deploy de la v2) contra el ORIGINAL.
Todo se loguea en experimentos.jsonl con su hipotesis.

  1) umbral : busqueda binaria del nuevo limite de TRANSFER (v1: 100000 pasaba;
              v2: 100000 da E506, 40000 pasa).
  2) replay : re-manda a la v2 los requests de la v1 que no dependen del estado
              (errores sin cuentas ni operaciones creadas) y compara la respuesta.
              Lo distinto es candidato al cambio que falta.
  3) anula  : ANULA de una TRANSFER y anular dos veces (v1: lineas 6319/6320 del log),
              nunca probado en la v2.
  4) meta   : /__reset, token malo y rutas desconocidas (v1: lineas 6300-6306 del log).
  5) supuestos: lo que model.py hace sin evidencia (E304 vs otros errores, monto "05",
              control 99/"00", "PING;"), comparado contra el modelo en el momento.

  python incidente.py [umbral|replay|anula|meta|supuestos]   # sin argumento corre las tres

  TOKEN=<token> python incidente.py
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python incidente.py"
"""
import datetime
import json
from collections import defaultdict

from fuzz import LOG, _client, _log, _pace, _safe_json, reset, send
from compare import bodies_equal
from model import _checksum
from tabla import encabezado, fila, regla, resumen

# la v1 respondia igual que los ejemplos hasta las 15:38 (regresion.jsonl); el log de
# experimentos de la v1 termina a las 15:30:54
# hora de Bogota explicita: en Docker el reloj esta en UTC
V1_HASTA = datetime.datetime(2026, 10, 10, 15, 35,
                             tzinfo=datetime.timezone(datetime.timedelta(hours=-5))).timestamp()


def c(payload):
    return f"{payload};{_checksum(payload)}"


def _err(resp):
    return resp.get("error") if isinstance(resp, dict) else None


def umbral():
    cols = (("MONTO", 8), ("RESPUESTA", 50), ("LIMITE ENTRE", 20))
    print("\n=== 1) Umbral de TRANSFER: busqueda binaria entre 40000 (pasa) y 100000 (E506) ===\n")
    reset()
    for m in (c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;999999")):
        send(m, seq="v2-umbral", hipotesis="preparar estado: dos cuentas y saldo para transferir")
    print(encabezado(cols))
    lo, hi = 40000, 100000  # lo pasa, hi da E506
    while hi - lo > 1:
        mid = (lo + hi) // 2
        st, resp, _ = send(c(f"TRANSFER;AC-0001;AC-0002;{mid}"), seq="v2-umbral",
                           hipotesis=f"v2: el limite de TRANSFER esta entre {lo} y {hi}; pruebo {mid}")
        if _err(resp) == "E506":
            hi = mid
        else:
            lo = mid
        print(fila(cols, mid, resumen(st, resp), f"{lo} .. {hi}"))
    print(regla(cols))
    print(f"\nLimite v2: {lo} pasa, {hi} da E506  ->  E506 si monto >= {hi} (v1: si monto > 100000)")


def replay():
    cols = (("REQUEST V1", 34), ("V1", 30), ("V2 (AHORA)", 30), ("RESULTADO", 9))
    v1 = defaultdict(set)
    for l in open(LOG, encoding="utf-8"):
        r = json.loads(l)
        if r["ts"] < V1_HASTA and r.get("request") and isinstance(r["request"], dict):
            v1[r["request"]["m"]].add((r["status"], json.dumps(r["response"], sort_keys=True)))
    casos = []
    for m, vistos in v1.items():
        if len(vistos) != 1:
            continue  # respondio distinto segun el estado: no sirve tras un reset
        st, body = next(iter(vistos))
        resp = json.loads(body)
        # solo errores que no dependen de cuentas/operaciones creadas
        if _err(resp) in (None, "E202", "E001", "E506", "E507"):
            continue
        casos.append((m, st, resp))

    print(f"\n=== 2) Replay: {len(casos)} requests de la v1 sin estado, mandados de nuevo a la v2 ===\n")
    reset()  # ninguno crea cuentas ni operaciones: un solo reset alcanza
    print(encabezado(cols))
    cambios = []
    for m, st1, r1 in casos:
        st2, r2, _ = send(m, seq="v2-replay", hipotesis=f"v2 responde como la v1 ({st1} {_err(r1)})")
        igual = st1 == st2 and bodies_equal(json.dumps(r1).encode(), json.dumps(r2).encode())
        print(fila(cols, m, resumen(st1, r1), "=" if igual else resumen(st2, r2),
                   "OK" if igual else "CAMBIO"))
        if not igual:
            cambios.append((m, st1, r1, st2, r2))
    print(regla(cols))
    print(f"\n{len(casos) - len(cambios)}/{len(casos)} iguales a la v1")
    for m, st1, r1, st2, r2 in cambios:
        print(f"\nCAMBIO {m!r}\n  v1: {st1} {json.dumps(r1, ensure_ascii=False)}"
              f"\n  v2: {st2} {json.dumps(r2, ensure_ascii=False)}")


def anula():
    cols = (("MENSAJE", 30), ("ESPERADO (v1 con saldo en formato v2)", 40), ("V2 (AHORA)", 34), ("RESULTADO", 9))
    print("\n=== 3) ANULA de una TRANSFER y anular dos veces (v1: lineas 6319 y 6320) ===\n")
    # esperado = comportamiento v1; solo el saldo va en el formato nuevo (cambio 1, ya conocido)
    pasos = [
        (c("ALTA;Ana"), 201, {"cuentaId": "AC-0001"}),
        (c("ALTA;Beto"), 201, {"cuentaId": "AC-0002"}),
        (c("DEPOSITO;AC-0001;100000"), 200, {"status": "recieved", "operacionId": "OP-0001"}),
        (c("TRANSFER;AC-0001;AC-0002;40000"), 200, {"status": "recieved", "operacionId": "OP-0002"}),
        (c("ANULA;OP-0002"), 200, {"ok": True, "anulada": "OP-0002"}),
        (c("ANULA;OP-0002"), 200, {"ok": False, "motivo": "ya anulada"}),
        (c("CONSULTA;AC-0001"), 200, {"cuenta_id": "AC-0001", "saldo": "1000.00"}),
        (c("CONSULTA;AC-0002"), 200, {"cuenta_id": "AC-0002", "saldo": "0.00"}),
    ]
    reset()
    print(encabezado(cols))
    cambios = []
    for m, st1, r1 in pasos:
        st2, r2, _ = send(m, seq="v2-anula",
                          hipotesis=f"v2: ANULA de TRANSFER y doble ANULA como en la v1; espero {st1} {r1}")
        igual = st1 == st2 and bodies_equal(json.dumps(r1).encode(), json.dumps(r2).encode())
        print(fila(cols, m, resumen(st1, r1), "=" if igual else resumen(st2, r2), "OK" if igual else "CAMBIO"))
        if not igual:
            cambios.append((m, st1, r1, st2, r2))
    print(regla(cols))
    print(f"\n{len(pasos) - len(cambios)}/{len(pasos)} como se esperaba")
    for m, st1, r1, st2, r2 in cambios:
        print(f"\nCAMBIO {m!r}\n  esperado: {st1} {json.dumps(r1, ensure_ascii=False)}"
              f"\n  v2      : {st2} {json.dumps(r2, ensure_ascii=False)}")


def meta():
    cols = (("REQUEST", 30), ("V1", 40), ("V2 (AHORA)", 34), ("RESULTADO", 9))
    print("\n=== 4) Meta: /__reset, token malo y rutas (v1: lineas 6300-6306) ===\n")
    malo = {"Authorization": "Bearer token-malo"}
    pasos = [  # (metodo, ruta, headers, cuerpo, status v1, cuerpo v1)
        ("POST", "/__reset", None, None, 200, {"ok": True}),
        ("POST", "/msg", malo, {"m": "PING;64"}, 401, {"error": "E001", "mensaje": "no autorizado"}),
        ("GET", "/", None, None, 404, {"error": "E404", "mensaje": "ruta desconocida"}),
        ("POST", "/nope", None, None, 404, {"error": "E404", "mensaje": "ruta desconocida"}),
        ("GET", "/health", None, None, None, None),  # nunca probado en la v1
    ]
    print(encabezado(cols))
    for metodo, ruta, hdr, body, st1, r1 in pasos:
        _pace()
        r = _client.request(metodo, ruta, headers=hdr, json=body)
        r2 = _safe_json(r)
        que = f"{metodo} {ruta}" + (" token malo" if hdr else "")
        _log("v2-meta", body["m"] if body else None, r.status_code, r2, r.headers.get("X-Req"),
             f"v2: {que} responde como la v1" if st1 else f"v2: que responde {que} (sin dato de la v1)",
             extra={"ruta": f"{metodo} {ruta}"})
        if st1 is None:
            print(fila(cols, que, "(sin dato de la v1)", resumen(r.status_code, r2), "NUEVO"))
            continue
        igual = r.status_code == st1 and r2 == r1
        print(fila(cols, que, resumen(st1, r1), "=" if igual else resumen(r.status_code, r2),
                   "OK" if igual else "CAMBIO"))
    print(regla(cols))


def supuestos():
    from bordes import _igual, _modelo, _original
    import model
    cols = (("SUPUESTO", 16), ("MENSAJE", 32), ("V2 (ORIGINAL)", 34), ("MODELO", 9))
    print("\n=== 5) Supuestos del modelo contra la v2 ===\n")
    alta = [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;100000")]
    casos = [  # (supuesto, hipotesis, pasos); el ultimo paso es la sonda
        ("E304-vs-E401", "orden: E304 (misma cuenta) antes que E401 (cuenta inexistente)",
         [c("TRANSFER;AC-9999;AC-9999;100")]),
        ("E304-vs-E303", "orden: E303 (monto) antes que E304 (misma cuenta)",
         alta + [c("TRANSFER;AC-0001;AC-0001;0")]),
        ("E304-vs-E506", "orden: E304 (misma cuenta) antes que E506 (limite)",
         alta + [c("TRANSFER;AC-0001;AC-0001;60000")]),
        ("monto-05", "monto con cero a la izquierda ('05') da E303",
         alta + [c("DEPOSITO;AC-0001;05")]),
        ("control-99", "control 99 esta bien formado: da E202 (no E201)", alta + ["CONSULTA;AC-0001;99"]),
        ("control-00", "control '00' esta mal formado: da E201", alta + ["CONSULTA;AC-0001;00"]),
        ("ping-vacio", "'PING;' da E104 (segmento vacio)", ["PING;"]),
    ]
    print(encabezado(cols))
    difs = []
    for k, (sup, hip, pasos) in enumerate(casos):
        if k:
            print(regla(cols))
        reset()
        estado = model.initial_state()
        for j, paso in enumerate(pasos, 1):
            sonda = j == len(pasos)
            orig = _original(paso, f"v2-supuesto-{sup}", hip if sonda else f"preparar estado para: {hip}")
            *mod, estado = _modelo(paso, estado)
            if not sonda:
                continue
            ok = _igual(orig, mod)
            print(fila(cols, sup, paso, resumen(*orig), "=" if ok else "DIFERENTE"))
            if not ok:
                print(fila(cols, "", "", "modelo: " + resumen(*mod), ""))
                difs.append((sup, paso, orig, mod))
    print(regla(cols))
    print(f"\n{len(casos) - len(difs)}/{len(casos)} supuestos confirmados")
    for sup, paso, orig, mod in difs:
        print(f"\nDIFERENTE {sup} {paso!r}\n  v2    : {orig[0]} {json.dumps(orig[1], ensure_ascii=False)}"
              f"\n  modelo: {mod[0]} {json.dumps(mod[1], ensure_ascii=False)}")


if __name__ == "__main__":
    import sys
    fases = {"umbral": umbral, "replay": replay, "anula": anula, "meta": meta, "supuestos": supuestos}
    print("Incidente FR-0153: sondas contra el original (log: experimentos.jsonl)")
    for nombre in (sys.argv[1:] or fases):
        fases[nombre]()

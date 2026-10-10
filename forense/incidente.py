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

  python -m forense.incidente [umbral|replay|anula|meta|supuestos|afinar|anula-limite|titular|variantes|entrada|http]   # sin argumento corre las tres

  TOKEN=<token> python -m forense.incidente
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python -m forense.incidente"
"""
import datetime
import json
from collections import defaultdict

from forense.fuzz import LOG, _client, _log, _pace, _safe_json, reset, send
from compare import bodies_equal
from model import _checksum
from forense.tabla import encabezado, fila, regla, resumen

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


def _sondear(titulo, casos):
    """casos = [(nombre, hipotesis, pasos)]; cada caso arranca con reset. Compara cada paso
    del original contra model.py en el momento y lo loguea todo."""
    from bordes import _igual, _modelo, _original
    import model
    cols = (("CASO", 16), ("MENSAJE", 34), ("ORIGINAL", 36), ("MODELO", 9))
    print(f"\n=== {titulo} ===\n")
    print(encabezado(cols))
    difs = []
    for k, (nombre, hip, pasos) in enumerate(casos):
        if k:
            print(regla(cols))
        reset()
        estado = model.initial_state()
        for j, paso in enumerate(pasos, 1):
            sonda = j == len(pasos)
            orig = _original(paso, f"v2-{nombre}", hip if sonda else f"preparar estado para: {hip}")
            if orig[0] == 429:
                print(f"\nRATE-LIMIT de infra en {nombre}: se corta para no seguir gastando.")
                return
            *mod, estado = _modelo(paso, estado)
            ok = _igual(orig, mod)
            print(fila(cols, nombre if j == 1 else "", paso, resumen(*orig), "=" if ok else "DIFERENTE"))
            if not ok:
                print(fila(cols, "", "", "modelo: " + resumen(*mod), ""))
                difs.append((nombre, paso, orig, mod))
    print(regla(cols))
    print(f"\n{sum(len(p) for _, _, p in casos) - len(difs)}/{sum(len(p) for _, _, p in casos)} pasos iguales al modelo")
    for nombre, paso, orig, mod in difs:
        print(f"\nDIFERENTE {nombre} {paso!r}\n  original: {orig[0]} {json.dumps(orig[1], ensure_ascii=False)}"
              f"\n  modelo  : {mod[0]} {json.dumps(mod[1], ensure_ascii=False)}")


def supuestos():
    alta = [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;100000")]
    _sondear("5) Supuestos del modelo contra la v2", [
        ("E304-vs-E401", "orden: E304 (misma cuenta) antes que E401 (cuenta inexistente)",
         [c("TRANSFER;AC-9999;AC-9999;100")]),
        ("E304-vs-E303", "orden: E303 (monto) antes que E304 (misma cuenta)",
         alta + [c("TRANSFER;AC-0001;AC-0001;0")]),
        ("E304-vs-E506", "orden: E304 (misma cuenta) antes que E506 (limite)",
         alta + [c("TRANSFER;AC-0001;AC-0001;60000")]),
        ("monto-05", "monto con cero a la izquierda ('05') da E303", alta + [c("DEPOSITO;AC-0001;05")]),
        ("control-99", "control 99 esta bien formado: da E202 (no E201)", alta + ["CONSULTA;AC-0001;99"]),
        ("control-00", "control '00' esta mal formado: da E201", alta + ["CONSULTA;AC-0001;00"]),
        ("ping-vacio", "'PING;' da E104 (segmento vacio)", ["PING;"]),
    ])


def afinar():
    """Lo que dejo aleatorio.py (semilla 1): E506 vs E507, tope de monto y sugerencia de E301."""
    dos = [c("ALTA;Ana"), c("ALTA;Beto")]
    mil = dos + [c("DEPOSITO;AC-0001;1000")]
    t = lambda x: c(f"TRANSFER;AC-0001;AC-0002;{x}")
    casos = [
        ("lim-saldo0", "saldo 0 y 150000: E506 (limite) o E507 (saldo)", dos + [t(150000)]),
        ("lim-saldo0-60k", "saldo 0 y 60000: E506 o E507", dos + [t(60000)]),
    ]
    for x in (200000, 300000, 500000, 999999):
        casos.append((f"lim-{x}", f"saldo 1000 y {x}: hasta que monto aplica E506", mil + [t(x)]))
    for x in (10**7, 10**9, 2**31 - 1, 2**31, 10**12, 2**53, 2**63 - 1, 2**63, 10**19):
        casos.append((f"tope-{x}", f"TRANSFER {x}: E303 (tope de monto) o E401 (sin cuentas)",
                      [c(f"TRANSFER;AC-0001;AC-0002;{x}")]))
    for x in (10**12, 10**20):
        casos.append((f"dep-{x}", f"DEPOSITO {x}: tiene tope (E303) o pasa", [c("ALTA;Ana"), c(f"DEPOSITO;AC-0001;{x}")]))
    for cmd in ("ALT", "ALTAX", "ALTB", "ATLA", "ALTAAA", "XLTB", "DEPOSTO", "DEPOSITOS",
                "CONSULTAR", "TRANSFERIR", "ANULAR", "PIN"):
        casos.append((f"sug-{cmd}", f"E301 de '{cmd}': trae sugerencia o no", [c(f"{cmd};AC-0001")]))
    _sondear("6) Afinar: E506 vs E507, tope de monto, sugerencia de E301", casos)


def anula_limite():
    """aleatorio.py #280: tras una ANULA, TRANSFER 999999 dio E507 en vez de E506."""
    t = lambda o, d, x: c(f"TRANSFER;{o};{d};{x}")
    dos = [c("ALTA;Ana"), c("ALTA;Beto")]
    casos = [
        ("A-anula", "tras ANULA de un deposito, TRANSFER 999999 desde saldo 0 da E507 (no E506)",
         dos + [c("DEPOSITO;AC-0001;1000"), c("ANULA;OP-0001"), t("AC-0002", "AC-0001", 999999)]),
        ("B-sin-anula", "sin ANULA, tras deposito de 120000, TRANSFER 999999 desde saldo 0 da E506",
         dos + [c("DEPOSITO;AC-0001;120000"), t("AC-0002", "AC-0001", 999999)]),
        ("C-anula-pasa", "tras una ANULA, TRANSFER 60000 con saldo suficiente pasa el limite",
         dos + [c("DEPOSITO;AC-0001;200000"), c("DEPOSITO;AC-0001;1000"), c("ANULA;OP-0002"),
                t("AC-0001", "AC-0002", 60000), c("CONSULTA;AC-0001")]),
        ("D-sin-estado", "tope de monto (E303 vs E401 sin cuentas) y sugerencia de E301 a distancia 3/4",
         [t("AC-0001", "AC-0002", x) for x in (4294967295, 4294967296, 9999999999, 10000000000,
                                                  99999999999, 100000000000, 999999999999)]
         + [c("XYZA;AC-0001"), c("WXYZ;AC-0001"), c("PONG;AC-0001")]),
    ]
    _sondear("7) ANULA y limite, tope de monto, sugerencia a distancia 3", casos)


def titular():
    """aleatorio.py #280: AC-0007 y AC-0001 eran los dos de 'José'; TRANSFER 999999 dio E507.
    Hipotesis: el limite de 50000 no aplica entre cuentas del mismo titular."""
    t = lambda o, d, x: c(f"TRANSFER;{o};{d};{x}")
    _sondear("8) Limite entre cuentas del mismo titular", [
        ("titular", "mismo titular (Ana y Ana): TRANSFER 60000 pasa, el limite no aplica",
         [c("ALTA;Ana"), c("ALTA;Ana"), c("DEPOSITO;AC-0001;100000"),
          t("AC-0001", "AC-0002", 60000), c("CONSULTA;AC-0002")]),
        ("titular-mayus", "'Ana' y 'ana' cuentan como el mismo titular",
         [c("ALTA;Ana"), c("ALTA;ana"), c("DEPOSITO;AC-0001;100000"), t("AC-0001", "AC-0002", 60000)]),
        ("titular-999999", "mismo titular con otra cuenta en el medio: 999999 da E507 y 60000 pasa",
         [c("ALTA;Ana"), c("ALTA;Beto"), c("ALTA;Ana"), c("DEPOSITO;AC-0001;100000"),
          t("AC-0001", "AC-0003", 999999), t("AC-0001", "AC-0003", 60000)]),
    ])


def variantes():
    """Tras la corrida 3 (82/100): 7 tests fallan en el primer request y 11 mas adelante.
    Espacios en el mensaje, mensajes repetidos, ANULA con el dinero ya gastado, saldo negativo
    y ANULA de una transferencia entre cuentas del mismo titular."""
    t = lambda o, d, x: c(f"TRANSFER;{o};{d};{x}")
    _sondear("9) Variantes: espacios, repetidos, ANULA con saldo gastado, saldo negativo", [
        ("espacios", "espacios alrededor del comando y de los campos: se recortan o no",
         [" PING;64", "PING ;64", "PING;64 ", "\tPING;64", "   ",
          " ALTA;Ana;50", "ALTA ;Ana;50", "ALTA; Ana;50", "ALTA;Ana ;50",
          "CONSULTA; AC-0001;14", "CONSULTA;AC-0001 ;14"]),
        ("repetidos", "el mismo DEPOSITO/TRANSFER dos veces seguidas: se procesa dos veces o se rechaza",
         [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;1000"), c("DEPOSITO;AC-0001;1000"),
          t("AC-0001", "AC-0002", 100), t("AC-0001", "AC-0002", 100), c("CONSULTA;AC-0001")]),
        ("anula-gastado", "ANULA de una TRANSFER cuyo destino ya gasto el dinero; operar con saldo negativo",
         [c("ALTA;Ana"), c("ALTA;Beto"), c("ALTA;Caro"), c("DEPOSITO;AC-0001;1000"),
          t("AC-0001", "AC-0002", 1000), t("AC-0002", "AC-0003", 1000), c("ANULA;OP-0002"),
          c("CONSULTA;AC-0002"), t("AC-0002", "AC-0003", 1), c("DEPOSITO;AC-0002;500"),
          c("CONSULTA;AC-0002")]),
        ("anula-titular", "ANULA de una TRANSFER exenta del limite (mismo titular) y del deposito previo",
         [c("ALTA;Ana"), c("ALTA;Ana"), c("DEPOSITO;AC-0001;100000"), t("AC-0001", "AC-0002", 60000),
          c("ANULA;OP-0002"), c("CONSULTA;AC-0001"), c("ANULA;OP-0001"), c("CONSULTA;AC-0001")]),
    ])


def entrada():
    """Seccion Entrada del enunciado: limites, nombres con simbolos, JSON raro y el orden
    auth/ruta sin token (la evidencia v1 de 'auth antes que ruta' es solo de /msg)."""
    from bordes import raw
    _sondear("10a) Entrada: limites de tamano, nombres con simbolos, JSON raro", [
        ("entrada", "limites de largo del nombre, simbolos en el nombre y JSON con forma rara",
         [c("ALTA;" + "x" * n) for n in (41, 100, 256, 1000)]
         + [c(f"ALTA;{n}") for n in ("Ana.B", "Ana_B", "Ana@B", "Ana/B", "😀")]
         + [raw('{"m": "PING;64", "x": 1}'), raw('{"m": null}'), raw("[]")]),
    ])
    # sin token / token malo: lo responde app.py (auth antes que todo, salvo /health)
    cols = (("REQUEST", 34), ("ORIGINAL", 40), ("NUESTRO APP", 30), ("", 9))
    print("\n=== 10b) Auth y ruta sin token ===\n")
    print(encabezado(cols))
    e001 = (401, {"error": "E001", "mensaje": "no autorizado"})
    for metodo, ruta, hdr in [("GET", "/nope", {"Authorization": ""}),
                              ("POST", "/__reset", {"Authorization": ""}),
                              ("POST", "/__reset", {"Authorization": "Bearer token-malo"})]:
        _pace()
        r = _client.request(metodo, ruta, headers=hdr)
        r2 = _safe_json(r)
        que = f"{metodo} {ruta} " + ("sin token" if hdr["Authorization"] == "" else "token malo")
        _log("v2-entrada", None, r.status_code, r2, r.headers.get("X-Req"),
             f"v2: {que} -> E001 (auth antes que la ruta) o 404", extra={"ruta": f"{metodo} {ruta}"})
        igual = r.status_code == e001[0] and r2 == e001[1]
        print(fila(cols, que, resumen(r.status_code, r2), "=" if igual else resumen(*e001),
                   "OK" if igual else "DIFERENTE"))
    print(regla(cols))


def http():
    """Capa HTTP: variantes de ruta, metodo y esquema de auth. Se compara contra app.py
    corriendo en este mismo proceso con el mismo token (no contra model.py)."""
    import asyncio
    import os
    import httpx
    from fuzz import TOKEN
    os.environ["TEAM_TOKEN"] = TOKEN
    from app import app as nuestro

    auth = {"ok": f"Bearer {TOKEN}", "sin": "", "minus": f"bearer {TOKEN}"}
    pasos = [  # (metodo, ruta, auth, manda PING)
        ("GET", "/health", "sin", False), ("GET", "/__reset", "ok", False),
        ("GET", "/__reset", "sin", False), ("POST", "/msg/", "ok", True),
        ("POST", "/MSG", "ok", True), ("PUT", "/msg", "ok", True),
        ("POST", "/msg?x=1", "ok", True), ("POST", "/msg", "minus", True),
        ("DELETE", "/nope", "sin", False), ("POST", "/health", "ok", False),
    ]

    async def local(metodo, ruta, hdr, body):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=nuestro), base_url="http://t") as cl:
            r = await cl.request(metodo, ruta, headers=hdr, json=body)
            return r.status_code, _safe_json(r)

    cols = (("REQUEST", 30), ("ORIGINAL", 40), ("NUESTRO APP", 34), ("", 9))
    print("\n=== 11) Capa HTTP: rutas, metodos y esquema de auth ===\n")
    print(encabezado(cols))
    for metodo, ruta, a_, ping in pasos:
        hdr = {"Authorization": auth[a_]}
        body = {"m": "PING;64"} if ping else None
        _pace()
        r = _client.request(metodo, ruta, headers=hdr, json=body)
        orig = (r.status_code, _safe_json(r))
        if r.status_code == 429:
            print("\nRATE-LIMIT de infra: se corta para no seguir gastando.")
            return
        que = f"{metodo} {ruta} ({'token ' + a_ if a_ != 'sin' else 'sin token'})"
        _log("v2-http", body["m"] if body else None, orig[0], orig[1], r.headers.get("X-Req"),
             f"v2: que responde {que}", extra={"ruta": f"{metodo} {ruta}", "auth": a_})
        mio = asyncio.run(local(metodo, ruta, hdr, body))
        igual = orig == mio
        print(fila(cols, que, resumen(*orig), "=" if igual else resumen(*mio), "OK" if igual else "DIFERENTE"))
    print(regla(cols))


if __name__ == "__main__":
    import sys
    fases = {"umbral": umbral, "replay": replay, "anula": anula, "meta": meta, "supuestos": supuestos, "afinar": afinar, "anula-limite": anula_limite, "titular": titular, "variantes": variantes, "entrada": entrada, "http": http}
    print("Incidente FR-0153: sondas contra el original (log: experimentos.jsonl)")
    for nombre in (sys.argv[1:] or fases):
        fases[nombre]()

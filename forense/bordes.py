"""
bordes.py - Bateria de casos borde contra el ORIGINAL (incidente FR-0153).

Cada caso arranca con /__reset y se loguea en experimentos.jsonl con su hipotesis.
Por cada paso compara:
  - MODELO: lo que responde nuestro model.py (huecos del reemplazo).
  - V1    : lo que respondia el original al capturar el baseline (bordes_v1.jsonl).
            Si el baseline no existe, esta corrida lo crea. Despues del deploy de la
            v2, cada CAMBIO es candidato a uno de los 3 cambios del ticket.

  TOKEN=<token> python -m forense.bordes
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python -m forense.bordes"
"""
import json
import os

from forense.fuzz import _client, _log, _pace, _safe_json, reset, send
import model
from compare import bodies_equal
from forense.tabla import encabezado, fila, regla, resumen

# capturado a las 15:58, ya con la v2 desplegada (FR-0153): es la foto de la v2
BASELINE = os.environ.get("BASELINE", "datos/bordes_v2.jsonl")
COLS = (("CASO", 14), ("MENSAJE", 32), ("RESPUESTA DEL ORIGINAL", 48), ("MODELO", 9), ("V1", 8))


def c(payload):
    """Mensaje con su control correcto: pasa la integridad y prueba lo que sigue."""
    return f"{payload};{model._checksum(payload)}"


def raw(body):
    """Cuerpo crudo (no {"m": ...}) para probar la entrada."""
    return ("raw", body)


BASE = [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;1000")]  # AC-0001 con 1000, AC-0002 con 0

# (caso, hipotesis, pasos). El ultimo paso es la sonda; los anteriores preparan el estado.
CASOS = [
    # --- montos ---
    ("monto-0", "DEPOSITO con monto 0 da E303", BASE + [c("DEPOSITO;AC-0001;0")]),
    ("monto-neg", "DEPOSITO con monto negativo da E303", BASE + [c("DEPOSITO;AC-0001;-5")]),
    ("monto-texto", "DEPOSITO con monto no numerico da E303", BASE + [c("DEPOSITO;AC-0001;abc")]),
    ("monto-decimal", "DEPOSITO con monto decimal: E303 o se acepta", BASE + [c("DEPOSITO;AC-0001;1.5")]),
    ("monto-grande", "DEPOSITO tiene limite propio o no", BASE + [c("DEPOSITO;AC-0001;999999")]),
    ("monto-vs-cta", "orden: monto invalido (E303) antes que cuenta inexistente (E401)",
     BASE + [c("DEPOSITO;AC-9999;0")]),
    ("transf-0", "TRANSFER con monto 0 da E303", BASE + [c("TRANSFER;AC-0001;AC-0002;0")]),
    ("transf-neg", "TRANSFER con monto negativo da E303", BASE + [c("TRANSFER;AC-0001;AC-0002;-5")]),
    # --- umbral y orden de TRANSFER ---
    ("umbral", "umbral exacto del limite de TRANSFER (entre 100000 y 120000)",
     [c("ALTA;Ana"), c("ALTA;Beto"), c("DEPOSITO;AC-0001;900000"),
      c("TRANSFER;AC-0001;AC-0002;100001"), c("TRANSFER;AC-0001;AC-0002;110000"),
      c("TRANSFER;AC-0001;AC-0002;119999")]),
    ("lim-vs-saldo", "orden: limite (E506) antes que saldo insuficiente (E507)",
     BASE + [c("TRANSFER;AC-0001;AC-0002;150000")]),
    ("lim-vs-cta", "orden: cuenta inexistente (E401) antes que limite (E506)",
     BASE + [c("TRANSFER;AC-9999;AC-0001;150000")]),
    ("transf-misma", "TRANSFER a la misma cuenta", BASE + [c("TRANSFER;AC-0001;AC-0001;100"),
                                                        c("CONSULTA;AC-0001")]),
    ("transf-exacto", "TRANSFER por el saldo exacto pasa", BASE + [c("TRANSFER;AC-0001;AC-0002;1000"),
                                                                c("CONSULTA;AC-0001")]),
    # --- ANULA ---
    ("anula-inex", "ANULA sobre operacion inexistente", BASE + [c("ANULA;OP-9999")]),
    ("anula-dep", "ANULA de un DEPOSITO revierte el saldo", BASE + [c("ANULA;OP-0001"),
                                                                  c("CONSULTA;AC-0001")]),
    ("anula-negativo", "ANULA de un DEPOSITO cuyo dinero ya se transfirio: saldo negativo o error",
     BASE + [c("TRANSFER;AC-0001;AC-0002;1000"), c("ANULA;OP-0001"), c("CONSULTA;AC-0001")]),
    ("anula-mal-id", "ANULA con id que no es OP-####", BASE + [c("ANULA;XYZ")]),
    # --- integridad y forma del mensaje ---
    ("sin-control", "mensaje sin ';' da E103", ["ZZZ"]),
    ("ping-solo", "PING sin campos", ["PING"]),
    ("ping-aridad", "PING con dos campos", ["PING;1;2"]),
    ("ping-ctrl", "PING no valida el control", ["PING;0", "PING;XX"]),
    ("m-vacio", "m vacio", [""]),
    ("solo-sep", "m es solo ';'", [";"]),
    ("ctrl-neg", "control negativo", BASE + ["CONSULTA;AC-0001;-14"]),
    ("ctrl-ceros", "control con ceros a la izquierda (014)", BASE + ["CONSULTA;AC-0001;014"]),
    ("ctrl-mas97", "control + 97 (111) equivale a 14 o no", BASE + ["CONSULTA;AC-0001;111"]),
    ("ctrl-espacio", "control con espacio (' 14')", BASE + ["CONSULTA;AC-0001; 14"]),
    ("cmd-minus", "comando en minusculas con control valido", [c("alta;Ana")]),
    # --- caracteres que el checksum no tiene confirmados ---
    ("alta-vacio", "ALTA con nombre vacio", [c("ALTA;")]),
    ("alta-espacio", "ALTA con espacio en el nombre: el checksum lo descarta", [c("ALTA;Ana Maria")]),
    ("alta-enie", "ALTA con ñ y tilde: el checksum los descarta", [c("ALTA;Muñoz")]),
    ("cta-minus", "CONSULTA con la cuenta en minusculas", BASE + [c("CONSULTA;ac-0001")]),
    # --- cuerpo del request ---
    ("body-nojson", "cuerpo que no es JSON", [raw("hola")]),
    ("body-sin-m", "JSON sin la clave m", [raw('{"x": "PING;64"}')]),
    ("body-m-num", "m no es string", [raw('{"m": 5}')]),
    ("body-vacio", "cuerpo vacio", [raw("")]),
]


def _original(paso, seq, hipotesis):
    if isinstance(paso, tuple):
        _pace()
        r = _client.post("/msg", content=paso[1].encode(), headers={"content-type": "application/json"})
        resp = _safe_json(r)
        _log(seq, None, r.status_code, resp, r.headers.get("X-Req"), hipotesis,
             extra={"request": paso[1]})
        return r.status_code, resp
    st, resp, _ = send(paso, seq=seq, hipotesis=hipotesis)
    return st, resp


def _modelo(paso, estado):
    body = paso[1].encode() if isinstance(paso, tuple) else json.dumps({"m": paso}).encode()
    try:
        (st, _h, rbody), estado = model.respond("POST", "/msg", "", {}, body, estado)
    except Exception as e:  # el modelo se cae: uvicorn responderia 500
        return 500, f"Internal Server Error ({type(e).__name__})", estado
    try:
        return st, json.loads(rbody), estado
    except Exception:
        return st, rbody.decode(), estado


def _igual(a, b):
    return a[0] == b[0] and bodies_equal(json.dumps(a[1]).encode(), json.dumps(b[1]).encode())


if __name__ == "__main__":
    previo = {}
    if os.path.exists(BASELINE):
        for l in open(BASELINE, encoding="utf-8"):
            r = json.loads(l)
            previo[(r["caso"], r["paso"])] = (r["status"], r["response"])
    capturar = not previo
    print(f"Casos borde contra el original: {_client.base_url}")
    print(f"Log: experimentos.jsonl | V1: {BASELINE} "
          f"({'se crea en esta corrida' if capturar else 'se compara contra el'})")
    print("MODELO: '=' si model.py responde igual. V1: '=' si el original responde como al capturar.\n")
    print(encabezado(COLS))

    nuevo, difs, n_mod, n_v1 = [], [], 0, 0
    for k, (caso, hip, pasos) in enumerate(CASOS):
        if k:
            print(regla(COLS))
        reset()
        estado = model.initial_state()
        for j, paso in enumerate(pasos, 1):
            es_sonda = j == len(pasos)
            seq = f"bordes-{caso}"
            orig = _original(paso, seq, hip if es_sonda else f"preparar estado para: {hip}")
            *mod, estado = _modelo(paso, estado)
            v1 = previo.get((caso, j))
            nuevo.append({"caso": caso, "paso": j, "request": paso[1] if isinstance(paso, tuple) else paso,
                          "status": orig[0], "response": orig[1]})
            ok_mod = _igual(orig, mod)
            col_v1 = "-" if v1 is None else ("=" if _igual(orig, v1) else "CAMBIO")
            n_mod += not ok_mod
            n_v1 += col_v1 == "CAMBIO"
            texto = paso[1] if isinstance(paso, tuple) else paso
            print(fila(COLS, caso if j == 1 else "", repr(texto), resumen(*orig),
                       "=" if ok_mod else "DIFERENTE", col_v1))
            if not ok_mod:
                print(fila(COLS, "", "", "modelo: " + resumen(*mod), "", ""))
                difs.append(("MODELO", caso, texto, orig, tuple(mod)))
            if col_v1 == "CAMBIO":
                print(fila(COLS, "", "", "v1    : " + resumen(*v1), "", ""))
                difs.append(("V1", caso, texto, orig, v1))
    print(regla(COLS))

    if capturar:
        with open(BASELINE, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in nuevo)
        print(f"\nBaseline V1 guardado en {BASELINE} ({len(nuevo)} respuestas).")
    print(f"\nModelo distinto del original: {n_mod} paso(s)")
    if not capturar:
        print(f"Original distinto de V1     : {n_v1} paso(s)")
    # la tabla corta los textos largos: las diferencias van completas abajo
    for tipo, caso, texto, orig, otro in difs:
        print(f"\n{tipo} {caso} {texto!r}")
        print(f"  original: {orig[0]} {json.dumps(orig[1], ensure_ascii=False)}")
        print(f"  {'modelo' if tipo == 'MODELO' else 'v1    '}  : {otro[0]} {json.dumps(otro[1], ensure_ascii=False)}")

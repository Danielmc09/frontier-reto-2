"""
model.py - Comportamiento PURO del reemplazo (Reto 2 - "La caja negra").

El servicio es un interprete de comandos bancario sobre POST /msg con cuerpo
{"m": "CMD;arg1;...;control"}. Toda la logica observada vive aqui. app.py solo
mueve bytes. El evaluador compara STATUS + CUERPO (JSON por claves); los headers
NO se comparan.

Estado: verificado contra pruebas/ejemplos.jsonl (20/20, test_control.py).
Lo PENDIENTE y marcado TODO(forense):
  - Rutas != /msg, body no-JSON, monto no numerico, orden fino de errores,
    ANULA sobre op inexistente, umbral exacto de TRANSFER.
"""
import json
import re

_H = [(b"content-type", b"application/json; charset=utf-8")]

# arity = numero de campos tras el comando, INCLUYENDO el control
ARITY = {"PING": 1, "ALTA": 2, "CONSULTA": 2, "DEPOSITO": 3, "TRANSFER": 4, "ANULA": 2}
PING_VALIDA_CONTROL = False  # "responde pong aunque el ultimo campo no sea numero"
# v2 (FR-0153): 50000 pasa, 50001 da E506. En la v1 el limite era 100000.
LIMITE_TRANSFER = 50000
# control bien formado: 1 o 2 digitos. Confirmado v2: "0", "00", "99" -> bien formados
# (E202 si no coinciden); "014", "111", " 14", "-14", "5X" -> E201.
_CONTROL = re.compile(r"^[0-9]{1,2}$")
# monto valido: entero positivo sin ceros a la izquierda.
# Confirmado v2: "0", "-5", "abc", "1.5", "05" -> E303.
# Tope: hasta 10 digitos (9999999999 pasa, 10000000000 da E303, en DEPOSITO y TRANSFER).
_MONTO = re.compile(r"^[1-9][0-9]{0,9}$")

# --- Checksum del control: ISO 7064 MOD 97-10 (el del IBAN) sobre el payload ---
# El payload completo 'CMD;args' se pasa a digitos: los digitos quedan, cada letra
# (sin distinguir mayusculas) se vuelve su posicion en el alfabeto en decimal
# (A=1 ... Z=26, asi que J-Z ocupan dos digitos) y el resto se descarta.
# control = 98 - (N*100 mod 97), siempre en [2, 98].
# CONFIRMADO: 85/85 pares de experimentos.jsonl y ejemplos. Que se descarte todo
# caracter no alfanumerico (o no ASCII) esta probado para ';', '-', espacio y 'ñ'
# ('ALTA;Ana Maria' y 'ALTA;Muñoz' pasan la integridad en la v2, bordes_v2.jsonl).
def _checksum(payload: str) -> int:
    digitos = "".join(ch if ch.isdigit() else str(ord(ch) - 64)
                      for ch in payload.upper() if ch.isascii() and ch.isalnum())
    return 98 - int(digitos + "00") % 97


def initial_state() -> dict:
    return {"cuentas": {}, "titulares": {}, "ops": {}, "next_cuenta": 1, "next_op": 1}


def _b(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _r(status, obj):
    return (status, _H, _b(obj))


def _err(code, msg, status):
    return _r(status, {"error": code, "mensaje": msg})


def _distancia(a: str, b: str) -> int:
    """Levenshtein: inserciones, borrados y sustituciones."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _e301(cmd: str):
    """E301 con 'sugerencia' si un comando conocido esta a distancia <= 2 (confirmado:
    ATLA/XLTB/TRANSFERIR sugieren, XYZA a 3 y SALDOS a 4 no). Empate: el primero en ARITY
    (supuesto)."""
    mejor = min(ARITY, key=lambda k: _distancia(cmd, k))   # min devuelve el primero en empate
    d = _distancia(cmd, mejor)
    cuerpo = {"error": "E301", "mensaje": "comando desconocido "}   # OJO: espacio final
    if d <= 2:
        cuerpo["sugerencia"] = mejor
    return _r(400, cuerpo)


def _saldo(centavos: int) -> str:
    """v2: el saldo sale como string con dos decimales, en unidades de 100 (40000 -> "400.00")."""
    signo = "-" if centavos < 0 else ""
    return f"{signo}{abs(centavos) // 100}.{abs(centavos) % 100:02d}"


def control_valido(payload: str, control_int: int) -> bool:
    """payload = 'CMD;arg1;...' (sin el control), CMD en mayusculas."""
    return control_int == _checksum(payload)


def respond(method, path, query, headers, body, state):
    """Superficie del servicio. Conocido: POST /msg. Resto: TODO(forense)."""
    if method == "POST" and path == "/msg":
        return _msg(body, state), state
    # Confirmado por fuzzing: cualquier otra ruta/metodo -> 404 E404.
    return _err("E404", "ruta desconocida", 404), state


def _msg(body, st):
    # --- cuerpo: confirmado v2 (bordes_v2.jsonl): no-JSON o vacio -> E100; sin 'm' o 'm'
    # que no es string -> E102. Un JSON que no es objeto -> E102 es supuesto.
    try:
        data = json.loads(body)
    except Exception:
        return _err("E100", "json inválido", 400)
    if not isinstance(data, dict) or not isinstance(data.get("m"), str):
        return _err("E102", "falta m", 400)

    partes = data["m"].split(";")
    cmd_up = partes[0].upper()          # comandos case-insensitive
    args = partes[1:]

    # --- forma: sin ';' no hay campo de control -> E103 ('ZZZ', '', y tambien 'PING' solo).
    # Algun segmento vacio -> E104 (';', 'ALTA;;85' y 'PING;', confirmado).
    if not args:
        return _err("E103", "falta control", 400)
    if "" in partes:
        return _err("E104", "segmento vacío", 400)

    # --- integridad antes que comando y aridad: control = ultimo campo, checksum sobre
    # todo lo anterior. Confirmado: 'ZZZ;1' -> E202 (no E301), 'ALTA;a;b;c;0' -> E202 (no E302).
    if not (cmd_up == "PING" and not PING_VALIDA_CONTROL):
        if not _CONTROL.match(args[-1]):
            return _err("E201", "control mal formado", 400)
        payload = ";".join([cmd_up] + args[:-1])
        if not control_valido(payload, int(args[-1])):
            return _err("E202", "control inválido", 400)

    if cmd_up not in ARITY:
        return _e301(cmd_up)
    if len(args) != ARITY[cmd_up]:
        return _err("E302", "aridad inválida", 400)

    return _dispatch(cmd_up, args, st)


def _dispatch(cmd, args, st):
    if cmd == "PING":
        return _r(200, {"pong": True})

    if cmd == "ALTA":
        acc = f"AC-{st['next_cuenta']:04d}"
        st["next_cuenta"] += 1
        st["cuentas"][acc] = 0
        st["titulares"][acc] = args[0]
        return _r(201, {"cuentaId": acc})

    if cmd == "CONSULTA":
        acc = args[0]
        if acc not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)
        return _r(200, {"cuenta_id": acc, "saldo": _saldo(st["cuentas"][acc])})

    if cmd == "DEPOSITO":
        acc, monto_raw = args[0], args[1]
        if not _MONTO.match(monto_raw):     # monto antes que cuenta: 'DEPOSITO;AC-9999;0' -> E303
            return _err("E303", "monto inválido", 400)
        if acc not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)
        monto = int(monto_raw)
        st["cuentas"][acc] += monto
        op = f"OP-{st['next_op']:04d}"; st["next_op"] += 1
        st["ops"][op] = {"tipo": "DEPOSITO", "acc": acc, "monto": monto, "anulada": False}
        return _r(200, {"status": "recieved", "operacionId": op})

    if cmd == "TRANSFER":
        o, d, monto_raw = args[0], args[1], args[2]
        if not _MONTO.match(monto_raw):
            return _err("E303", "monto inválido", 400)
        if o == d:                          # despues de E303, antes que E401 y E506 (confirmado)
            return _err("E304", "origen y destino iguales", 400)
        if o not in st["cuentas"] or d not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)   # antes que E506 (lim-vs-cta)
        monto = int(monto_raw)
        # el limite no aplica entre cuentas del mismo titular, nombre exacto con mayusculas
        # (confirmado: Ana->Ana 60000 pasa, Ana->ana da E506; incidente.py titular)
        if monto > LIMITE_TRANSFER and st["titulares"][o] != st["titulares"][d]:
            return _err("E506", "límite excedido", 422)
        if st["cuentas"][o] < monto:
            return _err("E507", "saldo insuficiente", 422)
        st["cuentas"][o] -= monto
        st["cuentas"][d] += monto
        op = f"OP-{st['next_op']:04d}"; st["next_op"] += 1
        st["ops"][op] = {"tipo": "TRANSFER", "o": o, "d": d, "monto": monto, "anulada": False}
        return _r(200, {"status": "recieved", "operacionId": op})

    if cmd == "ANULA":
        op = args[0]
        rec = st["ops"].get(op)
        if rec is None:
            return _err("E402", "operación inexistente", 404)
        if rec["anulada"]:
            return _r(200, {"ok": False, "motivo": "ya anulada"})
        _revertir(rec, st)
        rec["anulada"] = True
        return _r(200, {"ok": True, "anulada": op})

    return _err("E301", "comando desconocido ", 400)


def _revertir(rec, st):
    if rec["tipo"] == "DEPOSITO":
        st["cuentas"][rec["acc"]] -= rec["monto"]
    elif rec["tipo"] == "TRANSFER":
        st["cuentas"][rec["d"]] -= rec["monto"]
        st["cuentas"][rec["o"]] += rec["monto"]

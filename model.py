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

_H = [(b"content-type", b"application/json; charset=utf-8")]

# arity = numero de campos tras el comando, INCLUYENDO el control
ARITY = {"PING": 1, "ALTA": 2, "CONSULTA": 2, "DEPOSITO": 3, "TRANSFER": 4, "ANULA": 2}
PING_VALIDA_CONTROL = False  # "responde pong aunque el ultimo campo no sea numero"
LIMITE_TRANSFER = 100000     # probable: 100000 ok, 120000 E506. Acotar por fuzzing.

# --- Checksum del control: ISO 7064 MOD 97-10 (el del IBAN) sobre el payload ---
# El payload completo 'CMD;args' se pasa a digitos: los digitos quedan, cada letra
# (sin distinguir mayusculas) se vuelve su posicion en el alfabeto en decimal
# (A=1 ... Z=26, asi que J-Z ocupan dos digitos) y el resto se descarta.
# control = 98 - (N*100 mod 97), siempre en [2, 98].
# CONFIRMADO: 85/85 pares de experimentos.jsonl y ejemplos. Que se descarte todo
# caracter no alfanumerico esta probado para ';' y '-'; para el resto es supuesto.
def _checksum(payload: str) -> int:
    digitos = "".join(ch if ch.isdigit() else str(ord(ch) - 64)
                      for ch in payload.upper() if ch.isascii() and ch.isalnum())
    return 98 - int(digitos + "00") % 97


def initial_state() -> dict:
    return {"cuentas": {}, "ops": {}, "next_cuenta": 1, "next_op": 1}


def _b(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _r(status, obj):
    return (status, _H, _b(obj))


def _err(code, msg, status):
    return _r(status, {"error": code, "mensaje": msg})


def _es_entero(s: str) -> bool:
    try:
        int(s); return True
    except Exception:
        return False


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
    try:
        data = json.loads(body) if body else {}
    except Exception:
        return _err("E201", "control mal formado", 400)  # TODO(forense): body no-JSON

    m = data.get("m", "")
    partes = m.split(";")
    cmd_up = partes[0].upper()          # comandos case-insensitive
    args = partes[1:]

    # --- integridad PRIMERO: control = ultimo campo, checksum sobre todo lo anterior.
    # Confirmado: 'ZZZ;1' -> E202 (no E301) y 'ALTA;a;b;c;0' -> E202 (no E302).
    # Confirmado: sin ';' no hay campo de control -> E103 ('ZZZ').
    if not (cmd_up == "PING" and not PING_VALIDA_CONTROL):
        if not args:
            return _err("E103", "falta control", 400)
        if not _es_entero(args[-1]):
            return _err("E201", "control mal formado", 400)
        payload = ";".join([cmd_up] + args[:-1])
        if not control_valido(payload, int(args[-1])):
            return _err("E202", "control inválido", 400)

    if cmd_up not in ARITY:
        return _err("E301", "comando desconocido ", 400)   # OJO: espacio final
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
        return _r(201, {"cuentaId": acc})

    if cmd == "CONSULTA":
        acc = args[0]
        if acc not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)
        return _r(200, {"cuenta_id": acc, "saldo": st["cuentas"][acc]})

    if cmd == "DEPOSITO":
        acc, monto_raw = args[0], args[1]
        if not _es_entero(monto_raw):
            return _err("E201", "control mal formado", 400)  # TODO(forense): error real de monto
        if acc not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)
        monto = int(monto_raw)
        st["cuentas"][acc] += monto
        op = f"OP-{st['next_op']:04d}"; st["next_op"] += 1
        st["ops"][op] = {"tipo": "DEPOSITO", "acc": acc, "monto": monto, "anulada": False}
        return _r(200, {"status": "recieved", "operacionId": op})

    if cmd == "TRANSFER":
        o, d, monto_raw = args[0], args[1], args[2]
        if not _es_entero(monto_raw):
            return _err("E201", "control mal formado", 400)  # TODO(forense)
        if o not in st["cuentas"] or d not in st["cuentas"]:
            return _err("E401", "cuenta inexistente", 404)   # TODO(forense): orden vs E506/E507
        monto = int(monto_raw)
        if monto > LIMITE_TRANSFER:
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
            return _err("E401", "cuenta inexistente", 404)   # TODO(forense): op inexistente
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

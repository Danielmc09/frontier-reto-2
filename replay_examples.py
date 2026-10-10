"""
replay_examples.py - Verifica el interprete (model.respond) contra
pruebas/ejemplos.jsonl: reset -> manda cada request en orden -> compara
status + cuerpo con la regla del evaluador.

El control (checksum) aun no esta reversado, asi que poblamos un oraculo
PROVISIONAL con los controles validos de los propios ejemplos. Esto solo
valida que el INTERPRETE es correcto; el oraculo se reemplaza por el
checksum real (control_valido) antes de servir al set oculto.

Uso:  EX=pruebas/ejemplos.jsonl python replay_examples.py
"""
import json
import os
import model
from compare import resp_equal

EX = os.environ.get("EX", "pruebas/ejemplos.jsonl")

lines = [json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()]

# --- construir oraculo de control desde los ejemplos (payload -> control valido) ---
oraculo = {}
for rec in lines:
    m = rec["request"]["m"]
    partes = m.split(";")
    cmd_up = partes[0].upper()
    args = partes[1:]
    if cmd_up == "PING" or len(args) != model.ARITY.get(cmd_up, -1):
        continue
    ctrl = args[-1]
    if not ctrl.lstrip("-").isdigit():
        continue
    err = rec["response"].get("error") if isinstance(rec["response"], dict) else None
    if err in ("E201", "E202"):
        continue  # control rechazado: no es un control valido
    oraculo[";".join([cmd_up] + args[:-1])] = int(ctrl)

model.CONTROL_ORACLE = oraculo

# --- replay de la secuencia ---
st = model.initial_state()
ok = 0
misses = []
for rec in lines:
    body = json.dumps(rec["request"]).encode("utf-8")
    (status, _h, rbody), st = model.respond("POST", "/msg", "", {}, body, st)
    exp_body = json.dumps(rec["response"]).encode("utf-8")
    if resp_equal(rec["status"], exp_body, status, rbody):
        ok += 1
    else:
        misses.append((rec["n"], rec["request"]["m"], rec["status"],
                       rec["response"], status, json.loads(rbody.decode("utf-8"))))

print(f"{ok}/{len(lines)} ejemplos reproducidos")
for n, m, es, eb, gs, gb in misses:
    print(f"  MISS n={n} m={m!r}")
    print(f"       esperado: {es} {eb}")
    print(f"       obtuve  : {gs} {gb}")

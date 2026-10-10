"""
replay_examples.py - Verifica el interprete (model.respond) contra
pruebas/ejemplos.jsonl: reset -> manda cada request en orden -> compara
status + cuerpo con la regla del evaluador.

El control se valida con el checksum real (model.control_valido), asi que
esto prueba interprete y checksum juntos.

Uso:  EX=pruebas/ejemplos.jsonl python replay_examples.py
"""
import json
import os
import model
from compare import resp_equal

EX = os.environ.get("EX", "pruebas/ejemplos.jsonl")

lines = [json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()]

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

"""
replay_examples.py - Verifica el interprete (model.respond) contra
pruebas/ejemplos.jsonl: reset -> manda cada request en orden -> compara
status + cuerpo con la regla del evaluador.

El control se valida con el checksum real (model.control_valido), asi que
esto prueba interprete y checksum juntos.

Uso:  python -m forense.replay_examples   (EX=pruebas/ejemplos.jsonl para la v1)
"""
import json
import os
import model
from compare import resp_equal
from forense.tabla import encabezado, fila, regla, resumen

# la v2 es la vigente (FR-0153); los ejemplos de la v1 siguen en pruebas/ejemplos.jsonl
EX = os.environ.get("EX", "pruebas/ejemplos_v2.jsonl")
COLS = (("N", 3), ("MENSAJE", 34), ("RESPUESTA ESPERADA (original)", 56), ("RESULTADO", 9))

lines = [json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()]

# --- replay de la secuencia: una fila por ejemplo, con lo que compara ---
st = model.initial_state()
ok = 0
misses = []
print(f"Replay de {EX} contra model.respond, en orden y desde el estado inicial.")
print("Compara status + cuerpo del modelo contra lo que respondio el original.\n")
print(encabezado(COLS))
for rec in lines:
    m = rec["request"]["m"]
    body = json.dumps(rec["request"]).encode("utf-8")
    (status, _h, rbody), st = model.respond("POST", "/msg", "", {}, body, st)
    esperado = resumen(rec["status"], rec["response"])
    igual = resp_equal(rec["status"], json.dumps(rec["response"]).encode("utf-8"), status, rbody)
    if igual:
        ok += 1
        print(fila(COLS, rec["n"], m, esperado, "OK"))
    else:
        obtenido = resumen(status, json.loads(rbody))
        misses.append((rec["n"], m, esperado, obtenido))
        print(fila(COLS, rec["n"], m, "original: " + esperado, "MISS"))
        print(fila(COLS, "", "", "modelo  : " + obtenido, ""))
print(regla(COLS))

# la tabla corta los textos largos: los MISS van completos abajo
for n, m, esperado, obtenido in misses:
    print(f"\nMISS n={n} {m!r}\n  original: {esperado}\n  modelo  : {obtenido}")

print(f"\n{ok}/{len(lines)} ejemplos reproducidos")

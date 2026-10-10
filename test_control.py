"""Checksum del control contra la evidencia: controles.jsonl + los 20 ejemplos.

Uso:  python test_control.py
"""
import json
import subprocess
import sys
import model

pares = [json.loads(l) for l in open("controles.jsonl", encoding="utf-8") if l.strip()]
pares += [
    {"payload": "DEPOSITO;AC-0001;250000", "control": 86},
    {"payload": "TRANSFER;AC-0001;AC-0002;40000", "control": 86},
    {"payload": "ANULA;OP-0003", "control": 66},
    {"payload": "CONSULTA;000-", "control": 10},
    {"payload": "CONSULTA;ZZZZ", "control": 19},
    {"payload": "CONSULTA;000z", "control": 47},
]
for p in pares:
    c = p["control"]
    assert model.control_valido(p["payload"], c), p
    assert not model.control_valido(p["payload"], c % 97 + 2), p  # otro control: E202

# orden de errores: la integridad va antes que comando y aridad (differential.py, seq3)
def error(m):
    body = json.dumps({"m": m}).encode()
    (_, _, rbody), _ = model.respond("POST", "/msg", "", {}, body, model.initial_state())
    return json.loads(rbody).get("error")

assert error("ZZZ;1") == "E202"
assert error("ALTA;a;b;c;0") == "E202"
assert error("ZZZ;54") == "E301"
assert error("ALTA;a;b;c;18") == "E302"

out = subprocess.run([sys.executable, "replay_examples.py"], capture_output=True, text=True).stdout
assert out.startswith("20/20"), out
print(f"ok: {len(pares)} pares + 20/20 ejemplos")

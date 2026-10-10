"""
cambio3.py - Candidatos al cambio 3 (FR-0153) contra la V1 del servicio.

Manda una tira compacta (un solo reset) con los comportamientos que solo vimos en la v2
y la compara contra model.py, que hoy reproduce la v2. Lo que la v1 responde distinto,
descontando los cambios 1 (formato del saldo) y 2 (limite 100000 -> 50000), es el cambio 3.
Todo se loguea en experimentos.jsonl.

  BASE_URL=<url de la v1> TOKEN=<token> python -m forense.cambio3
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e BASE_URL="<url v1>" -e TOKEN="$TOKEN" \
  #   python:3.12-slim sh -c "pip install -q httpx && python -m forense.cambio3"
"""
import json

from forense.fuzz import _client, reset
from forense.bordes import _igual, _modelo, _original, raw
import model
from forense.tabla import encabezado, fila, regla, resumen


def c(payload):
    return f"{payload};{model._checksum(payload)}"


# (candidato, paso). Sin cuentas creadas hasta el bloque 'titular'.
PASOS = [
    ("E103 forma", "ZZZ"), ("E103 forma", "PING"),
    ("E104 vacio", ";"), ("E104 vacio", "ALTA;;85"), ("E104 vacio", "PING;"),
    ("E100/E102 body", raw("hola")), ("E100/E102 body", raw('{"x": "PING;64"}')),
    ("E100/E102 body", raw('{"m": 5}')), ("E100/E102 body", raw("")),
    ("control", "CONSULTA;AC-0001;014"), ("control", "CONSULTA;AC-0001;111"),
    ("control", "CONSULTA;AC-0001;-14"), ("control", "CONSULTA;AC-0001; 14"),
    ("control", "CONSULTA;AC-0001;00"),
    ("sugerencia", c("altas;AC-0001")),
    ("tope monto", c("TRANSFER;AC-0001;AC-0002;10000000000")),
    ("E303 monto", c("DEPOSITO;AC-0001;05")), ("E303 monto", c("DEPOSITO;AC-0001;-5")),
    ("E304 misma", c("TRANSFER;AC-9999;AC-9999;100")),
    # titular: 150000 supera el limite de las dos versiones (v1 100000, v2 50000)
    ("titular", c("ALTA;Ana")), ("titular", c("ALTA;Ana")),
    ("titular", c("DEPOSITO;AC-0001;300000")),
    ("titular", c("TRANSFER;AC-0001;AC-0002;150000")),
    ("E304 misma", c("TRANSFER;AC-0001;AC-0001;100")),
    # saldo negativo: anular el deposito cuando ya se transfirio la mitad
    ("saldo negativo", c("ANULA;OP-0001")), ("saldo negativo", c("CONSULTA;AC-0001")),
]

if __name__ == "__main__":
    cols = (("CANDIDATO", 15), ("MENSAJE", 34), ("V1 (ESTE SERVIDOR)", 36), ("V2 (MODELO)", 30))
    print(f"Candidatos al cambio 3 contra: {_client.base_url}")
    print("V2 es lo que hace model.py (reproduce la v2). Descontar cambio 1 (saldo) y 2 (limite).\n")
    print(encabezado(cols))
    reset()
    st = model.initial_state()
    distintos = []
    for cand, paso in PASOS:
        orig = _original(paso, "v1-cambio3", f"v1: {cand} responde como la v2 (si no, es el cambio 3)")
        *mod, st = _modelo(paso, st)
        texto = paso[1] if isinstance(paso, tuple) else paso
        igual = _igual(orig, mod)
        print(fila(cols, cand, repr(texto), resumen(*orig), "=" if igual else resumen(*mod)))
        if not igual:
            distintos.append((cand, texto, orig, mod))
    print(regla(cols))
    print(f"\nDistintos de la v2: {len(distintos)} de {len(PASOS)}")
    for cand, texto, orig, mod in distintos:
        print(f"\n{cand}  {texto!r}\n  v1: {orig[0]} {json.dumps(orig[1], ensure_ascii=False)}"
              f"\n  v2: {mod[0]} {json.dumps(mod[1], ensure_ascii=False)}")

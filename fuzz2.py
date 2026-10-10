"""
fuzz2.py - Segunda tanda quirurgica para crackear el checksum del `control`.
Reusa la infra de fuzz.py (pacer, log a experimentos.jsonl).

  TOKEN=<tu token de la caja negra> python fuzz2.py
  # o en Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python fuzz2.py"

Diseño (experimentos controlados, cada grupo aisla una variable):
  - baseline_len : args todo-cero de distinta longitud -> efecto de la longitud / base.
  - pos_weight   : una 'A' en cada distancia (resto 0, longitud fija 7) -> peso de cada posicion.
  - modulus      : valores altos que fuerzan wrap -> revela el modulo (97 vs 100).
  - command_base : mismo arg, distinto comando -> base por comando.
  - guion_letras : valor del '-' y linealidad de letras altas.

Pegame la TABLA final a Claude.
"""
from fuzz import control_valido, reset   # usa el cliente/pacer/log de fuzz.py

GRUPOS = {
    "baseline_len": [
        "CONSULTA;0", "CONSULTA;00", "CONSULTA;000", "CONSULTA;0000",
        "CONSULTA;00000", "CONSULTA;000000", "CONSULTA;0000000",
    ],
    "pos_weight (A en cada distancia, len 7)": [
        "CONSULTA;000000A", "CONSULTA;00000A0", "CONSULTA;0000A00",
        "CONSULTA;000A000", "CONSULTA;00A0000", "CONSULTA;0A00000", "CONSULTA;A000000",
    ],
    "modulus (fuerza wrap)": [
        "CONSULTA;000Z", "CONSULTA;00ZZ", "CONSULTA;ZZZZ",
    ],
    "command_base (arg 0000)": [
        "ALTA;0000", "CONSULTA;0000", "ANULA;0000",
    ],
    "guion_letras": [
        "CONSULTA;000-", "CONSULTA;000J",
    ],
}

if __name__ == "__main__":
    reset()
    tabla = []
    for grupo, payloads in GRUPOS.items():
        print(f"\n== {grupo} ==")
        for p in payloads:
            c = control_valido(p)
            tabla.append((p, c))
            print(f"  {p:<22} -> {c}")
    print("\n== TABLA (pegasela a Claude) ==")
    for p, c in tabla:
        print(f"{p}\t{c}")

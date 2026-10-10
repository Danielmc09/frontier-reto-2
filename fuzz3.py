"""
fuzz3.py - Tanda FINAL para cerrar el checksum. Reusa fuzz.py. Corres VOS con tu token:

  TOKEN=<tu token de la caja negra> python fuzz3.py
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python fuzz3.py"

Pincha lo unico que falta:
  - valor de CADA letra (A-Z, y una muestra de minusculas) en la ultima posicion,
  - bases de los comandos que faltan (DEPOSITO, TRANSFER, y ALTA/ANULA cortos).

Pegame la TABLA final.
"""
import string
from fuzz import control_valido, reset

if __name__ == "__main__":
    reset()
    tabla = []

    print("== valor de letras (ultima posicion) ==")
    for L in string.ascii_uppercase:
        p = f"CONSULTA;000{L}"
        c = control_valido(p); tabla.append((p, c)); print(f"  {p} -> {c}")
    for L in ["a", "m", "z"]:   # muestra de minusculas (los nombres las usan)
        p = f"CONSULTA;000{L}"
        c = control_valido(p); tabla.append((p, c)); print(f"  {p} -> {c}")

    print("\n== bases por comando ==")
    for p in ["ALTA;0", "ANULA;0", "DEPOSITO;0;0", "TRANSFER;0;0;0"]:
        c = control_valido(p); tabla.append((p, c)); print(f"  {p} -> {c}")

    print("\n== TABLA (pegasela a Claude) ==")
    for p, c in tabla:
        print(f"{p}\t{c}")

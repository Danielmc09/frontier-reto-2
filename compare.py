"""
compare.py - Igualdad de respuestas segun la regla del evaluador:
  - mismo status, y
  - mismo cuerpo. Si ambos son JSON: claves de objeto en cualquier orden,
    arrays en el mismo orden, strings y numeros identicos. Si alguno no es
    JSON: texto exacto, caracter por caracter.
Los headers NO se comparan.
"""
import json


def bodies_equal(a: bytes, b: bytes) -> bool:
    try:
        ja = json.loads(a)
        jb = json.loads(b)
    except Exception:
        return a == b  # alguno no es JSON -> texto exacto
    return _json_eq(ja, jb)


def _json_eq(x, y) -> bool:
    # bool es subclase de int: tratar aparte para no igualar True con 1
    if isinstance(x, bool) or isinstance(y, bool):
        return x is y
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(_json_eq(x[k], y[k]) for k in x)
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(_json_eq(i, j) for i, j in zip(x, y))
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return x == y
    return x == y


def resp_equal(status_a, body_a, status_b, body_b) -> bool:
    return status_a == status_b and bodies_equal(body_a, body_b)

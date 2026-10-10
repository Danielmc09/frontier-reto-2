"""tabla.py - Salida en tabla para la terminal (replay_examples, differential, regresion)."""
import json


def fila(cols, *vals):
    """cols = (("TITULO", ancho), ...). Corta cada valor a su ancho."""
    return "  ".join(str(v)[:w].ljust(w) for v, (_, w) in zip(vals, cols))


def encabezado(cols):
    return fila(cols, *(n for n, _ in cols)) + "\n" + regla(cols)


def regla(cols):
    return "  ".join("-" * w for _, w in cols)


def resumen(status, body):
    """'400 E103 falta control' o '200 {"pong":true}': status + cuerpo corto."""
    if isinstance(body, dict) and "error" in body:
        return f"{status} {body['error']} {body.get('mensaje', '')}"
    if isinstance(body, (dict, list)):
        return f"{status} {json.dumps(body, ensure_ascii=False, separators=(',', ':'))}"
    return f"{status} {body}"

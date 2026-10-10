"""
regresion.py - Detector rapido del cambio de las 15:30 (~26 requests).
Corre un battery fijo contra el ORIGINAL y lo compara con el baseline conocido.
Reusa fuzz.py. Corres VOS con tu token de la caja negra:

  TOKEN=<tu token> python regresion.py
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python regresion.py"

Antes de las 15:30 debe decir SIN CAMBIOS. Despues, lista EXACTAMENTE que cambio
(comando, error, checksum, auth o ruta) para parchear model.py y redeployar.
"""
import json
import os
from fuzz import reset, send, _client
from compare import bodies_equal

EX = os.environ.get("EX", "pruebas/ejemplos.jsonl")

if __name__ == "__main__":
    difs = []

    # 1) los 20 ejemplos (semantica + estado + errores + checksum)
    reset()
    for rec in (json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()):
        st, resp, _ = send(rec["request"]["m"], seq="regresion", hipotesis="regresion ejemplos")
        same = (st == rec["status"]) and bodies_equal(
            json.dumps(resp).encode(), json.dumps(rec["response"]).encode())
        if not same:
            difs.append(f"ejemplo n={rec['n']} m={rec['request']['m']!r}: "
                        f"ahora {st} {resp} | baseline {rec['status']} {rec['response']}")

    # 2) auth y rutas (esperado confirmado por fuzzing)
    checks = [
        ("POST", "/msg", {"Authorization": ""}, {"m": "PING;64"},
         401, {"error": "E001", "mensaje": "no autorizado"}),
        ("GET", "/nope", None, None, 404, {"error": "E404", "mensaje": "ruta desconocida"}),
        ("GET", "/msg", None, None, 404, {"error": "E404", "mensaje": "ruta desconocida"}),
    ]
    for method, path, hdr, body, exp_st, exp_body in checks:
        r = _client.request(method, path, headers=hdr, json=body)
        try:
            rb = r.json()
        except Exception:
            rb = r.text
        if r.status_code != exp_st or rb != exp_body:
            difs.append(f"{method} {path}: ahora {r.status_code} {rb} | baseline {exp_st} {exp_body}")

    # 3) checksum: control valido (14) vs invalido (15) para CONSULTA;AC-0001
    reset()
    _, r_ok, _ = send("CONSULTA;AC-0001;14", seq="regresion", hipotesis="checksum valido")
    _, r_bad, _ = send("CONSULTA;AC-0001;15", seq="regresion", hipotesis="checksum invalido")
    ok_err = r_ok.get("error") if isinstance(r_ok, dict) else None
    bad_err = r_bad.get("error") if isinstance(r_bad, dict) else None
    if ok_err in ("E201", "E202") or bad_err != "E202":
        difs.append(f"checksum CONSULTA;AC-0001: control 14 -> {r_ok} ; control 15 -> {r_bad} "
                    f"(se esperaba 14 valido, 15 -> E202)")

    print()
    if difs:
        print("=== CAMBIO DETECTADO (parchear model.py y redeployar) ===")
        for d in difs:
            print("  -", d)
    else:
        print("=== SIN CAMBIOS (todo igual al baseline) ===")

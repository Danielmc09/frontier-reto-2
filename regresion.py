"""
regresion.py - Detector rapido del cambio de las 15:30 (~26 requests).
Corre un battery fijo contra el ORIGINAL y lo compara con el baseline conocido.
Reusa fuzz.py y loguea en regresion.jsonl (experimentos.jsonl ya se entrego).

  TOKEN=<tu token> python regresion.py
  # o Docker:
  # docker run --rm -v "$PWD":/app -w /app -e TOKEN="$TOKEN" python:3.12-slim \
  #   sh -c "pip install -q httpx && python regresion.py"

Antes de las 15:30 debe decir SIN CAMBIOS. Despues, lista EXACTAMENTE que cambio
(comando, error, checksum, auth o ruta) para parchear model.py y redeployar.
"""
import json
import os

# experimentos.jsonl ya se entrego: la regresion loguea aparte (fuzz.py lee LOG_PATH al importarse)
os.environ.setdefault("LOG_PATH", "regresion.jsonl")
from fuzz import reset, send, _client  # noqa: E402
from compare import bodies_equal
from tabla import encabezado, fila, regla, resumen

EX = os.environ.get("EX", "pruebas/ejemplos.jsonl")

COLS = (("BLOQUE", 9), ("CHEQUEO", 34), ("RESPUESTA ESPERADA (baseline)", 56), ("RESULTADO", 9))


if __name__ == "__main__":
    difs = []

    def mostrar(same, bloque, que, esperado, ahora):
        if same:
            print(fila(COLS, bloque, que, esperado, "OK"))
        else:
            difs.append((bloque, que, esperado, ahora))
            print(fila(COLS, bloque, que, "baseline: " + esperado, "CAMBIO"))
            print(fila(COLS, "", "", "ahora   : " + ahora, ""))

    print(f"Regresion contra el original: {_client.base_url}")
    print(f"Log de esta corrida: {os.environ['LOG_PATH']}")
    print("Compara lo que responde el original hoy contra lo que respondia antes.\n")
    print(encabezado(COLS))

    # 1) los 20 ejemplos (semantica + estado + errores + checksum)
    reset()
    for rec in (json.loads(l) for l in open(EX, encoding="utf-8") if l.strip()):
        st, resp, _ = send(rec["request"]["m"], seq="regresion", hipotesis="regresion ejemplos")
        same = (st == rec["status"]) and bodies_equal(
            json.dumps(resp).encode(), json.dumps(rec["response"]).encode())
        mostrar(same, f"ejemplo{rec['n']}", rec["request"]["m"],
                resumen(rec["status"], rec["response"]), resumen(st, resp))
    print(regla(COLS))

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
        same = r.status_code == exp_st and rb == exp_body
        mostrar(same, "auth/ruta", f"{method} {path}" + (" sin token" if hdr else ""),
                resumen(exp_st, exp_body), resumen(r.status_code, rb))
    print(regla(COLS))

    # 3) checksum: control valido (14) vs invalido (15) para CONSULTA;AC-0001
    reset()
    st_ok, r_ok, _ = send("CONSULTA;AC-0001;14", seq="regresion", hipotesis="checksum valido")
    st_bad, r_bad, _ = send("CONSULTA;AC-0001;15", seq="regresion", hipotesis="checksum invalido")
    ok_err = r_ok.get("error") if isinstance(r_ok, dict) else None
    bad_err = r_bad.get("error") if isinstance(r_bad, dict) else None
    mostrar(ok_err not in ("E201", "E202"), "checksum", "CONSULTA;AC-0001;14 (valido)",
            "pasa la integridad (ni E201 ni E202)", resumen(st_ok, r_ok))
    mostrar(bad_err == "E202", "checksum", "CONSULTA;AC-0001;15 (invalido)",
            "400 E202 control inválido", resumen(st_bad, r_bad))
    print(regla(COLS))

    if difs:
        print(f"\n=== CAMBIO DETECTADO en {len(difs)} chequeo(s): parchear model.py y redeployar ===")
        # la tabla corta los textos largos: los cambios van completos abajo
        for bloque, que, esperado, ahora in difs:
            print(f"\nCAMBIO {bloque} {que!r}")
            print(f"  baseline: {esperado}")
            print(f"  ahora   : {ahora}")
    else:
        print("\n=== SIN CAMBIOS (todo igual al baseline) ===")

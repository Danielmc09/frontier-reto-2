# Caja negra — reemplazo

Reimplementación de un servicio HTTP heredado del que no había documentación ni código.
Su comportamiento se reconstruyó por observación (fuzzing contra el original) y este
repositorio lo replica: mismo status y mismo cuerpo para cada request, errores incluidos.

El enunciado original del reto está en [`ENUNCIADO.md`](ENUNCIADO.md).

## Qué hace el servicio

Es un intérprete de comandos bancarios. Recibe mensajes por `POST /msg` con un cuerpo
`{"m": "CMD;arg1;...;control"}`, donde el último campo es un checksum del mensaje.

| Comando    | Argumentos                 | Efecto                                   | Respuesta OK                              |
| ---------- | -------------------------- | ---------------------------------------- | ----------------------------------------- |
| `PING`     | `control` (no se valida)   | Ninguno                                  | `200 {"pong": true}`                      |
| `ALTA`     | `nombre;control`           | Crea una cuenta `AC-0001`, `AC-0002`…    | `201 {"cuentaId": "AC-0001"}`             |
| `CONSULTA` | `cuenta;control`           | Ninguno                                  | `200 {"cuenta_id", "saldo"}`              |
| `DEPOSITO` | `cuenta;monto;control`     | Suma al saldo, registra `OP-0001`…       | `200 {"status": "recieved", "operacionId"}` |
| `TRANSFER` | `origen;destino;monto;control` | Mueve saldo (límite 100000)          | `200 {"status": "recieved", "operacionId"}` |
| `ANULA`    | `operacion;control`        | Revierte un depósito o transferencia     | `200 {"ok": true, "anulada"}`             |

Los comandos no distinguen mayúsculas. El estado (cuentas, saldos, operaciones) vive en
memoria y se reinicia con `POST /__reset`.

### Errores

| Código | Status | Cuándo                                     |
| ------ | ------ | ------------------------------------------ |
| `E001` | 401    | Token ausente o incorrecto                 |
| `E201` | 400    | El control no es un entero                 |
| `E202` | 400    | El control no coincide con el checksum     |
| `E301` | 400    | Comando desconocido (el mensaje lleva un espacio final, como el original) |
| `E302` | 400    | Cantidad de argumentos incorrecta          |
| `E401` | 404    | Cuenta inexistente                         |
| `E404` | 404    | Ruta o método desconocido                  |
| `E506` | 422    | Transferencia por encima del límite        |
| `E507` | 422    | Saldo insuficiente                         |

### Checksum del control

ISO 7064 MOD 97-10 (el algoritmo del dígito de control del IBAN) sobre el payload
completo `CMD;args`:

1. Se pasa a dígitos: los dígitos quedan, cada letra se vuelve su posición en el alfabeto
   (`A=1` … `Z=26`, sin distinguir mayúsculas) y los separadores (`;`, `-`) se descartan.
2. `control = 98 - (N·100 mod 97)`, siempre en el rango `[2, 98]`.

Ejemplo: `ALTA;Lucia` → `1122011221391` → control `82`. Verificado contra los 85 pares
válidos de `experimentos.jsonl` y los ejemplos (`test_control.py`).

## Rutas

| Ruta            | Auth | Comportamiento                         |
| --------------- | ---- | -------------------------------------- |
| `GET /health`   | No   | `200 {"status": "ok"}`                 |
| `POST /__reset` | Sí   | Vuelve el estado al inicial            |
| `POST /msg`     | Sí   | Interpreta el comando                  |
| Cualquier otra  | Sí   | `404 E404`                             |

La autenticación es `Authorization: Bearer <token>`, comparado contra la variable de
entorno `TEAM_TOKEN` (o `RESET_TOKEN` para pruebas locales). Sin ninguna configurada, se
acepta cualquier Bearer no vacío.

## Estructura

**Servicio** (lo único que va en la imagen):

- `model.py`: todo el comportamiento, como función pura `respond(..., state) -> (respuesta, state)`.
- `app.py`: transporte ASGI mínimo. Autentica, maneja `/health` y `/__reset`, y delega el resto a `model.py`.
- `compare.py`: igualdad de respuestas con la regla del evaluador (JSON sin orden de claves, texto exacto si no es JSON).

**Forense** (herramientas contra el original, no se despliegan):

- `fuzz.py`, `fuzz2.py`, `fuzz3.py`: tandas de experimentos para reversar el checksum. Escriben `experimentos.jsonl` y `controles.jsonl`.
- `harness.py`: cliente con limitador de tasa (< 10 req/s) y log en formato de experimentos.
- `differential.py`: manda las mismas secuencias al original y al reemplazo y reporta divergencias.
- `replay_examples.py`: reproduce `pruebas/ejemplos.jsonl` contra `model.py`.
- `test_control.py`: verifica el checksum contra la evidencia y que los 20 ejemplos se reproduzcan.
- `test_smoke.py`: verifica el contrato del entrypoint sin levantar servidor.

## Ejecución

```bash
pip install -r requirements.txt
TEAM_TOKEN=<token> uvicorn app:app --workers 1
```

Con Docker:

```bash
docker build -t caja-negra .
docker run -p 8000:8000 -e TEAM_TOKEN=<token> caja-negra
```

Corre con **un solo worker**: el estado está en memoria del proceso, y varios workers o
réplicas tendrían estados separados.

## Herramientas forenses

```bash
pip install -r requirements-dev.txt
python test_control.py                          # checksum + ejemplos contra el modelo
RESET_TOKEN=testreset python test_smoke.py      # contrato del entrypoint
TOKEN=<token> python differential.py            # original vs reemplazo
TOKEN=<token> python fuzz.py [meta|ejemplos|checksum]
```

## Pendiente

Marcado como `TODO(forense)` en el código: cuerpo exacto de `/__reset` del original, body
no JSON, monto no numérico, `ANULA` sobre operación inexistente y el orden fino entre
`E401`, `E506` y `E507`.

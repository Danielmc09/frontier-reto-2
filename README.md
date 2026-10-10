# Caja negra — reemplazo

Reimplementación de un servicio HTTP heredado del que no había documentación ni código.
Su comportamiento se reconstruyó por observación (fuzzing contra el original) y este
repositorio lo replica: mismo status y mismo cuerpo para cada request, errores incluidos.

El servicio cambió durante el día (incidente FR-0153). El reemplazo reproduce la
**versión 2**, la vigente. La especificación completa, con la evidencia de cada
comportamiento, está en [`docs/especificacion.md`](docs/especificacion.md), y el
enunciado del reto en [`docs/ENUNCIADO.md`](docs/ENUNCIADO.md).

## Qué hace el servicio

Es un intérprete de comandos bancarios. Recibe mensajes por `POST /msg` con un cuerpo
`{"m": "CMD;arg1;...;control"}`, donde el último campo es un checksum del mensaje.

| Comando    | Argumentos                     | Efecto                                    | Respuesta OK                                 |
| ---------- | ------------------------------ | ----------------------------------------- | -------------------------------------------- |
| `PING`     | `control` (no se valida)       | Ninguno                                   | `200 {"pong": true}`                         |
| `ALTA`     | `nombre;control`               | Crea una cuenta `AC-0001`, `AC-0002`…     | `201 {"cuentaId": "AC-0001"}`                |
| `CONSULTA` | `cuenta;control`               | Ninguno                                   | `200 {"cuenta_id", "saldo": "400.00"}`       |
| `DEPOSITO` | `cuenta;monto;control`         | Suma al saldo y registra `OP-0001`…       | `200 {"status": "recieved", "operacionId"}`  |
| `TRANSFER` | `origen;destino;monto;control` | Mueve saldo (límite 50000, ver abajo)     | `200 {"status": "recieved", "operacionId"}`  |
| `ANULA`    | `operacion;control`            | Revierte un depósito o una transferencia  | `200 {"ok": true, "anulada"}`                |

- Los comandos no distinguen mayúsculas.
- El saldo se informa como string con dos decimales en unidades de 100: `40000` → `"400.00"`.
- Los montos son enteros positivos, sin ceros a la izquierda y de hasta 10 dígitos.
- El límite de TRANSFER (50000) **no aplica entre dos cuentas del mismo titular**
  (el nombre dado en `ALTA`, exacto).
- `ANULA` puede dejar un saldo negativo. Las operaciones repetidas se procesan cada vez.
- El estado (cuentas, titulares, saldos, operaciones) vive en memoria y se reinicia con
  `POST /__reset`.

### Errores

| Código | Status | Cuándo                                                              |
| ------ | ------ | ------------------------------------------------------------------- |
| `E404` | 404    | Ruta o método desconocido (se evalúa antes que el token)            |
| `E001` | 401    | Token ausente o incorrecto en una ruta que existe                   |
| `E100` | 400    | El cuerpo no es JSON                                                |
| `E102` | 400    | Falta `m`, o no es un string                                        |
| `E103` | 400    | El mensaje no tiene `;` (falta el control)                          |
| `E104` | 400    | Algún segmento está vacío                                           |
| `E201` | 400    | El control no tiene 1 o 2 dígitos                                   |
| `E202` | 400    | El control no coincide con el checksum                              |
| `E301` | 400    | Comando desconocido; agrega `sugerencia` si uno conocido está a distancia ≤ 2 |
| `E302` | 400    | Cantidad de argumentos incorrecta                                   |
| `E303` | 400    | Monto inválido                                                      |
| `E304` | 400    | Origen y destino iguales                                            |
| `E401` | 404    | Cuenta inexistente                                                  |
| `E402` | 404    | Operación inexistente                                               |
| `E506` | 422    | Transferencia por encima del límite                                 |
| `E507` | 422    | Saldo insuficiente                                                  |

Se evalúan en ese orden: ruta, token, cuerpo, forma, control, comando, aridad, monto y
reglas de negocio.

### Checksum del control

ISO 7064 MOD 97-10 (el algoritmo del dígito de control del IBAN) sobre el payload
completo `CMD;args`:

1. Se pasa a dígitos: los dígitos quedan, cada letra se vuelve su posición en el alfabeto
   (`A=1` … `Z=26`, sin distinguir mayúsculas) y todo lo demás se descarta.
2. `control = 98 - (N·100 mod 97)`, siempre en el rango `[2, 98]`.

Ejemplo: `ALTA;Lucia` → `1122011221391` → control `82`.

## Rutas

| Ruta            | Token | Comportamiento                              |
| --------------- | ----- | ------------------------------------------- |
| `GET /health`   | Sí    | `200 {"ok": true}`                          |
| `POST /__reset` | Sí    | `200 {"ok": true}` y estado inicial         |
| `POST /msg`     | Sí    | Interpreta el comando                       |
| Cualquier otra  | No    | `404 E404`, con o sin token                 |

El token es `Authorization: Bearer <token>`, comparado contra la variable de entorno
`TEAM_TOKEN` (o `RESET_TOKEN` para pruebas locales).

## Arquitectura de archivos

```
.
├── app.py              Transporte ASGI: rutas, token, /health y /__reset; delega en model.py
├── model.py            Todo el comportamiento: respond(request, estado) -> (respuesta, estado)
├── compare.py          Igualdad de respuestas con la regla del evaluador
├── Dockerfile          Imagen del servicio (solo copia app.py, model.py y compare.py)
├── DOCKER.md           Cómo se construye y corre la imagen
├── docker-compose.yml  El servicio en local con un comando
├── railway.json        Despliegue en Railway: un proceso, un worker
├── Procfile            Comando de arranque para plataformas tipo Heroku
├── requirements.txt    Dependencias del servicio (uvicorn)
├── requirements-dev.txt  Dependencias de las herramientas forenses y tests (httpx)
│
├── docs/
│   ├── especificacion.md   Comportamientos con evidencia y confianza (entregable)
│   └── ENUNCIADO.md        Enunciado del reto
├── datos/
│   ├── experimentos.jsonl  Log de cada request al original (entregable; id = número de línea)
│   ├── controles.jsonl     Pares payload → control válido usados para reversar el checksum
│   ├── bordes_v2.jsonl     Respuestas de la versión 2 a los casos borde
│   └── regresion.jsonl     Corridas de la regresión
├── pruebas/
│   ├── ejemplos.jsonl      Los 20 ejemplos del reto (versión 1)
│   └── ejemplos_v2.jsonl   Los mismos 20 ejemplos contra la versión 2
├── forense/            Herramientas contra el original (no van en la imagen)
│   ├── fuzz.py             Cliente con limitador de tasa y log; base de las demás
│   ├── fuzz2.py, fuzz3.py  Tandas que reversaron el checksum
│   ├── bordes.py           Casos borde: original contra modelo y contra un baseline
│   ├── incidente.py        Sondas del incidente FR-0153, por fases
│   ├── aleatorio.py        Diferencial aleatorio en flujo continuo, con semilla
│   ├── cambio3.py          Candidatos al tercer cambio, contra la versión 1
│   ├── regresion.py        Detector de cambios del servicio contra un baseline fijo
│   ├── differential.py     Secuencias fijas: original contra reemplazo por HTTP
│   ├── replay_examples.py  Ejemplos contra el modelo, sin red
│   ├── harness.py          Cliente mínimo del primer barrido
│   └── tabla.py            Salida en tabla para la terminal
├── tests/
│   ├── test_v2.py          Modelo contra respuestas grabadas de la versión 2
│   ├── test_control.py     Checksum, orden de errores y ejemplos
│   ├── test_app.py         Orden ruta/token y /health
│   └── test_smoke.py       Contrato del entrypoint
└── documentos/         Documento de diseño y diagrama de arquitectura
```

El servicio queda en la raíz y la imagen copia solo esos tres archivos: las herramientas
forenses, los datos y los tests no se despliegan.

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

## Tests y herramientas forenses

Todo se ejecuta desde la raíz del repositorio, como módulo:

```bash
pip install -r requirements-dev.txt

python -m tests.test_v2                    # modelo contra la versión 2
python -m tests.test_control               # checksum, orden de errores y ejemplos
python -m tests.test_app                   # rutas, token y /health

TOKEN=<token> python -m forense.regresion            # ¿cambió el servicio?
TOKEN=<token> python -m forense.bordes               # casos borde contra el modelo
TOKEN=<token> python -m forense.incidente <fase>     # umbral, replay, anula, meta, ...
TOKEN=<token> N=200 SEED=1 python -m forense.aleatorio
BASE_URL=<url v1> TOKEN=<token> python -m forense.cambio3
```

Los scripts contra el original escriben en `datos/experimentos.jsonl` (salvo la regresión,
que usa `datos/regresion.jsonl`), respetan el límite de 10 requests por segundo y se
cortan solos si la infraestructura responde con rate limit.

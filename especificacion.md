# Especificación del servicio — Reto 2 "La Caja Negra"

Servicio de banca por mensajes sobre HTTP. Un cliente manda comandos en
`POST /msg` con cuerpo `{"m": "CMD;arg1;...;control"}` y el servicio responde en
JSON. Tiene estado por token, reiniciable con `POST /__reset`.

**Evidencia.** Las referencias `ej:N` son líneas de `pruebas/ejemplos.jsonl`
(los 20 ejemplos de la mañana). Las `exp:seq=...` son grupos de
`experimentos.jsonl` (nuestro log de fuzzing). **Confianza:** *confirmado* =
probado y se repite · *probable* = visto una vez o inferido · *supuesto* = no
probado, es lo que hace el reemplazo por defecto.

---

## 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E1.1 | `Authorization: Bearer <token>` en todas las llamadas. Sin token o token inválido → `401 {"error":"E001","mensaje":"no autorizado"}`. La auth se evalúa **antes** que la ruta. | exp:seq=meta-auth | confirmado |
| E1.2 | Endpoints: `POST /msg` (mensajes), `POST /__reset` (reinicio de estado), `GET /health` (200 readiness). | ej:1, exp:seq=meta | confirmado |
| E1.3 | Cualquier otra ruta o método → `404 {"error":"E404","mensaje":"ruta desconocida"}` (incluye `GET /msg`). | exp:seq=meta-ruta | confirmado |
| E1.4 | Cuerpo de `/msg`: JSON con clave `m`. El valor es `CMD;arg1;...;control`, campos separados por `;`. El **primer** campo es el comando (case-insensitive: `CONSULTa` = `CONSULTA`). El **último** campo es el `control` (checksum). | ej:11 | confirmado |
| E1.5 | Cuerpo no-JSON / sin `m` → `400` (comportamiento exacto no probado). | — | supuesto |

## 2. Integridad (validación del `control`)

El último campo es un `control` (checksum). Debe ser numérico y coincidir con el
checksum del mensaje; si no, se rechaza.

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E2.1 | Control no numérico → `400 {"error":"E201","mensaje":"control mal formado"}`. | ej:17 | confirmado |
| E2.2 | Control numérico pero distinto del checksum → `400 {"error":"E202","mensaje":"control inválido"}`. | ej:2 | confirmado |
| E2.3 | `PING` **no** valida control (responde aunque el último campo no sea número). | ej:1 | confirmado |
| E2.4 | **Fórmula del checksum.** Horner sobre el argumento (todo lo que sigue al comando): `r = (10·r − 3·v(ch)) mod 97`, arrancando en una base por comando; el control válido es `r` llevado al rango **[2,98]** (`si r<2: r+=97`). | exp:seq=checksum, sweep | confirmado |
| E2.5 | Base por comando (init del Horner): `CONSULTA=11, ALTA=85, ANULA=45, DEPOSITO=29, TRANSFER=58`. | exp:seq=checksum | confirmado |
| E2.6 | `v(ch)`: dígito→`d+3` · `A–I`/`a–i`→`ord(upper)−61` (4–12) · `J–Z`/`j–z`→`ord(upper)−40` (34–50) · `;`→48 · `-`→73. | exp:seq=checksum | confirmado (dígitos, A–I, `AC-####`); probable (resto) |
| E2.7 | Casos no cubiertos por la fórmula (letras minúsculas en medio de nombres, letras repetidas, `-` final): el reemplazo **acepta** cualquier control para no rechazar uno válido. Ver Riesgos. | exp:seq=checksum | supuesto |

## 3. Comandos

| ID | Comando | Aridad | Efecto y respuesta | Evidencia | Confianza |
|----|---------|--------|--------------------|-----------|-----------|
| E3.1 | `PING;<x>` | 1 | `200 {"pong":true}` | ej:1 | confirmado |
| E3.2 | `ALTA;<nombre>;<control>` | 2 | Crea cuenta secuencial con saldo 0 → `201 {"cuentaId":"AC-000N"}` | ej:3,4 | confirmado |
| E3.3 | `CONSULTA;<cuenta>;<control>` | 2 | Si existe → `200 {"cuenta_id":"AC-000N","saldo":<n>}` (ojo: clave `cuenta_id` en snake_case) | ej:5,8 | confirmado |
| E3.4 | `DEPOSITO;<cuenta>;<monto>;<control>` | 3 | Suma `monto` al saldo → `200 {"status":"recieved","operacionId":"OP-000N"}` (typo *recieved*) | ej:6,18 | confirmado |
| E3.5 | `TRANSFER;<origen>;<destino>;<monto>;<control>` | 4 | Mueve fondos → `200 {"status":"recieved","operacionId":"OP-000N"}` | ej:7,10 | confirmado |
| E3.6 | `ANULA;<opId>;<control>` | 2 | Revierte la operación: 1ª vez `200 {"ok":true,"anulada":"OP-000N"}`; si ya estaba anulada `200 {"ok":false,"motivo":"ya anulada"}` | ej:13,14 | confirmado |

## 4. Memoria entre requests (estado)

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E4.1 | Estado por token: cuentas (`AC-000N`→saldo), operaciones (`OP-000N`→detalle y si está anulada), y contadores secuenciales de cuenta y operación. | ej:3–8 | confirmado |
| E4.2 | Los saldos son acumulativos; `DEPOSITO`/`TRANSFER` los modifican; `ANULA` revierte el efecto de la operación. | ej:6,7,13,19 | confirmado |
| E4.3 | `POST /__reset` (con el token) reinicia el estado y los contadores → `200 {"ok":true}`. Tras reset, la primera cuenta es `AC-0001` y la primera operación `OP-0001`. | exp:seq=meta | confirmado |
| E4.4 | El header `X-Req` de la respuesta parece un contador de requests por token (no se compara en la evaluación). | exp (campo x_req) | probable |

## 5. Errores (con orden de evaluación)

| ID | Error | Status | Cuerpo exacto | Evidencia | Confianza |
|----|-------|--------|---------------|-----------|-----------|
| E5.1 | E001 | 401 | `{"error":"E001","mensaje":"no autorizado"}` | exp:seq=meta-auth | confirmado |
| E5.2 | E404 | 404 | `{"error":"E404","mensaje":"ruta desconocida"}` | exp:seq=meta-ruta | confirmado |
| E5.3 | E301 | 400 | `{"error":"E301","mensaje":"comando desconocido "}` (¡espacio final!) | ej:12 | confirmado |
| E5.4 | E302 | 400 | `{"error":"E302","mensaje":"aridad inválida"}` | ej:20 | confirmado |
| E5.5 | E201 | 400 | `{"error":"E201","mensaje":"control mal formado"}` | ej:17 | confirmado |
| E5.6 | E202 | 400 | `{"error":"E202","mensaje":"control inválido"}` | ej:2 | confirmado |
| E5.7 | E401 | 404 | `{"error":"E401","mensaje":"cuenta inexistente"}` | ej:15 | confirmado |
| E5.8 | E506 | 422 | `{"error":"E506","mensaje":"límite excedido"}` (transferencia sobre el límite) | ej:9 | confirmado |
| E5.9 | E507 | 422 | `{"error":"E507","mensaje":"saldo insuficiente"}` | ej:16 | confirmado |
| E5.10 | **Orden:** auth (E001) → ruta (E404) → comando conocido (E301) → aridad (E302) → control bien formado (E201) → control válido (E202) → negocio (E401 / E506 / E507). | ej:9,12,15,16,20 | probable |
| E5.11 | Límite exacto de `TRANSFER`: `100000` pasa, `120000` da E506 → umbral en (100000, 120000]. El reemplazo usa `monto > 100000 → E506`. | ej:9,10 | probable |
| E5.12 | `ANULA` sobre operación inexistente / monto no numérico: comportamiento exacto no probado. | — | supuesto |

## 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E6.1 | *(Pendiente del incidente de las 15:30. Se detecta re-corriendo la regresión y diffeando `experimentos.jsonl`; se documenta aquí qué cambió, desde cuándo y cómo se detectó.)* | — | — |

## 7. Riesgos (comportamientos que un cliente nuevo no debería heredar)

| ID | Riesgo | Cómo cerrarlo |
|----|--------|---------------|
| E7.1 | Typo `"recieved"` en las respuestas de DEPOSITO/TRANSFER. | Corregir a `received` en una versión nueva, con un período de compatibilidad. |
| E7.2 | Espacio final en `"comando desconocido "`. | Normalizar el mensaje de error. |
| E7.3 | Checksum con **bug de módulo incompleto** (rango [2,98] en vez de [0,96]) y **discontinuidad** en el valor de las letras a partir de la `J`. Hace el control frágil y difícil de regenerar. | Reemplazar por un checksum estándar (p.ej. CRC32 o HMAC) con migración de clientes. |
| E7.4 | Clave `cuenta_id` (snake) en CONSULTA vs `cuentaId`/`operacionId` (camel) en el resto: inconsistencia de nombres. | Unificar convención en la API nueva. |
| E7.5 | Estado en memoria por proceso (sin persistencia): un reinicio pierde todo; varias instancias divergen. | Externalizar el estado (base de datos / store compartido). |

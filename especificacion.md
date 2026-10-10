# Especificación del servicio — Reto 2 "La Caja Negra"

Servicio de banca por mensajes sobre HTTP. Un cliente manda comandos en
`POST /msg` con cuerpo `{"m": "CMD;arg1;...;control"}` y el servicio responde en
JSON. Tiene estado por token, reiniciable con `POST /__reset`.

**Evidencia.** Cada referencia es un `id` de `experimentos.jsonl`, que coincide
con su número de línea. Los 20 ejemplos de `pruebas/ejemplos.jsonl` se
reprodujeron contra el original y están en el log como los ids 6307–6326
(ejemplo N = id 6306+N). **Confianza:** *confirmado* =
probado y se repite · *probable* = visto una vez o inferido · *supuesto* = no
probado, es lo que hace el reemplazo por defecto.

---

## 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E1.1 | `Authorization: Bearer <token>` en todas las llamadas. Sin token o token inválido → `401 {"error":"E001","mensaje":"no autorizado"}`. La auth se evalúa **antes** que la ruta. | 6301, 6302 | confirmado |
| E1.2 | Endpoints: `POST /msg` (mensajes), `POST /__reset` (reinicio de estado), `GET /health` (200 readiness). | 6307, 6300 | confirmado |
| E1.3 | Cualquier otra ruta o método → `404 {"error":"E404","mensaje":"ruta desconocida"}` (incluye `GET /msg`). | 6303–6306 | confirmado |
| E1.4 | Cuerpo de `/msg`: JSON con clave `m`. El valor es `CMD;arg1;...;control`, campos separados por `;`. El **primer** campo es el comando (case-insensitive: `CONSULTa` = `CONSULTA`). El **último** campo es el `control` (checksum). | 6317 | confirmado |
| E1.5 | Cuerpo no-JSON / sin `m` → `400` (comportamiento exacto no probado). | — | supuesto |

## 2. Integridad (validación del `control`)

El último campo es un `control` (checksum). Debe ser numérico y coincidir con el
checksum del mensaje; si no, se rechaza.

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E2.1 | Control no numérico → `400 {"error":"E201","mensaje":"control mal formado"}`. | 6323 | confirmado |
| E2.2 | Control numérico pero distinto del checksum → `400 {"error":"E202","mensaje":"control inválido"}`. | 6308 | confirmado |
| E2.3 | El control se calcula con **ISO 7064 MOD 97-10** (el algoritmo del dígito de control del IBAN) sobre el payload **completo** `CMD;arg1;...`, sin el control: se pasa a un número N y `control = 98 − (N·100 mod 97)`. Ejemplo: `ALTA;Lucia` → `1122011221391` → `82`. Ajusta 85/85 pares válidos del log, incluidos los de varios argumentos. | 83, 102, 6276, 6299, 6312, 6313 | confirmado |
| E2.4 | Paso a dígitos: cada dígito queda igual; cada letra se reemplaza por su posición en el alfabeto en decimal (`A=1` … `Z=26`), así que `A–I` aportan un dígito y `J–Z` dos. Por eso el valor efectivo de las letras salta entre la `I` y la `J`. | 1162, 4634, 2739, 2374, 2431, 2451 | confirmado |
| E2.5 | Las letras no distinguen mayúsculas: `000a` y `000A` tienen el mismo control. | 1162, 5947 | confirmado |
| E2.6 | Los separadores no aportan dígitos: `CONSULTA;000-` tiene el mismo control que `CONSULTA;000`; el `;` entre campos tampoco. | 1585, 2643, 6276 | confirmado |
| E2.7 | Cualquier otro carácter no alfanumérico (espacio, `ñ`, tildes) se descarta igual que los separadores. | — | supuesto |
| E2.8 | El control siempre cae en el rango **[2, 98]**, propio de `98 − (x mod 97)`. `CONSULTA;A` da 98. | 1261 | confirmado |
| E2.9 | `PING` no valida el control: responde `pong` con cualquier último campo (`PING;0`, `PING;XX`), aunque `PING;64` resulta ser su control válido. | 6307; `PING;0` y `PING;XX` vistos con `differential.py`, pendientes de loguear | confirmado |
| E2.10 | Mensaje sin `;` (sin campo de control) → `400 {"error":"E103","mensaje":"falta control"}`. | `ZZZ` visto con `differential.py`, pendiente de loguear | confirmado |

## 3. Comandos

| ID | Comando | Aridad | Efecto y respuesta | Evidencia | Confianza |
|----|---------|--------|--------------------|-----------|-----------|
| E3.1 | `PING;<x>` | 1 | `200 {"pong":true}` | 6307 | confirmado |
| E3.2 | `ALTA;<nombre>;<control>` | 2 | Crea cuenta secuencial con saldo 0 → `201 {"cuentaId":"AC-000N"}` | 6309, 6310 | confirmado |
| E3.3 | `CONSULTA;<cuenta>;<control>` | 2 | Si existe → `200 {"cuenta_id":"AC-000N","saldo":<n>}` (ojo: clave `cuenta_id` en snake_case) | 6311, 6314 | confirmado |
| E3.4 | `DEPOSITO;<cuenta>;<monto>;<control>` | 3 | Suma `monto` al saldo → `200 {"status":"recieved","operacionId":"OP-000N"}` (typo *recieved*) | 6312, 6324 | confirmado |
| E3.5 | `TRANSFER;<origen>;<destino>;<monto>;<control>` | 4 | Mueve fondos → `200 {"status":"recieved","operacionId":"OP-000N"}` | 6313, 6316 | confirmado |
| E3.6 | `ANULA;<opId>;<control>` | 2 | Revierte la operación: 1ª vez `200 {"ok":true,"anulada":"OP-000N"}`; si ya estaba anulada `200 {"ok":false,"motivo":"ya anulada"}` | 6319, 6320 | confirmado |

## 4. Memoria entre requests (estado)

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E4.1 | Estado por token: cuentas (`AC-000N`→saldo), operaciones (`OP-000N`→detalle y si está anulada), y contadores secuenciales de cuenta y operación. | 6309–6314 | confirmado |
| E4.2 | Los saldos son acumulativos; `DEPOSITO`/`TRANSFER` los modifican; `ANULA` revierte el efecto de la operación. | 6312, 6313, 6319, 6325 | confirmado |
| E4.3 | `POST /__reset` (con el token) reinicia el estado y los contadores → `200 {"ok":true}`. Tras reset, la primera cuenta es `AC-0001` y la primera operación `OP-0001`. | 6300 | confirmado |
| E4.4 | El header `X-Req` de la respuesta parece un contador de requests por token (no se compara en la evaluación). | exp (campo x_req) | probable |

## 5. Errores (con orden de evaluación)

| ID | Error | Status | Cuerpo exacto | Evidencia | Confianza |
|----|-------|--------|---------------|-----------|-----------|
| E5.1 | E001 | 401 | `{"error":"E001","mensaje":"no autorizado"}` | 6301, 6302 | confirmado |
| E5.2 | E404 | 404 | `{"error":"E404","mensaje":"ruta desconocida"}` | 6303–6306 | confirmado |
| E5.3 | E301 | 400 | `{"error":"E301","mensaje":"comando desconocido "}` (¡espacio final!) | 6318 | confirmado |
| E5.4 | E302 | 400 | `{"error":"E302","mensaje":"aridad inválida"}` | 6326 | confirmado |
| E5.4b | E103 | 400 | `{"error":"E103","mensaje":"falta control"}` (mensaje sin `;`) | `ZZZ` vía `differential.py`, pendiente de loguear | confirmado |
| E5.5 | E201 | 400 | `{"error":"E201","mensaje":"control mal formado"}` | 6323 | confirmado |
| E5.6 | E202 | 400 | `{"error":"E202","mensaje":"control inválido"}` | 6308 | confirmado |
| E5.7 | E401 | 404 | `{"error":"E401","mensaje":"cuenta inexistente"}` | 6321 | confirmado |
| E5.8 | E506 | 422 | `{"error":"E506","mensaje":"límite excedido"}` (transferencia sobre el límite) | 6315 | confirmado |
| E5.9 | E507 | 422 | `{"error":"E507","mensaje":"saldo insuficiente"}` | 6322 | confirmado |
| E5.10 | **Orden:** auth (E001) → ruta (E404) → falta control (E103) → control bien formado (E201) → control válido (E202) → comando conocido (E301) → aridad (E302) → monto (E303) → negocio (E401 / E506 / E507). La integridad va antes que el comando: `ZZZ;1` → E202 (no E301) y `ALTA;a;b;c;0` → E202 (no E302). Los ejemplos con E301/E302 traen el control válido (38 y 11), por eso llegan a esa validación. | 6318, 6326; `ZZZ;1` y `ALTA;a;b;c;0` vistos con `differential.py`, pendientes de loguear | confirmado |
| E5.11 | Límite exacto de `TRANSFER`: `100000` pasa, `120000` da E506 → umbral en (100000, 120000]. El reemplazo usa `monto > 100000 → E506`. | 6315, 6316 | probable |
| E5.12 | `ANULA` sobre operación inexistente: comportamiento exacto no probado. | — | supuesto |
| E5.13 | E303 | 400 | `{"error":"E303","mensaje":"monto inválido"}` con monto `0` en `DEPOSITO` y `TRANSFER`. Se evalúa antes que la existencia de las cuentas: la cuenta `0` no existe y aun así responde E303, no E401. | 6276, 6299 | confirmado |
| E5.14 | Montos negativos o no numéricos también dan E303. | — | supuesto |

## 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E6.1 | *(Pendiente del incidente de las 15:30. Se detecta re-corriendo la regresión y diffeando `experimentos.jsonl`; se documenta aquí qué cambió, desde cuándo y cómo se detectó.)* | — | — |

## 7. Riesgos (comportamientos que un cliente nuevo no debería heredar)

| ID | Riesgo | Cómo cerrarlo |
|----|--------|---------------|
| E7.1 | Typo `"recieved"` en las respuestas de DEPOSITO/TRANSFER. | Corregir a `received` en una versión nueva, con un período de compatibilidad. |
| E7.2 | Espacio final en `"comando desconocido "`. | Normalizar el mensaje de error. |
| E7.3 | El control es un checksum (ISO 7064 MOD 97-10), no una firma: cualquiera que conozca la fórmula genera controles válidos. Detecta errores de tipeo, pero no un mensaje adulterado. | Firmar los mensajes con HMAC y un secreto por cliente, con migración de clientes. |
| E7.4 | Clave `cuenta_id` (snake) en CONSULTA vs `cuentaId`/`operacionId` (camel) en el resto: inconsistencia de nombres. | Unificar convención en la API nueva. |
| E7.5 | Estado en memoria por proceso (sin persistencia): un reinicio pierde todo; varias instancias divergen. | Externalizar el estado (base de datos / store compartido). |

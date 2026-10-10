# Especificación del servicio — Reto 2 "La Caja Negra"

Servicio de banca por mensajes sobre HTTP. Un cliente manda comandos en
`POST /msg` con cuerpo `{"m": "CMD;arg1;...;control"}` y el servicio responde en
JSON. Tiene estado por token, reiniciable con `POST /__reset`.

Este documento describe la **versión 2**, vigente desde la tarde del día del reto
(incidente FR-0153). Lo que cambió respecto de la versión 1 está en la sección 6.

**Evidencia.** Cada referencia es un `id` de `experimentos.jsonl`, que coincide con
su número de línea. Las líneas 1–6416 son de la versión 1 y las 6417 en adelante de
la versión 2. Los 20 ejemplos de `pruebas/ejemplos.jsonl` se reprodujeron contra la
versión 1 en las líneas 6307–6326 (ejemplo N = línea 6306+N).

**Confianza:** *confirmado* = probado y se repite · *probable* = visto una vez o
inferido · *supuesto* = no probado, es lo que hace el reemplazo por defecto.

---

## 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E1.1 | Rutas que existen: `POST /msg`, `POST /__reset` y `GET /health`. | 6300, 6307, 6733 | confirmado |
| E1.2 | **La ruta se evalúa antes que el token.** Cualquier otro método o ruta responde `404 {"error":"E404","mensaje":"ruta desconocida"}`, con o sin token: `GET /nope` sin token, `GET /msg`, `GET /__reset`, `POST /msg/`, `POST /MSG`, `PUT /msg`, `POST /health`, `DELETE /nope`. | 7393, 7397–7401, 7404, 7405 | confirmado |
| E1.3 | En las rutas que existen se exige `Authorization: Bearer <token>`. Sin token, con un token inválido o con el esquema en minúscula (`bearer`) → `401 {"error":"E001","mensaje":"no autorizado"}`. | 6301, 6302, 7394, 7395, 7403 | confirmado |
| E1.4 | `GET /health` con token → `200 {"ok":true}`; sin token → `401 E001`. | 6733, 7396 | confirmado |
| E1.5 | `POST /__reset` con token → `200 {"ok":true}`; reinicia cuentas, operaciones y contadores. | 6300, 6729 | confirmado |
| E1.6 | El query string se ignora: `POST /msg?x=1` responde igual que `POST /msg`. | 7402 | confirmado |
| E1.7 | Cuerpo que no es JSON, o vacío → `400 {"error":"E100","mensaje":"json inválido"}`. | 6523, 6526 | confirmado |
| E1.8 | JSON sin clave `m`, con `m` que no es string, con `m` nulo o que no es un objeto (`[]`) → `400 {"error":"E102","mensaje":"falta m"}`. Las claves extra se ignoran. | 6524, 6525, 7390, 7391, 7392 | confirmado |
| E1.9 | `m` es `CMD;arg1;...;control`, con campos separados por `;`. El comando no distingue mayúsculas (`CONSULTa`, `alta`). No se recortan espacios: `" PING;64"` y `"PING ;64"` dan E301 con `"sugerencia":"PING"`; un nombre con espacios es válido. | 6317, 6515, 7344, 7345, 7351 | confirmado |
| E1.10 | No hay límite de largo observado: nombres de 41, 100, 256 y 1000 caracteres, con símbolos (`.`, `_`, `@`, `/`) o emoji, se aceptan. | 7381–7389 | confirmado |

## 2. Integridad (validación del `control`)

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E2.1 | Mensaje sin `;` (`ZZZ`, `PING`, `""`, solo espacios) → `400 {"error":"E103","mensaje":"falta control"}`. | 6492, 6493, 6497, 7348 | confirmado |
| E2.2 | Algún segmento vacío (`;`, `ALTA;;85`, `PING;`) → `400 {"error":"E104","mensaje":"segmento vacío"}`. Se evalúa antes que el control. | 6498, 6516, 6755 | confirmado |
| E2.3 | El control es el último campo y está bien formado si tiene **1 o 2 dígitos** (`0`, `00`, `99`). Cualquier otra cosa (`5X`, `-14`, `014`, `111`, `" 14"`) → `400 {"error":"E201","mensaje":"control mal formado"}`. | 6323, 6502, 6506, 6510, 6514, 6750, 6754 | confirmado |
| E2.4 | **Fórmula del checksum: ISO 7064 MOD 97-10** (el dígito de control del IBAN) sobre el payload completo `CMD;arg1;...` sin el control. El payload se pasa a dígitos: cada dígito queda igual y cada letra pasa a su posición en el alfabeto (`A=1` … `Z=26`, así que `J`–`Z` ocupan dos dígitos). Con ese número N: `control = 98 − (N·100 mod 97)`, siempre en `[2, 98]`. Ejemplo: `ALTA;Lucia` → `1122011221391` → `82`. | 83, 102, 1162, 2374, 2431, 2451, 2739, 4634, 6312, 6313 | confirmado |
| E2.5 | Las letras no distinguen mayúsculas, y todo carácter que no sea una letra o un dígito ASCII se descarta: `;`, `-`, espacio, `ñ`, emoji. | 1162, 5947, 1585, 2643, 6517, 6518, 7389 | confirmado |
| E2.6 | Control bien formado pero distinto del checksum → `400 {"error":"E202","mensaje":"control inválido"}`. | 6308, 6754 | confirmado |
| E2.7 | La integridad se evalúa **antes** que el comando y la aridad: `SALDOS;AC-0001;39` da E202, mientras que con el control válido (38) da E301. Con la aridad pasa lo mismo. | 7186, 6318, 6822 | confirmado |
| E2.8 | `PING` no valida el control (`PING;0`, `PING;XX` → pong), pero sí exige `;` (E103) y segmentos no vacíos (E104). | 6495, 6496, 6493, 6755 | confirmado |
| E2.9 | La regla del checksum es la misma en la versión 1 y en la 2: 66 requests de la v1 con control válido responden igual en la v2. | 6546–6712 | confirmado |

## 3. Comandos

Los montos son enteros positivos sin ceros a la izquierda y de **hasta 10 dígitos**.
Cualquier otro monto (`0`, `-5`, `abc`, `1.5`, `05`, `+5`, 11 dígitos o más) da
`400 {"error":"E303","mensaje":"monto inválido"}`.

| ID | Comando | Aridad | Efecto y respuesta | Evidencia | Confianza |
|----|---------|--------|--------------------|-----------|-----------|
| E3.1 | `PING;<x>` | 1 | `200 {"pong":true}` | 6307, 6495 | confirmado |
| E3.2 | `ALTA;<nombre>;<control>` | 2 | Crea una cuenta secuencial con saldo 0 y guarda el nombre como **titular** (exacto, distingue mayúsculas) → `201 {"cuentaId":"AC-000N"}`. Nombres repetidos son válidos y crean otra cuenta. | 6309, 6310, 7129, 7130 | confirmado |
| E3.3 | `CONSULTA;<cuenta>;<control>` | 2 | `200 {"cuenta_id":"AC-000N","saldo":"<s>"}`. El saldo es un **string con dos decimales, en unidades de 100**: `40000` → `"400.00"`, `-1000` → `"-10.00"`. Cuenta inexistente o mal escrita (`ac-0001`) → E401. | 6472, 6487, 7133, 6522 | confirmado |
| E3.4 | `DEPOSITO;<cuenta>;<monto>;<control>` | 3 | Suma el monto → `200 {"status":"recieved","operacionId":"OP-000N"}` (con el typo *recieved*). Sin límite propio más allá del tope de 10 dígitos. El monto se valida antes que la cuenta. | 6312, 6436, 6440, 7088 | confirmado |
| E3.5 | `TRANSFER;<origen>;<destino>;<monto>;<control>` | 4 | Mueve fondos → `200 {"status":"recieved","operacionId":"OP-000N"}`. Orden: monto (E303) → misma cuenta (E304) → cuentas (E401) → límite (E506) → saldo (E507). **Límite: E506 si el monto supera 50000, salvo entre dos cuentas del mismo titular**, donde no aplica. | 6544, 6545, 6466, 6734, 6738, 6742, 6458, 6462, 7132, 7137, 7142 | confirmado |
| E3.6 | `ANULA;<opId>;<control>` | 2 | Revierte la operación → `200 {"ok":true,"anulada":"OP-000N"}`. Si ya estaba anulada → `200 {"ok":false,"motivo":"ya anulada"}`. Operación inexistente o id mal formado → `404 {"error":"E402","mensaje":"operación inexistente"}`. La reversión puede dejar un saldo negativo. No crea una operación nueva. | 6717, 6718, 6476, 6491, 6487 | confirmado |

## 4. Memoria entre requests (estado)

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E4.1 | El estado es por token: cuentas (saldo y titular), operaciones (tipo, montos y si están anuladas) y dos contadores secuenciales, `AC-` y `OP-`. | 6309–6326, 7129–7143 | confirmado |
| E4.2 | Solo las operaciones exitosas consumen un `OP-`: los rechazos (E506 y otros) no avanzan el contador. | 6527–6545 | confirmado |
| E4.3 | El titular de cada cuenta decide si aplica el límite de TRANSFER (E3.5). `Ana` y `ana` son titulares distintos. | 7132, 7137, 7142 | confirmado |
| E4.4 | Los saldos son acumulativos. `ANULA` revierte el efecto y puede dejar un saldo negativo; con saldo negativo, una TRANSFER da E507 y un DEPOSITO suma normalmente. | 6487, 7362–7372 | confirmado |
| E4.5 | No hay detección de duplicados: el mismo DEPOSITO o TRANSFER repetido se procesa cada vez. | 7355–7361 | confirmado |
| E4.6 | El header `X-Req` es un contador de requests; se reinició con el deploy de la versión 2. No se compara en la evaluación. | campo `x_req` del log | probable |

## 5. Errores (con orden de evaluación)

| ID | Error | Status | Cuerpo exacto | Evidencia | Confianza |
|----|-------|--------|---------------|-----------|-----------|
| E5.1 | E404 | 404 | `{"error":"E404","mensaje":"ruta desconocida"}` | 7393, 7397 | confirmado |
| E5.2 | E001 | 401 | `{"error":"E001","mensaje":"no autorizado"}` | 6301, 7396 | confirmado |
| E5.3 | E100 | 400 | `{"error":"E100","mensaje":"json inválido"}` | 6523 | confirmado |
| E5.4 | E102 | 400 | `{"error":"E102","mensaje":"falta m"}` | 6524 | confirmado |
| E5.5 | E103 | 400 | `{"error":"E103","mensaje":"falta control"}` | 6492 | confirmado |
| E5.6 | E104 | 400 | `{"error":"E104","mensaje":"segmento vacío"}` | 6498 | confirmado |
| E5.7 | E201 | 400 | `{"error":"E201","mensaje":"control mal formado"}` | 6323, 6506 | confirmado |
| E5.8 | E202 | 400 | `{"error":"E202","mensaje":"control inválido"}` | 6308 | confirmado |
| E5.9 | E301 | 400 | `{"error":"E301","mensaje":"comando desconocido "}` (con un espacio al final). Si un comando conocido está a **distancia de Levenshtein ≤ 2**, agrega `"sugerencia":"<COMANDO>"` (`altas`, `ATLA`, `XLTB`, `TRANSFERIR`, `PONG` sugieren; `SALDOS`, `XYZA` y `WXYZ` no). | 6318, 7091–7102, 7126–7128 | confirmado |
| E5.10 | E302 | 400 | `{"error":"E302","mensaje":"aridad inválida"}` | 6326, 6494 | confirmado |
| E5.11 | E303 | 400 | `{"error":"E303","mensaje":"monto inválido"}` | 6420, 6424, 6428, 6432, 6746, 7122 | confirmado |
| E5.12 | E304 | 400 | `{"error":"E304","mensaje":"origen y destino iguales"}` | 6466, 6734 | confirmado |
| E5.13 | E401 | 404 | `{"error":"E401","mensaje":"cuenta inexistente"}` | 6321, 6462 | confirmado |
| E5.14 | E402 | 404 | `{"error":"E402","mensaje":"operación inexistente"}` | 6476, 6491 | confirmado |
| E5.15 | E506 | 422 | `{"error":"E506","mensaje":"límite excedido"}` | 6544, 6458 | confirmado |
| E5.16 | E507 | 422 | `{"error":"E507","mensaje":"saldo insuficiente"}` | 6322, 7142 | confirmado |
| E5.17 | **Orden:** ruta (E404) → token (E001) → cuerpo (E100, E102) → forma (E103, E104) → control (E201, E202; PING no lo valida) → comando (E301) → aridad (E302) → monto (E303) → misma cuenta (E304) → existencia (E401 / E402) → límite (E506, salvo mismo titular) → saldo (E507). | 7393, 7394, 6498, 7186, 6318, 6440, 6738, 6734, 6462, 6458, 7142 | confirmado |
| E5.18 | Cuando dos comandos conocidos empatan en distancia para la sugerencia, se elige el primero en el orden PING, ALTA, CONSULTA, DEPOSITO, TRANSFER, ANULA. | — | supuesto |

## 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
|----|----------------|-----------|-----------|
| E6.1 | **Cuándo y cómo se detectó.** Una regresión fija (`regresion.py`: los 20 ejemplos, auth, rutas y checksum) respondió igual que la versión 1 en las corridas de las 15:30, 15:32, 15:35 y 15:38, y distinto a las 16:01. El deploy de la versión 2 ocurrió entre las 15:38 y las 15:58: a las 15:58 los casos borde ya devolvían el saldo nuevo. | 6395–6416 (v1, 15:30), 6472 (v2, 15:58) | confirmado |
| E6.2 | **Cambio 1: formato del saldo.** v1: número entero (`40000`). v2: string con dos decimales en unidades de 100 (`"400.00"`). | v1: 6314, 6325 · v2: 6472, 7133 | confirmado |
| E6.3 | **Cambio 2: límite de TRANSFER.** v1: 100000 pasaba y 120000 daba E506. v2: 50000 pasa y 50001 da E506 (búsqueda binaria). En la regresión, el ejemplo 10 (100000) pasó de 200 a E506; eso arrastró a los ejemplos 11, 13, 14 y 18, porque `OP-0003` ya no existe y los saldos cambian. | v1: 6315, 6316 · v2: 6544, 6545 | confirmado |
| E6.4 | **Cambio 3: sin identificar con evidencia de antes y después.** Todo lo que la versión 1 llegó a ver responde igual en la versión 2: 74 requests de la v1 sin estado, ANULA de una TRANSFER y doble ANULA, `/__reset`, token inválido y rutas. Por eliminación, el cambio 3 está entre comportamientos que solo observamos en la v2: la exención del límite entre cuentas del mismo titular (candidato principal: es la única regla con estado), E104, E100/E102, el control de 1–2 dígitos, la sugerencia de E301, el tope de 10 dígitos o E304. | 6546–6712, 6713–6728, 6729–6733 | supuesto |
| E6.5 | **Limitación.** La foto de los casos borde se tomó a las 15:58, cuando la versión 2 ya estaba desplegada, así que no hay respuestas de la versión 1 para esos casos. | 6417–6526 | confirmado |

## 7. Riesgos (comportamientos que un cliente nuevo no debería heredar)

| ID | Riesgo | Cómo cerrarlo |
|----|--------|---------------|
| E7.1 | **El límite de transferencia se evita con el nombre del titular.** Basta dar de alta una cuenta con el mismo nombre que otra para mover montos sin límite entre las dos. El titular es un string libre, no una identidad. | Asociar las cuentas a un cliente autenticado (id, no nombre) y aplicar el límite por cliente, también entre cuentas propias si el negocio lo exige. |
| E7.2 | `ANULA` puede dejar saldos negativos: se puede anular un depósito cuyo dinero ya se transfirió. | Validar el saldo antes de revertir, o registrar la deuda explícitamente. |
| E7.3 | Sin detección de duplicados: un reintento del cliente procesa dos veces el mismo DEPOSITO o TRANSFER. | Claves de idempotencia por operación. |
| E7.4 | El control es un checksum (ISO 7064 MOD 97-10), no una firma: cualquiera que conozca la fórmula genera controles válidos. Detecta errores de tipeo, no adulteraciones. | Firmar los mensajes con HMAC y un secreto por cliente. |
| E7.5 | El saldo cambió de número a string con unidades de 100 sin aviso. Un cliente que lo leía como número se rompe o muestra valores 100 veces más chicos. | Versionar la API y anunciar cambios de formato. |
| E7.6 | Typo `"recieved"` y espacio final en `"comando desconocido "`. | Corregirlos en una versión nueva, con un período de compatibilidad. |
| E7.7 | Nombres de claves inconsistentes: `cuenta_id` (snake_case) en CONSULTA y `cuentaId`/`operacionId` (camelCase) en el resto. | Unificar la convención en la API nueva. |
| E7.8 | Estado en memoria por proceso: un reinicio pierde todo y varias instancias divergen. | Externalizar el estado en una base de datos. |

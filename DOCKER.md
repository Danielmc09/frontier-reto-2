# Docker — reemplazo (Reto 2)

Multistage: una etapa compila dependencias en un venv, la otra es una imagen
`python:3.12-slim` no-root con **solo** `model.py`, `app.py`, `compare.py` y el venv.
Las herramientas forenses (`forense/`), los tests (`tests/`), los datos (`datos/`) y la
documentación **no** entran en la imagen.

## Comandos (los corres tú)

Build:
```bash
docker build -t caja-negra .
```

Run local (una instancia):
```bash
docker run --rm -p 8000:8000 -e PORT=8000 -e RESET_TOKEN=testreset caja-negra
```

Probar:
```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/msg -H 'content-type: application/json' -d '{"m":"PING;64"}'
```

Con compose:
```bash
docker compose up --build
```

## Deploy en Railway
- Railway detecta el `Dockerfile` (ver `railway.json`: builder `DOCKERFILE`).
- **Una sola réplica** (`numReplicas: 1`) y **un solo worker** (ya en el `CMD`/startCommand):
  el estado vive en memoria del proceso; varias instancias = estados distintos = el set falla.
- Healthcheck: `GET /health`.
- Variables: `PORT` (lo pone Railway) y las de auth/reset cuando cableemos el token del equipo.

## Nota
`requirements.txt` = runtime (solo `uvicorn`). Para el tooling local:
```bash
pip install -r requirements-dev.txt
```

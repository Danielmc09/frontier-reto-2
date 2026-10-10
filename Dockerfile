# syntax=docker/dockerfile:1

# ========== Stage 1: builder ==========
# Compila las dependencias de runtime en un venv aislado.
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ========== Stage 2: runtime ==========
# Imagen final: slim, no-root, solo el codigo que SIRVE el reemplazo.
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000
WORKDIR /app

# usuario no-root
RUN useradd -r -u 10001 appuser

# venv con las dependencias de runtime (solo uvicorn)
COPY --from=builder /opt/venv /opt/venv

# SOLO el codigo del servicio. El tooling forense (harness/differential/replay)
# NO va en la imagen: no se necesita para servir y mantiene la imagen chica.
COPY model.py app.py compare.py ./

# Normalizar permisos: los archivos del build context podian venir sin lectura
# para "otros", y el proceso corre como appuser. 0644 => legibles por todos.
RUN chmod 0644 /app/*.py

USER appuser

EXPOSE 8000

# Healthcheck del contenedor contra /health (sin auth, 200 cuando esta listo).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health').getcode()==200 else 1)"

# IMPORTANTE: UN SOLO worker / UNA SOLA instancia.
# El estado vive en memoria del proceso; varios workers o replicas = estados
# separados = el set oculto (que le habla a un solo proceso) falla.
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

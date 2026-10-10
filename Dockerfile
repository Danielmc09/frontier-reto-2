# syntax=docker/dockerfile:1

# ========== Stage 1: builder ==========
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ========== Stage 2: runtime ==========
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

# SOLO el codigo del servicio. --chown => appuser es DUENO (lectura garantizada
# aunque el archivo del contexto venga con modo restringido, p.ej. 0600).
COPY --chown=appuser:appuser model.py app.py compare.py ./

# Cinturon y tirantes: lectura para todos en archivos, busqueda en directorios.
RUN chmod -R a+rX /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health').getcode()==200 else 1)"

# UN SOLO worker / UNA SOLA instancia: el estado vive en memoria del proceso.
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

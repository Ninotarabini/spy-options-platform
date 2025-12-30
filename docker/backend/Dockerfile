FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

# Crear usuario PRIMERO
RUN useradd -m -u 1000 appuser

# Copiar paquetes a ubicación del usuario
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

# Ajustar permisos y PATH
RUN chown -R appuser:appuser /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

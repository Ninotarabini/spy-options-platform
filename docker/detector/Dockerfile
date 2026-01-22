FROM python:3.11-slim AS builder
WORKDIR /app

# Install build dependencies for numpy, pandas, scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario PRIMERO
RUN useradd -m -u 1000 appuser

# Copiar paquetes a ubicación del usuario
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

# Ajustar permisos y PATH
RUN chown -R appuser:appuser /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

# Health check: Verify process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD cat /etc/hostname || exit 1

CMD ["python", "detector.py"]

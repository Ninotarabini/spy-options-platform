# ---------- Builder ----------
FROM python:3.11-slim AS builder

# Build-time version argument
ARG BUILD_VERSION="dev-local"
ENV APP_VERSION=${BUILD_VERSION}


WORKDIR /app

# Build deps for numpy / scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    libopenblas0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* # Python dep
COPY requirements.txt ./requirements.txt 
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Runtime ----------
FROM python:3.11-slim
WORKDIR /app

# Runtime libs (añadido procps para el healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgomp1 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copiamos las librerías instaladas desde el builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy ONLY runtime code
COPY detector.py .
COPY anomaly_algo.py .
COPY ibkr_client.py .
COPY config.py .
COPY models.py .
COPY metrics.py .
COPY market_hours.py .
COPY volume_aggregator.py .
COPY volume_tracker.py .
COPY signalr_client.py .

# Permissions
RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD pgrep -f detector.py || exit 1

CMD ["python", "detector.py"]

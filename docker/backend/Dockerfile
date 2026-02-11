FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies as root, then copy to appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && cp -r /root/.local /home/appuser/.local 2>/dev/null || true

# Copy application code
COPY --chown=appuser:appuser . .
RUN chown -R appuser:appuser /home/appuser/.local 2>/dev/null || true

ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MODEL_BUNDLE=/app/model-bundle \
    HOME=/tmp
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home hotelml
COPY --chown=hotelml:hotelml model-bundle ./model-bundle
USER hotelml
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')"
CMD ["uvicorn", "hotelml.api:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]

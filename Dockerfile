# Multi-stage image. The model binary is not copied. scripts/entrypoint.sh
# pulls it from the DVC remote after the container starts.
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements-serve.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements-serve.txt

FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/sh appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DVC_NO_ANALYTICS=1 \
    HOME=/home/appuser \
    PORT=8000 \
    MODEL_AUTOLOAD=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY requirements-serve.txt /app/requirements.txt
COPY params.yaml /app/params.yaml
COPY src /app/src
COPY app /app/app
COPY scripts /app/scripts
COPY .dvc/config /app/.dvc/config
COPY .dvc/.gitignore /app/.dvc/.gitignore
COPY dvc.yaml /app/dvc.yaml
COPY dvc.lock /app/dvc.lock
COPY data/raw/retail_price.csv.dvc /app/data/raw/retail_price.csv.dvc

RUN mkdir -p /app/models /app/.dvc/cache /app/.dvc/tmp \
    && chmod +x /app/scripts/entrypoint.sh /app/scripts/fetch_model.sh /app/scripts/smoke_test.sh \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=2)"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

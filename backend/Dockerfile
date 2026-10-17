# syntax=docker/dockerfile:1
# GreenGuardian API (and, later, the scheduled worker: same image, different command).
# Build context: ./backend    Build: docker build -t greenguardian-backend ./backend

# ---- build stage: resolve and install dependencies into a virtualenv (compilers/caches never reach the runtime image)
FROM python:3.12-slim-bookworm AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# ---- runtime stage
FROM python:3.12-slim-bookworm AS runtime
# A fixed non-root identity (no shell, no login). Secrets are NEVER baked in: everything arrives as environment variables.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /srv --shell /usr/sbin/nologin app \
 && mkdir -p /data/storage \
 && chown -R app:app /data
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_PROVIDER=local \
    STORAGE_LOCAL_DIR=/data/storage
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
# Alembic needs its scripts next to the working directory; the application code itself is installed in the venv.
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"
# One process per container: scale by running more containers. Migrations are a separate one-shot command
# (`alembic upgrade head`), never run implicitly at start-up, so several replicas cannot race each other.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

# Install the package and runtime deps. Use --no-cache-dir to keep the image
# lean — we don't need pip's cache after install.
WORKDIR /app

# Copy only metadata first so dependency installs can be cached across edits.
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir -e .

# Runtime configuration. App writes credentials/tokens/DB to /data, which the
# compose file mounts as a named volume so state persists across rebuilds.
ENV PARSLI_APP_DIR=/data \
    PARSLI_DATABASE__SQLITE_PATH=/data/parsli.db \
    PYTHONUNBUFFERED=1

# Create the data dir at build time so first boot doesn't race the volume mount.
RUN mkdir -p /data/tokens

EXPOSE 8000

# Use uvicorn directly (the CLI's `parsli serve` binds to 127.0.0.1 by default,
# which would hide the service from the docker network).
CMD ["uvicorn", "parsli.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

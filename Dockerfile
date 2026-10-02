# syntax=docker/dockerfile:1
#
# PharmaStock / Stockera: Streamlit app with the paid-tier AI Action Plan.
#
# The base image is multi-arch, so the same file builds natively on
# Windows/Intel (linux/amd64) and Apple Silicon Macs (linux/arm64). Every
# dependency ships wheels for both, so no compiler toolchain is needed.
# To publish one image for both platforms:
#   docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/stockera:latest --push .
#
# Secrets are NOT baked in: ANTHROPIC_API_KEY arrives at runtime from .env via
# docker-compose (and .env is excluded from the build context by .dockerignore).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    STOCKERA_DATA_DIR=/app/data \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Unprivileged runtime user; /app/data holds the SQLite database (users,
# token usage, saved reports) and is mounted as a named volume.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data \
 && chown app:app /app/data

COPY --chown=app:app . .

USER app
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"

CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]

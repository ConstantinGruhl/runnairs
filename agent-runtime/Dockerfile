# Base image for all deployed agents.
# Build context is the repo root; per-agent images extend this image
# with the agent's code copied in (Phase 5+).
#
# Build (from repo root):
#   docker build -f agent-runtime/Dockerfile -t platform/agent-runtime:latest .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /agent

# Install platform_sdk so agents can `import platform_sdk` out of the box.
COPY packages/platform_sdk /opt/platform_sdk
RUN pip install --upgrade pip && pip install /opt/platform_sdk

# Per-agent images COPY their code on top of this layer.
COPY agent-runtime/entrypoint.py /agent/entrypoint.py

ENTRYPOINT ["python", "/agent/entrypoint.py"]

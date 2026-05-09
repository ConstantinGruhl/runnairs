# Base image for all deployed agents.
# Per-agent images are built FROM this image with the agent's code copied in.
# Real implementation lands in Phase 4.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /agent

# platform_sdk is mounted/copied in once it ships.
COPY entrypoint.py /agent/entrypoint.py

ENTRYPOINT ["python", "/agent/entrypoint.py"]

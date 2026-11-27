FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYVISTA_OFF_SCREEN=true \
    VTK_DEFAULT_RENDER_WINDOW_OFFSCREEN=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libxrender1 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    xvfb \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml AGENTS.md ./
COPY engine/ ./engine/
COPY server.py ./
COPY examples/ ./examples/

RUN pip install --no-cache-dir -e .

CMD ["python", "server.py"]

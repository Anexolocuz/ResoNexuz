FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RESONEXUZ_CONFIG_DIR=/config

RUN apt-get update && apt-get install -y --no-install-recommends \
    libegl1 \
    libgl1 \
    libglx0 \
    libglfw3 \
    libwayland-client0 \
    libwayland-egl1 \
    libx11-6 \
    libportaudio2 \
    pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt README.md LICENSE ./
COPY resonexuz ./resonexuz

RUN pip install --no-cache-dir . && mkdir -p /config

EXPOSE 8765
ENTRYPOINT ["resonexuz"]
CMD ["--ui", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]

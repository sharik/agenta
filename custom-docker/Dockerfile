# Use Python 3.11 instead of 3.10
FROM python:3.12-slim as base

# Set environment variables
ENV PATH="/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV LANG=C.UTF-8
ENV GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D
ENV PYTHON_VERSION=3.12.1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    netbase \
    tzdata \
    dpkg-dev \
    gcc \
    gnupg \
    libbluetooth-dev \
    libbz2-dev \
    libc6-dev \
    libdb-dev \
    libffi-dev \
    libgdbm-dev \
    liblzma-dev \
    libncursesw5-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    make \
    tk-dev \
    uuid-dev \
    wget \
    xz-utils \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install core dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir \
    poetry \
    langchain \
    llama_index \
    openai \
    cohere \
    python-dotenv \
    uvicorn \
    replicate \
    "litellm>=1.0,<2.0" \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp

# Install agenta package
RUN pip install --no-cache-dir -U agenta

# Ensure Python commands are available without "3" suffix
# Ensure Python commands are available without "3" suffix (Check file exists first)
RUN set -eux; \
    for src in idle3 pip3 pydoc3 python3 python3-config; do \
        dst="$(echo "$src" | tr -d 3)"; \
        if [ -s "/usr/local/bin/$src" ] && [ ! -e "/usr/local/bin/$dst" ]; then \
            ln -svT "$src" "/usr/local/bin/$dst"; \
        fi \
    done

# Set the default command
CMD ["python3"]

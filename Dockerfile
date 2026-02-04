FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U pip uv

COPY pyproject.toml /app/pyproject.toml

# Copy source before editable install so `-e .` can resolve the package.
COPY src /app/src

RUN uv pip install --system -e ".[dev]"

COPY . /app

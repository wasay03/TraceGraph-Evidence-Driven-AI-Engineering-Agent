FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY tracegraph ./tracegraph
COPY migrations ./migrations
COPY sql ./sql
RUN pip install --no-cache-dir . && git config --global --add safe.directory '*'

ENV TG_LOG_LEVEL=INFO
EXPOSE 8000
CMD ["tg", "serve", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim
LABEL description="Telegram bot — DuckDB + Parquet via S3-compatible server"
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot_main.py entrypoint.sh prepare_s3_server.py ./
RUN chmod +x entrypoint.sh

VOLUME /data/parquet

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

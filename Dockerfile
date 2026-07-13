FROM ghcr.io/siafoundation/s3d:latest AS s3d-stage
FROM python:3.11-slim

LABEL description="Telegram bot — DuckDB + Parquet via s3d (Sia Storage)"

WORKDIR /app

COPY --from=s3d-stage /usr/bin/s3d /usr/bin/s3d
COPY --from=s3d-stage /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot_main.py admin_panel.py entrypoint.sh prepare_s3_server.py ./
RUN chmod +x entrypoint.sh

COPY s3d.yml /data/s3d.yml
COPY s3d.db /data/s3d.db
COPY s3d.yml /app/s3d.yml

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
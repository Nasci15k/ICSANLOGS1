FROM python:3.11-alpine
LABEL description="Telegram bot — DuckDB + Parquet via S3-compatible server"
WORKDIR /app

RUN apk add --no-cache curl ca-certificates libstdc++

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código do bot + servidor
COPY bot_main.py entrypoint.sh prepare_s3_server.py ./
RUN chmod +x entrypoint.sh

# Ponto de montagem dos arquivos Parquet
VOLUME /data/parquet

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

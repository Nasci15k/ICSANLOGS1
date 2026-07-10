#!/bin/sh
# entrypoint.sh — Inicia servidor S3 Python (se local) + bot Telegram

PARQUET_DIR="${PARQUET_DIR:-/data/parquet}"
S3_PORT="${S3_PORT:-8000}"
S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:$S3_PORT}"

GW_PID=""

# Só inicia servidor Python se o endpoint for localhost
case "$S3_ENDPOINT" in
    http://localhost*|http://127.0.0.1*)
        echo ">>> Servindo Parquet de $PARQUET_DIR na porta $S3_PORT"
        python3 /app/prepare_s3_server.py "$PARQUET_DIR" "$S3_PORT" &
        GW_PID=$!
        for i in $(seq 1 10); do
            if curl -sf http://localhost:$S3_PORT/ > /dev/null 2>&1; then
                echo ">>> Gateway S3 pronto!"
                break
            fi
            sleep 1
        done
        ;;
    *)
        echo ">>> Usando S3 externo: $S3_ENDPOINT"
        ;;
esac

cleanup() {
    echo ">>> Encerrando..."
    [ -n "$GW_PID" ] && kill $GW_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

echo ">>> Iniciando bot..."
exec python /app/bot_main.py

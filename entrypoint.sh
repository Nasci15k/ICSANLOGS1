#!/bin/sh
# entrypoint.sh — Inicia s3d (Sia S3 gateway) + bot Telegram

S3D_DATA_DIR="${S3D_DATA_DIR:-/data}"

echo ">>> Iniciando s3d (S3 gateway para Sia Storage)..."
export S3D_DATA_DIR="${S3D_DATA_DIR:-/data}"
s3d -api.s3 :8000 &
S3D_PID=$!

for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
        echo ">>> s3d pronto!"
        break
    fi
    sleep 1
done

cleanup() {
    echo ">>> Encerrando..."
    kill $S3D_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

echo ">>> Iniciando bot..."
exec python /app/bot_main.py
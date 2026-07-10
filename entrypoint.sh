#!/bin/sh
# entrypoint.sh — Inicia s3d (Sia S3 gateway) + bot Telegram
set -e

export S3D_DATA_DIR="${S3D_DATA_DIR:-/data}"
export S3D_CONFIG_FILE="${S3D_CONFIG_FILE:-/data/s3d.yml}"
export S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:8000}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-JI55REOJFJPNKT3YP7BA}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-Ctj6dXADHDmY50f1PwjZg7fT+2r06DuoNwjKEYab}"
export BUCKET_NAME="${BUCKET_NAME:-cgu-logs}"

echo ">>> Iniciando s3d..."
s3d -api.s3 :8000 &
S3D_PID=$!

for i in $(seq 1 15); do
    if python -c "import socket;s=socket.socket();s.settimeout(1);s.connect(('localhost',8000));s.close()" 2>/dev/null; then
        echo ">>> s3d pronto!"
        break
    fi
    [ "$i" -eq 15 ] && echo ">>> AVISO: continuando mesmo assim"
    sleep 1
done

cleanup() { kill $S3D_PID 2>/dev/null; exit 0; }
trap cleanup SIGTERM SIGINT

echo ">>> Iniciando bot..."
exec python /app/bot_main.py
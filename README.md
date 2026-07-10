# telegram-duckdb-bot

Bot Telegram que consulta dados em arquivos Parquet via DuckDB + S3.

## Arquitetura

```
Parquet files (/data/parquet/data_*.parquet)
    ↓ (serve via S3 API na porta 8000)
Servidor S3 Python (prepare_s3_server.py)
    ↓ (DuckDB httpfs)
Bot Telegram responde queries SELECT
```

## Deploy no JustRunMy.App

### 1. Push do código para o GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/seuusuario/duckdb-bot.git
git push -u origin main
```

### 2. Conectar repositório no JustRunMy.App

- Crie um app do tipo **Docker**
- Aponte para seu repositório
- Configure as variáveis de ambiente abaixo

### 3. Fazer upload dos arquivos Parquet

Use o storage persistente do JustRunMy.App montado em `/data/parquet`.

**Opção A — Upload via web:**
1. Acesse o painel do JustRunMy.App
2. Faça upload dos 16 arquivos `data_*.parquet` para o volume persistente

**Opção B — Pack e upload via SCP:**
```bash
# No seu computador (onde estão os .parquet):
python upload_parquet.py pack ~/.logs-indexer-studio/parquet_export parquet.tar.gz

# Copie o arquivo para o servidor:
scp parquet.tar.gz usuario@server:/data/parquet.tar.gz

# No servidor:
cd /data && tar xzf parquet.tar.gz
```

### 4. Variáveis de ambiente

| Variável | Obrigatório | Descrição | Default |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | Token do bot Telegram | — |
| `S3_ENDPOINT` | ❌ | URL do servidor S3 interno | `http://localhost:8000` |
| `S3_ACCESS_KEY` | ❌ | Access key (não validada) | `minioadmin` |
| `S3_SECRET_KEY` | ❌ | Secret key (não validada) | `minioadmin` |
| `BUCKET_NAME` | ❌ | Nome do bucket S3 | `data` |
| `MAX_RESULTS` | ❌ | Máx linhas por query | `50` |
| `QUERY_TIMEOUT_SEC` | ❌ | Timeout da query (s) | `30` |
| `KEEP_ALIVE_INTERVAL` | ❌ | Ping interno (min) | `5` |

### 5. Build local (opcional)

```bash
docker build -t duckdb-bot .
docker run -p 8000:8000 -v /caminho/parquet:/data/parquet -e BOT_TOKEN=xxx duckdb-bot
```

## Uso do bot

Envie mensagens com queries SELECT. Use `{table}` como placeholder:

```
SELECT login, url FROM {table} WHERE login LIKE '%gmail%' LIMIT 5
```

Comandos:
- `/tables` — lista tabelas disponíveis
- `/schema <nome>` — mostra colunas
- `/start` — ajuda

## Arquivos do projeto

| Arquivo | Descrição |
|---|---|
| `Dockerfile` | Imagem Docker do bot |
| `entrypoint.sh` | Script de entrada (inicia S3 server + bot) |
| `bot_main.py` | Bot Telegram com DuckDB httpfs |
| `prepare_s3_server.py` | Servidor S3 Python (range requests, S3 API) |
| `upload_parquet.py` | Utilitário para empacotar/enviar Parquet |
| `requirements.txt` | Dependências Python |
| `export_script.py` | Exporta DuckDB → Parquet |

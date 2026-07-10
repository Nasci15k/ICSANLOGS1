import os, asyncio, logging, time, re
from typing import Optional
import duckdb
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "data")

TABLE_WHITELIST = set(t.strip() for t in os.environ.get("TABLE_WHITELIST", "").split(",") if t.strip())
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "50"))
QUERY_TIMEOUT_SEC = int(os.environ.get("QUERY_TIMEOUT_SEC", "30"))
KEEP_ALIVE_INTERVAL = int(os.environ.get("KEEP_ALIVE_INTERVAL", "5"))

SAFE_SELECT_RE = re.compile(r"^\s*SELECT\b.*\bFROM\b", re.IGNORECASE | re.DOTALL)
BLOCKED_KEYWORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|EXECUTE|COPY)\b", re.IGNORECASE)

_conn: Optional[duckdb.DuckDBPyConnection] = None

def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(":memory:")
        _conn.execute("INSTALL httpfs; LOAD httpfs")
        _conn.execute("SET s3_endpoint = '" + S3_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/") + "'")
        _conn.execute("SET s3_access_key_id = '" + S3_ACCESS_KEY + "'")
        _conn.execute("SET s3_secret_access_key = '" + S3_SECRET_KEY + "'")
        _conn.execute("SET s3_url_style = 'path'")
        _conn.execute("SET s3_use_ssl = " + ("true" if S3_ENDPOINT.startswith("https") else "false"))
        log.info("DuckDB conectado via httpfs -> %s", S3_ENDPOINT)
    return _conn

def sanitize_query(text: str) -> Optional[str]:
    raw = text.strip()
    if not raw: return None
    if not SAFE_SELECT_RE.match(raw): return None
    if BLOCKED_KEYWORDS.search(raw): return None
    return raw

def build_sql(query: str) -> str:
    # Substitui {table} por read_parquet com glob
    parquet_url = f"s3://{BUCKET_NAME}/data_*.parquet"
    return query.replace("{table}", f"read_parquet('{parquet_url}')") + f" LIMIT {MAX_RESULTS}"

def format_rows(columns: list, rows: list) -> str:
    if not rows: return "0 resultados."
    header = " | ".join(str(c) for c in columns)
    sep = "-" * min(40, len(header))
    lines = [header, sep]
    for row in rows[:MAX_RESULTS]:
        vals = []
        for v in row:
            s = str(v) if v is not None else "NULL"
            if len(s) > 80: s = s[:77] + "..."
            vals.append(s)
        lines.append(" | ".join(vals))
    if len(rows) > MAX_RESULTS:
        lines.append(f"... e mais {len(rows) - MAX_RESULTS} linhas")
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envie uma query SELECT para consultar os dados.\n\n"
        "Use `{table}` como placeholder.\n"
        "Ex: SELECT login, url FROM {table} WHERE login LIKE '%gmail%' LIMIT 5\n\n"
        "Comandos: /tables, /schema"
    )

async def list_tables(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        url = f"s3://{BUCKET_NAME}/"
        rs = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: conn.execute(f"SELECT DISTINCT filename FROM glob('{url}*.parquet')").fetchall()),
            timeout=10)
        tables = sorted(set(r[0].replace(".parquet", "") for r in rs))
        if not tables:
            await update.message.reply_text("Nenhuma tabela encontrada.")
            return
        msg = "Tabelas disponíveis:\n" + "\n".join(f"  - `{t}`" for t in tables)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

async def schema_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Use: /schema <nome>")
        return
    name = args[0]
    try:
        conn = get_conn()
        url = f"s3://{BUCKET_NAME}/{name}.parquet"
        rs = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: conn.execute(f"DESCRIBE read_parquet('{url}')").fetchall()),
            timeout=10)
        if not rs:
            await update.message.reply_text(f"Tabela '{name}' nao encontrada.")
            return
        lines = [f"Colunas de '{name}':"]
        for col, dtype in rs:
            lines.append(f"  {col}: {dtype}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    query = sanitize_query(text)
    if query is None:
        await update.message.reply_text("Envie apenas SELECT. Comandos: /start, /tables, /schema")
        return

    if "{table}" not in query:
        await update.message.reply_text("Use `{table}` como placeholder. Ex: SELECT * FROM {table} LIMIT 5")
        return

    sql = build_sql(query)
    conn = get_conn()
    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: conn.execute(sql).fetchall()),
            timeout=QUERY_TIMEOUT_SEC)
        columns = [desc[0] for desc in conn.description]
        formatted = format_rows(columns, result)
        msg = f"`{sql[:200]}{'...' if len(sql)>200 else ''}`\n\n```\n{formatted}\n```"
        if len(msg) > 4000: msg = msg[:3997] + "..."
        await update.message.reply_text(msg, parse_mode="Markdown")
    except asyncio.TimeoutError:
        await update.message.reply_text("Query excedeu o tempo limite.")
    except Exception as e:
        await update.message.reply_text(f"Erro: {e}")

async def keep_alive():
    while True:
        await asyncio.sleep(KEEP_ALIVE_INTERVAL * 60)
        try:
            get_conn().execute("SELECT 1")
            log.debug("Keep-alive OK")
        except Exception as e:
            log.warning("Keep-alive falhou: %s", e)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tables", list_tables))
    app.add_handler(CommandHandler("schema", schema_table))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(keep_alive())

    log.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()

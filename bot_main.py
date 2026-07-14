import io, os, asyncio, logging, re, threading, time, uuid
import urllib.request
from typing import Optional
import duckdb
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from admin_panel import get_tier, get_planos, get_message, get_group, get_support, get_blocked, get_timeout, start as admin_start

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8000")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "JI55REOJFJPNKT3YP7BA")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "Ctj6dXADHDmY50f1PwjZg7fT+2r06DuoNwjKEYab")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "cgu-logs")
HEALTH_PORT = int(os.environ.get("PORT", "8080"))
QUERY_TIMEOUT = int(os.environ.get("QUERY_TIMEOUT", "300"))
SEPARATOR = "─" * 30

_pending = {}

def upload_paste(content):
    data = content.encode("utf-8")
    req = urllib.request.Request("https://copyandpaste.at/api/log", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8").strip()

_queries = {}

def qcount(uid):
    key = f"{time.strftime('%Y-%m-%d')}:{uid}"
    return _queries.get(key, 0)

def qinc(uid):
    key = f"{time.strftime('%Y-%m-%d')}:{uid}"
    _queries[key] = _queries.get(key, 0) + 1

def _blocked_re():
    doms = get_blocked()
    if not doms:
        return re.compile(r'(?!x)x')
    return re.compile("|".join(doms), re.IGNORECASE)

async def check_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_user:
        return True
    group = get_group()
    if not group:
        return True
    try:
        member = await ctx.bot.get_chat_member(chat_id=group, user_id=update.effective_user.id)
        ok = member.status in ("member", "administrator", "creator", "restricted")
        if not ok:
            await update.message.reply_text(
                f"🔒 *Acesso restrito!*\n\nVocê precisa entrar no grupo {group} para usar o bot.\n"
                f"https://t.me/{group.lstrip('@')}",
                parse_mode="Markdown")
        return ok
    except Exception:
        return True

TABLE_S3 = f"read_parquet('s3://{BUCKET_NAME}/data_*.parquet')"
TABLE = TABLE_S3
LOCAL_DB = "/data/logs.duckdb"
_conn: Optional[duckdb.DuckDBPyConnection] = None

def get_conn():
    global _conn
    if _conn is None:
        _conn = duckdb.connect(":memory:")
        _conn.execute("INSTALL httpfs; LOAD httpfs")
        ep = S3_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/")
        _conn.execute(f"SET s3_endpoint='{ep}'")
        _conn.execute(f"SET s3_access_key_id='{S3_ACCESS_KEY}'")
        _conn.execute(f"SET s3_secret_access_key='{S3_SECRET_KEY}'")
        _conn.execute("SET s3_url_style='path'")
        _conn.execute(f"SET s3_use_ssl={'true' if S3_ENDPOINT.startswith('https') else 'false'}")
    return _conn

def warmup():
    global TABLE
    try:
        wc = duckdb.connect(":memory:")
        wc.execute("INSTALL httpfs; LOAD httpfs")
        ep = S3_ENDPOINT.replace("http://", "").replace("https://", "").rstrip("/")
        wc.execute(f"SET s3_endpoint='{ep}'")
        wc.execute(f"SET s3_access_key_id='{S3_ACCESS_KEY}'")
        wc.execute(f"SET s3_secret_access_key='{S3_SECRET_KEY}'")
        wc.execute("SET s3_url_style='path'")
        wc.execute(f"SET s3_use_ssl={'true' if S3_ENDPOINT.startswith('https') else 'false'}")

        if os.path.exists(LOCAL_DB):
            get_conn().execute(f"ATTACH '{LOCAL_DB}' AS logs (READ_ONLY)")
            TABLE = "logs.data"
            log.info("WARMUP PRONTO")
        else:
            log.info("Warm-up: importando dados para cache local...")
            wc.execute(f"ATTACH '{LOCAL_DB}' AS logs")
            wc.execute(f"CREATE TABLE logs.data AS SELECT * FROM {TABLE_S3}")
            wc.execute("CHECKPOINT")
            get_conn().execute(f"ATTACH '{LOCAL_DB}' AS logs (READ_ONLY)")
            TABLE = "logs.data"
            log.info("WARMUP PRONTO")
        wc.close()
    except Exception as e:
        log.warning("Cache local indisponível: %s. Usando S3 httpfs.", e)

def check_health():
    try:
        conn = get_conn()
        conn.execute("SELECT 1")
        log.info("DuckDB OK")
        return True
    except Exception as e:
        log.error("DuckDB FAIL: %s", e)
        return False

def run_sql(sql):
    conn = get_conn()
    rows = conn.execute(sql).fetchall()
    cols = [d[0] for d in conn.description]
    return rows, cols

def build_file_content(rows, cols, label, elapsed, tier):
    support = get_support()
    lines = []
    if tier == 0:
        banner = get_message("free_banner").replace("\\n", "\n")
        lines.append(f"🧿 Icsan Logs • {support} (MODO GRATUITO)")
        lines.append("")
        lines.append(banner)
        lines.append("")
    elif tier == 1:
        banner = get_message("basic_banner").replace("\\n", "\n")
        lines.append(f"💎 Icsan Logs • {support} (PLANO BASICO)")
        lines.append("")
        lines.append(banner)
        lines.append("")
    lines.append(f"☑️ {label}")
    lines.append(f"🧵 LINHAS / ROWS: {len(rows)}")
    lines.append(f"⌛️ TIME: {elapsed:.2f}s")
    lines.append("")
    for r in rows:
        row = dict(zip(cols, r))
        lines.append(SEPARATOR)
        lines.append(f"Login: {row.get('login', '-')}")
        lines.append(f"Senha: {row.get('senha', '-')}")
        lines.append(SEPARATOR)
    return "\n".join(lines)

async def safe_query(update, sql, label, term=None):
    uid = update.effective_user.id
    tier = get_tier(uid)
    planos = get_planos()
    plano_free = planos.get("free", {})
    daily = plano_free.get("daily_limit", 5)
    blocked_re = _blocked_re()

    if tier == 0:
        if term and blocked_re.search(term):
            msg = get_message("blocked_gov").replace("\\n", "\n")
            await update.message.reply_text(msg, parse_mode="Markdown")
            return
        if daily > 0 and qcount(uid) >= daily:
            msg = get_message("daily_limit").replace("\\n", "\n").replace("{limit}", str(daily))
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

    wait_msg = await update.message.reply_text("⏳ *Processando consulta...*", parse_mode="Markdown")
    t0 = time.time()
    async def progress():
        while True:
            await asyncio.sleep(10)
            try:
                await wait_msg.edit_text(f"⏳ *Processando... ({int(time.time()-t0)}s)*", parse_mode="Markdown")
            except:
                break
    prog = asyncio.ensure_future(progress())
    try:
        loop = asyncio.get_event_loop()
        timeout = get_timeout()
        rows, cols = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: run_sql(sql)),
            timeout=timeout)
        prog.cancel()
        elapsed = time.time() - t0
        if not rows:
            await wait_msg.edit_text(
                f"☑️ {label}\n🧵 LINHAS / ROWS: 0\n⌛️ TIME: {elapsed:.2f}s\n\n— vazio / empty —")
            return
        if tier == 0:
            qinc(uid)
            pct = plano_free.get("percent", 20)
        elif tier == 1:
            pct = planos.get("basic", {}).get("percent", 50)
        else:
            pct = 100
        if pct < 100:
            rows = rows[:max(1, len(rows) * pct // 100)]
        content = build_file_content(rows, cols, label, elapsed, tier)
        key = uuid.uuid4().hex
        _pending[key] = content
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Arquivo .txt", callback_data=f"txt_{key}"),
             InlineKeyboardButton("🔗 Link CopyPaste", callback_data=f"paste_{key}")],
            [InlineKeyboardButton("🔍 Nova busca", switch_inline_query_current_chat="/search ")],
        ])
        if tier == 0:
            remaining = max(0, daily - qcount(uid))
            status = f"🧿 GRÁTIS ({remaining}/{daily} consultas restantes)"
        elif tier == 1:
            status = "💎 PLANO BASICO"
        else:
            status = "💎 PLANO VIP — 100%"
        await wait_msg.edit_text(
            f"{status}\n\n📥 Escolha o formato:",
            parse_mode="Markdown", reply_markup=kb)
    except asyncio.TimeoutError:
        prog.cancel()
        await wait_msg.edit_text("⌛️ Query excedeu o tempo limite.\n⏱ Timeout.")
    except Exception as e:
        prog.cancel()
        await wait_msg.edit_text(f"❌ Erro: {e}")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Buscar URL", switch_inline_query_current_chat="/url ")],
        [InlineKeyboardButton("👤 Buscar Login", switch_inline_query_current_chat="/login ")],
        [InlineKeyboardButton("🔑 Buscar Senha", switch_inline_query_current_chat="/senha ")],
    ])
    await update.message.reply_text(
        "🇧🇷 *ICSAN LOGS*\n"
        "Consulta de credenciais vazadas.\n\n"
        "🇺🇸 *ICSAN LOGS*\n"
        "Leaked credentials query.\n\n"
        "`/url site.com` — Buscar por URL\n"
        "`/login user@` — Buscar por login\n"
        "`/senha 123` — Buscar por senha\n"
        "`/search termo` — Busca geral\n"
        "`/query SELECT...` — SQL direto (use `{table}`)\n"
        "`/planos` — Planos premium\n"
        "`/help` — Ajuda",
        parse_mode="Markdown", reply_markup=kb)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    p = get_planos()
    f = p.get("free", {})
    await update.message.reply_text(
        "🇧🇷 *ICSAN LOGS — COMANDOS*\n"
        "`/url exemplo.com` — Busca urls contendo \"exemplo.com\"\n"
        "`/login gmail` — Busca logins contendo \"gmail\"\n"
        "`/senha 123456` — Busca senhas com \"123456\"\n"
        "`/search admin` — Busca em todos os campos\n"
        "`/query SELECT * FROM {table} LIMIT 5` — SQL livre\n"
        "`/planos` — Ver planos\n\n"
        "Resultados: `.txt` ou link CopyPaste.\n"
        f"Grátis: {f.get('percent', 20)}% | {f.get('daily_limit', 5)}/dia | /planos\n\n"
        "🇺🇸 *ICSAN LOGS — COMMANDS*\n"
        "Same as above.\n"
        "Results: `.txt` or CopyPaste link. /planos for tiers."
    )

def _sql_escape(s):
    return s.replace("'", "''")

async def cmd_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    term = " ".join(ctx.args)
    if not term:
        await update.message.reply_text("Use: /url site.com")
        return
    safe = _sql_escape(term)
    sql = f"SELECT login, senha, url FROM {TABLE} WHERE url LIKE '%{safe}%'"
    await safe_query(update, sql, f"URL: {term}", term)

async def cmd_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    term = " ".join(ctx.args)
    if not term:
        await update.message.reply_text("Use: /login email@")
        return
    safe = _sql_escape(term)
    sql = f"SELECT login, senha, url FROM {TABLE} WHERE login LIKE '%{safe}%'"
    await safe_query(update, sql, f"LOGIN: {term}", term)

async def cmd_senha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    term = " ".join(ctx.args)
    if not term:
        await update.message.reply_text("Use: /senha 123")
        return
    safe = _sql_escape(term)
    sql = f"SELECT login, senha, url FROM {TABLE} WHERE senha LIKE '%{safe}%'"
    await safe_query(update, sql, f"SENHA: {term}", term)

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    term = " ".join(ctx.args)
    if not term:
        await update.message.reply_text("Use: /search termo")
        return
    safe = _sql_escape(term)
    sql = f"SELECT login, senha, url FROM {TABLE} WHERE login LIKE '%{safe}%' OR senha LIKE '%{safe}%' OR url LIKE '%{safe}%'"
    await safe_query(update, sql, f"SEARCH: {term}", term)

async def cmd_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    text = " ".join(ctx.args)
    if not text:
        await update.message.reply_text("Use: /query SELECT * FROM {table} LIMIT 5")
        return
    if not re.match(r"^\s*SELECT\b", text, re.IGNORECASE):
        await update.message.reply_text("❌ Apenas SELECT é permitido.")
        return
    if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|EXECUTE|COPY)\b", text, re.IGNORECASE):
        await update.message.reply_text("❌ Comando bloqueado.")
        return
    sql = text.replace("{table}", TABLE)
    await safe_query(update, sql, "QUERY")

async def planos_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    p = get_planos()
    f, b, v = p.get("free", {}), p.get("basic", {}), p.get("vip", {})
    support = get_support()
    blocked = ", ".join(f.get("blocked_domains", [])) if f.get("blocked_domains") else "Nenhum"
    msg = (
        "📋 *ICSAN LOGS — PLANOS*\n\n"
        f"🎫 *GRÁTIS* — R$ 0\n"
        f"• {f.get('percent', 20)}% dos resultados\n"
        f"• {f.get('daily_limit', 5)} consultas/dia\n"
        f"• Bloqueados: {blocked}\n\n"
        f"💎 *BASICO* — R$ {b.get('price', '9,90')}/mês\n"
        f"• {b.get('percent', 50)}% dos resultados\n"
        f"• Consultas ilimitadas\n"
        f"• Todos os domínios\n\n"
        f"👑 *VIP* — R$ {v.get('price', '29,90')}/mês\n"
        f"• {v.get('percent', 100)}% dos resultados\n"
        f"• Consultas ilimitadas\n"
        f"• Todos os domínios liberados\n\n"
        f"📲 Pagamento: PIX\n"
        f"👤 Suporte: {support}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_group(update, ctx):
        return
    text = update.message.text.strip()
    if text.startswith("/"): return
    parts = text.split(None, 1)
    ctx.args = [parts[1]] if len(parts) > 1 else []
    cmd = parts[0].lower()
    if cmd in ("url", "/url"):
        await cmd_url(update, ctx)
    elif cmd in ("login", "/login"):
        await cmd_login(update, ctx)
    elif cmd in ("senha", "/senha", "pass"):
        await cmd_senha(update, ctx)
    else:
        ctx.args = [text]
        await cmd_search(update, ctx)

async def format_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, key = query.data.split("_", 1)
    content = _pending.pop(key, None)
    if content is None:
        await query.edit_message_text("⚠️ Resultado expirado. Faça a busca novamente.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Nova busca", switch_inline_query_current_chat="/search ")],
    ])
    if action == "txt":
        f = io.BytesIO(content.encode("utf-8"))
        f.name = "resultado.txt"
        await query.message.reply_document(document=f, filename="resultado.txt")
        await query.edit_message_text("📁 *Icsan Logs* — arquivo enviado!", parse_mode="Markdown", reply_markup=kb)
    elif action == "paste":
        loop = asyncio.get_event_loop()
        try:
            url = await loop.run_in_executor(None, upload_paste, content)
            await query.edit_message_text(
                f"🔗 *Link:* {url}", parse_mode="Markdown", reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao criar paste: {e}")

async def keep_alive():
    while True:
        await asyncio.sleep(300)
        try:
            get_conn().execute("SELECT 1")
        except Exception:
            pass

def main():
    admin_start(HEALTH_PORT)
    check_health()
    threading.Thread(target=warmup, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("login", cmd_login))
    app.add_handler(CommandHandler("senha", cmd_senha))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("query", cmd_query))
    app.add_handler(CommandHandler("planos", planos_cmd))
    app.add_handler(CallbackQueryHandler(format_choice, pattern=r"^(txt|paste)_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(keep_alive())

    log.info("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()

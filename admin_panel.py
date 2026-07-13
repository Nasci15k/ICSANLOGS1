import json, os, base64, logging, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

log = logging.getLogger(__name__)

CONFIG_PATH = "/data/bot_config.json"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

DEFAULT_CONFIG = {
    "query_timeout": 300,
    "planos": {
        "free": {
            "percent": 20,
            "daily_limit": 5,
            "blocked_domains": ["\\.gov"]
        },
        "basic": {
            "price": "9,90",
            "percent": 50,
            "daily_limit": 0
        },
        "vip": {
            "price": "29,90",
            "percent": 100,
            "daily_limit": 0
        }
    },
    "paid_users": {},
    "support_contact": "@suportefetchbrasil",
    "group": "@icsanlogs",
    "messages": {
        "blocked_gov": "🔒 *Acesso restrito!*\\n\\nUsuários gratuitos não podem consultar domínios .gov.\\n💎 Assine um plano em /planos.",
        "daily_limit": "📊 *Limite diário atingido!*\\n\\nVocê usou suas {limit} consultas gratuitas de hoje.\\n💎 Assine um plano em /planos.",
        "free_banner": "20% dos resultados liberados. Assine um plano em /planos.",
        "basic_banner": "50% dos resultados liberados. Assine o VIP em /planos para 100%."
    }
}

_config: Optional[dict] = None

def load():
    global _config
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _config = json.load(f)
            log.info("Config loaded from %s", CONFIG_PATH)
            return
    except Exception as e:
        log.warning("Failed to load config: %s", e)
    _config = DEFAULT_CONFIG.copy()
    save()

def save():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_config, f, indent=2, ensure_ascii=False)

def get():
    if _config is None:
        load()
    return _config

def get_tier(uid):
    return get().get("paid_users", {}).get(str(uid), 0)

def get_planos():
    return get().get("planos", DEFAULT_CONFIG["planos"])

def get_message(key):
    return get().get("messages", DEFAULT_CONFIG["messages"]).get(key, "")

def get_group():
    return get().get("group", "@icsanlogs")

def get_support():
    return get().get("support_contact", "@suportefetchbrasil")

def get_blocked():
    return get().get("planos", {}).get("free", {}).get("blocked_domains", ["\\.gov"])

def get_timeout():
    return get().get("query_timeout", 300)

PAGE_ADMIN = """<!DOCTYPE html>
<html lang=pt-BR>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Icsan Logs — Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}}
h1,h2{{color:#58a6ff}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin:16px 0}}
label{{display:block;margin:8px 0 4px;font-weight:600;font-size:13px}}
input,textarea,select{{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;margin-bottom:8px}}
input:focus,textarea:focus{{border-color:#58a6ff;outline:none}}
textarea{{font-family:monospace;min-height:60px}}
.row{{display:flex;gap:12px}}
.row>*{{flex:1}}
.btn{{background:#238636;color:#fff;border:none;padding:10px 24px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer}}
.btn:hover{{background:#2ea043}}
.btn.danger{{background:#da3633}}
.btn.danger:hover{{background:#f85149}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #30363d}}
th{{color:#8b949e;font-weight:600}}
.badge{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}}
.free{{background:#21262d;color:#8b949e}}
.basic{{background:#1a3a1a;color:#3fb950}}
.vip{{background:#3d1f00;color:#d29922}}
a{{color:#58a6ff}}
</style>
</head>
<body>
<h1>⚙ Icsan Logs — Admin Panel</h1>
<p style=color:#8b949e;margin:4px 0 20px>Configure tudo do bot. <a href=/admin/logout>Logout</a></p>

<form method=POST action=/admin/save enctype=application/x-www-form-urlencoded>

<div class=card>
<h2>🎫 Plano Grátis</h2>
<div class=row>
<div><label>% Resultados</label><input type=number name=free_percent value="{free_percent}" min=1 max=100></div>
<div><label>Consultas/dia</label><input type=number name=free_daily value="{free_daily}" min=0></div>
</div>
<label>Domínios bloqueados (regex, um por linha)</label>
<textarea name=free_blocked>{free_blocked}</textarea>
</div>

<div class=card>
<h2>💎 Plano Básico</h2>
<div class=row>
<div><label>Preço (R$)</label><input name=basic_price value="{basic_price}"></div>
<div><label>% Resultados</label><input type=number name=basic_percent value="{basic_percent}" min=1 max=100></div>
</div>
</div>

<div class=card>
<h2>👑 Plano VIP</h2>
<div class=row>
<div><label>Preço (R$)</label><input name=vip_price value="{vip_price}"></div>
<div><label>% Resultados</label><input type=number name=vip_percent value="{vip_percent}" min=1 max=100></div>
</div>
</div>

<div class=card>
<h2>👤 Usuários Pagantes</h2>
<p style=font-size:13px;color:#8b949e>ID do Telegram : tier (1=Básico, 2=VIP). Um por linha.</p>
<textarea name=paid_list rows=4>{paid_list}</textarea>
</div>

<div class=card>
<h2>🔧 Geral</h2>
<div class=row>
<div><label>Grupo Telegram</label><input name=group value="{group}"></div>
<div><label>Suporte</label><input name=support value="{support}"></div>
</div>
<div class=row>
<div><label>Timeout consulta (segundos)</label><input type=number name=query_timeout value="{query_timeout}" min=10 max=3600></div>
<div></div>
</div>
</div>

<div class=card>
<h2>💬 Mensagens do Bot</h2>
<label>.gov bloqueado</label>
<textarea name=msg_gov>{msg_gov}</textarea>
<label>Limite diário (use {{limit}})</label>
<textarea name=msg_daily>{msg_daily}</textarea>
<label>Banner Grátis</label>
<textarea name=msg_free>{msg_free}</textarea>
<label>Banner Básico</label>
<textarea name=msg_basic>{msg_basic}</textarea>
</div>

<button class=btn type=submit>💾 Salvar Configuração</button>
</form>

<div class=card>
<h2>📊 Estatísticas</h2>
<table>
<tr><th>Métrica</th><th>Valor</th></tr>
<tr><td>Usuários pagantes</td><td>{paid_count}</td></tr>
<tr><td>Plano Grátis %</td><td>{free_percent}%</td></tr>
<tr><td>Plano Básico %</td><td>{basic_percent}%</td></tr>
<tr><td>Plano VIP %</td><td>{vip_percent}%</td></tr>
</table>
</div>

</body>
</html>"""

class AdminHandler(BaseHTTPRequestHandler):
    def _auth(self):
        h = self.headers.get("Authorization", "")
        if not h.startswith("Basic "):
            return False
        try:
            dec = base64.b64decode(h[6:]).decode()
            _, pw = dec.split(":", 1)
            return pw == ADMIN_PASSWORD
        except Exception:
            return False

    def _fail(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Icsan Logs Admin"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Unauthorized")

    def _html(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _redirect(self, path):
        self.send_response(302)
        self.send_header("Location", path)
        self.end_headers()

    def do_GET(self):
        if self.path == "/admin/logout":
            self._fail()
            return
        if self.path in ("/admin", "/admin/"):
            if not self._auth():
                self._fail()
                return
            self._html(200, _render_admin())
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        if self.path == "/admin/save":
            if not self._auth():
                self._fail()
                return
            cl = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(cl).decode("utf-8")
            _apply_form(body)
            self._redirect("/admin")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass

def _render_admin():
    c = get()
    p = c["planos"]
    free = p["free"]
    basic = p["basic"]
    vip = p["vip"]
    paid = c.get("paid_users", {})
    msgs = c.get("messages", DEFAULT_CONFIG["messages"])
    fmt = lambda s: s.replace("\\n", "\n")
    return PAGE_ADMIN.format(
        free_percent=free["percent"],
        free_daily=free["daily_limit"],
        free_blocked="\n".join(free.get("blocked_domains", [])),
        basic_price=basic.get("price", "9,90"),
        basic_percent=basic["percent"],
        vip_price=vip.get("price", "29,90"),
        vip_percent=vip["percent"],
        paid_list="\n".join(f"{k}:{v}" for k, v in paid.items()),
        group=c.get("group", "@icsanlogs"),
        support=c.get("support_contact", "@suportefetchbrasil"),
        query_timeout=c.get("query_timeout", 300),
        msg_gov=fmt(msgs.get("blocked_gov", "")),
        msg_daily=fmt(msgs.get("daily_limit", "")),
        msg_free=fmt(msgs.get("free_banner", "")),
        msg_basic=fmt(msgs.get("basic_banner", "")),
        paid_count=len(paid),
    )

def _apply_form(body):
    import urllib.parse
    d = urllib.parse.parse_qs(body, keep_blank_values=True)
    gv = lambda k, default="": d.get(k, [default])[0]
    gi = lambda k, default=0: int(gv(k, str(default)))
    c = get()
    c["planos"]["free"]["percent"] = gi("free_percent", 20)
    c["planos"]["free"]["daily_limit"] = gi("free_daily", 5)
    c["planos"]["free"]["blocked_domains"] = [x.strip() for x in gv("free_blocked", "").split("\n") if x.strip()]
    c["planos"]["basic"]["price"] = gv("basic_price", "9,90")
    c["planos"]["basic"]["percent"] = gi("basic_percent", 50)
    c["planos"]["vip"]["price"] = gv("vip_price", "29,90")
    c["planos"]["vip"]["percent"] = gi("vip_percent", 100)
    paid = {}
    for line in gv("paid_list", "").split("\n"):
        line = line.strip()
        if ":" in line:
            uid, tier = line.split(":", 1)
            paid[uid.strip()] = int(tier.strip())
    c["paid_users"] = paid
    c["query_timeout"] = gi("query_timeout", 300)
    c["group"] = gv("group", "@icsanlogs").strip()
    c["support_contact"] = gv("support", "@suportefetchbrasil").strip()
    esc_nl = lambda s: s.replace("\r\n", "\n").replace("\n", "\\n")
    c["messages"]["blocked_gov"] = esc_nl(gv("msg_gov", ""))
    c["messages"]["daily_limit"] = esc_nl(gv("msg_daily", ""))
    c["messages"]["free_banner"] = esc_nl(gv("msg_free", ""))
    c["messages"]["basic_banner"] = esc_nl(gv("msg_basic", ""))
    save()
    log.info("Config saved via admin panel")

def start(port):
    load()
    srv = HTTPServer(("0.0.0.0", port), AdminHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    log.info("Admin panel on port %d", port)
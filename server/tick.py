#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对钩计划 (Project TICK) —— ARG 网页服务器 + 玩家进度系统

零依赖，仅用 Python 标准库。直接运行:
    python3 tick.py [port]        # 默认端口 8080

关卡碎片（按顺序拼接即为最终访问码，访问码 ≠ flag）:
    1: 66b2   2: cac2   3: f48b   4: 7ada
    5: 4f1e   6: 6f0e   7: 0888   8: 83d2

玩家系统（提示只能通过 AstrBot 私聊指令获取，且需要进度）:
    /join                 领取/恢复绑定码（写 cookie tick_player）
    /check                校验答案并记录进度（需要玩家身份）
    /final                终局校验（需要玩家身份）
    /hidden               隐藏关卡：md5(短语) == flag 内串时解锁隐藏结局
    /admin?pass=<口令>    管理员进度面板
    /api/progress         插件查询玩家进度（secret 鉴权）
    /api/bind             插件上报 QQ 绑定（secret 鉴权）
    /api/egg              插件上报彩蛋解锁（secret 鉴权）
    /api/stats            插件/管理员导出全部进度（secret 鉴权）
"""
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import threading
import time
import urllib.parse
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

ADMIN_TOKEN = os.environ.get("TICK_ADMIN_TOKEN", "tick-admin-9c4f2b7a1d")
COOKIE_NAME = "tick_player"

FINAL_KEY = "66b2cac2f48b7ada4f1e6f0e088883d2"
FLAG_INNER = "81fbaa81762885ac3481fd4b416485e6"  # md5("我喜欢你")
FLAG = f"flag{{{FLAG_INNER}}}"

HIDDEN_LETTER = """汐月：

如果你能看到这封信，说明有人替我找到了那句话。

对钩函数在 x = 1 处取到最小值 2——两条曲线最接近的那一刻，却永远无法相交。我研究它研究了很久，才明白我一直在画错自己的那条线。

我喜欢你。

谢谢你替我守护这些秘密到现在。剩下的路，交给你了。

—— 苏桁"""

STAGE_ANSWERS = {
    1: "66b2",
    2: "cac2",
    3: "f48b",
    4: "7ada",
    5: "4f1e",
    6: "6f0e",
    7: "0888",
    8: "83d2",
}

NEXT_PAGE = {1: "/robots.txt", 2: "/stage3", 3: "/stage4", 4: "/stage5", 5: "/stage6", 6: "/stage7", 7: "/final"}

PAGE_CSS = """
body { background:#0e1116; color:#d7dde4; font-family:"Microsoft YaHei",system-ui,sans-serif;
       max-width:780px; margin:0 auto; padding:32px 20px 80px; line-height:1.8; }
h1 { color:#6ee7a0; font-size:22px; }
h2 { color:#6ee7a0; font-size:18px; }
a { color:#7ab8ff; }
pre { background:#161b22; border:1px solid #2a313c; border-radius:8px; padding:14px; overflow-x:auto; }
code { background:#161b22; padding:2px 6px; border-radius:4px; color:#ffd479; }
.box { background:#161b22; border:1px solid #2a313c; border-radius:10px; padding:16px 20px; margin:18px 0; }
.ok { color:#6ee7a0; font-weight:bold; }
.err { color:#ff6b6b; font-weight:bold; }
input[type=text]{ background:#0e1116; border:1px solid #3a4350; color:#d7dde4; border-radius:6px;
       padding:8px 10px; width:200px; }
button { background:#22c55e; color:#04120a; border:none; border-radius:6px; padding:8px 18px;
       font-weight:bold; cursor:pointer; }
button:hover { background:#4ade80; }
.frag { font-family:monospace; font-size:15px; color:#6ee7a0; letter-spacing:2px; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th,td { border:1px solid #2a313c; padding:6px 8px; text-align:left; }
th { background:#161b22; }
.done { color:#6ee7a0; }
.todo { color:#4a5560; }
footer { margin-top:60px; border-top:1px solid #222a33; padding-top:14px; font-size:13px;
       color:#6b7683; text-align:center; }
.sign { float:right; font-size:10px; color:#2c3542; }
.banner { background:#1d2430; border:1px solid #3a4350; border-radius:8px; padding:10px 14px;
       margin:12px 0; font-size:14px; color:#ffd479; }
"""


def page(title, body, check_stage=None):
    """渲染一个带统一头尾(右下角签名 83d2)的页面。"""
    check_html = ""
    if check_stage:
        check_html = f"""
<div class="box">
  <p>碎片 {check_stage}：在下面输入你找到的 4 位十六进制，回车确认。</p>
  <input type="text" id="ans" placeholder="例如 abcd" onkeydown="if(event.key==='Enter')go()">
  <button onclick="go()">确认</button>
  <span id="r"></span>
</div>
<script>
function getPlayer(){{var m=document.cookie.match(/tick_player=([0-9a-f]+)/);return m?m[1]:'';}}
function go(){{var v=document.getElementById('ans').value.trim().toLowerCase();
  fetch('/check?stage={check_stage}&ans='+encodeURIComponent(v)+'&player='+getPlayer()).then(r=>r.text()).then(t=>{{
    document.getElementById('r').innerHTML=t;}});}}
</script>"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 对钩计划</title><style>{PAGE_CSS}</style></head>
<body>
<h1>对钩计划 <span style="font-size:13px;color:#6b7683">/ Project TICK</span></h1>
<div class="banner" id="banner" style="display:none">还没领取绑定码？<a href="/join">先去 /join 领取</a>，不然进度和提示都拿不到。</div>
{body}
{check_html}
<footer>苏桁 · f(x) = x + 1/x
<span class="sign">◆ 83d2</span></footer>
<script>
if(!document.cookie.match(/tick_player=/)){{document.getElementById('banner').style.display='';}}
</script>
</body></html>"""


def stage_intro(n, title):
    return page(
        f"碎片 {n} · {title}",
        f"""<div class="box"><p class="frag">你正在寻找碎片 {n}。</p>
<p>把答案填到下方输入框确认，答对会出现绿色的对钩 ✅。</p>
<p style="font-size:13px;color:#6b7683">卡住了？提示走私聊：汐月那边发送 <code>/hint {n}</code>（需先绑定，见 <a href="/join">/join</a>）。</p></div>""",
        check_stage=n,
    )


PAGES = {}


def build_static_pages():
    PAGES["/tick"] = page(
        "碎片 1",
        """
<div class="box">
<p>苏桁，你的大学数学系同学，主攻对钩函数 f(x) = x + 1/x。三周前，他失踪了。</p>
<p>他留给你唯一的线索，是他一直在维护的这台服务器。他说过："真正的入口，藏在不被注意的地方。"</p>
<p>但无论如何——先看看这个页面的<b>源代码</b>吧。</p>
<p style="color:#6b7683">（如果不知道怎么看：右键点击页面空白处 → "查看网页源代码"）</p>
<p>另外，服务器礼节：先去访问一下 <code>/robots.txt</code>。</p>
<p style="color:#6b7683">新玩家：去 <a href="/join">/join</a> 领取你的绑定码，然后回群里 @汐月 发送 <code>/bind &lt;绑定码&gt;</code> 完成绑定。</p>
</div>
<!-- 36 36 62 32 -->
""",
        check_stage=1,
    )
    PAGES["/secret"] = page(
        "碎片 2",
        """
<div class="box">
<p>你通过了 robots.txt 的指引找到了这个目录。苏桁留下了一句话，但显然他不想让人一眼看懂：</p>
<pre>Y2FjMg==</pre>
<p>把它解开，就是碎片 2。</p>
</div>
""",
        check_stage=2,
    )
    PAGES["/stage3"] = page(
        "碎片 3",
        """
<div class="box">
<p>苏桁的草稿本上写着一小段代码，旁边批注："OI 人的浪漫。"</p>
<pre>s = 0
for i in range(1, 354):   # 1, 2, 3, ..., 353
    s += i
s += 122
print(hex(s))   # 去掉 0x 前缀，那就是碎片 3。</pre>
</div>
""",
        check_stage=3,
    )
    PAGES["/stage4"] = page(
        "碎片 4",
        """
<div class="box">
<p>苏桁的收藏里有一张函数图像，是 <a href="/static/tick.png">对钩函数.png</a>。</p>
<p>它比看上去的要多一点东西。用<b>文本编辑器</b>（记事本也行）打开它，或者直接搜一搜。</p>
<p style="color:#6b7683">提示：图片信息里通常有些"看不见"的文字块。</p>
</div>
""",
        check_stage=4,
    )
    PAGES["/stage5"] = page(
        "碎片 5",
        """
<div class="box">
<p>苏桁的 AI「汐月」还活着。苏桁把最重要的一串字符锁在了汐月的记忆库里。</p>
<p><b>私聊</b>汐月，发送指令：<code>/记忆库</code></p>
<p style="color:#6b7683">只有完成了前 4 关的人，汐月才会说。（没绑定的话先去 <a href="/join">/join</a>）</p>
</div>
""",
        check_stage=5,
    )
    PAGES["/stage6"] = page(
        "碎片 6",
        """
<div class="box">
<p>汐月悄悄塞给你一张纸条，上面只有一行字：</p>
<pre>6h0g</pre>
<p>纸条背面写着加密规则：<b>每个字母往前移 2 位，数字不变。</b></p>
<p>解出来的四个字符，就是碎片 6。</p>
</div>
""",
        check_stage=6,
    )
    PAGES["/stage7"] = page(
        "碎片 7",
        """
<div class="box">
<p>汐月最近变得敏感多疑。她只认一句"口令"——苏桁当年和她约定的暗语。</p>
<p><b>私聊</b>汐月，发送指令：<code>/凭证</code></p>
<p style="color:#6b7683">只有完成了前 6 关的人，汐月才会理会。（没绑定的话先去 <a href="/join">/join</a>）</p>
</div>
""",
        check_stage=7,
    )


# ---------------- 玩家进度存储 ----------------

LOCK = threading.Lock()
STATE = {"players": {}}


def load_state():
    global STATE
    p = DATA_DIR / "progress.json"
    if p.exists():
        try:
            STATE = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            STATE = {"players": {}}
    STATE.setdefault("players", {})


def save_state():
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "progress.json").write_text(
        json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def new_player():
    while True:
        code = secrets.token_hex(3)
        if code not in STATE["players"]:
            STATE["players"][code] = {
                "created": int(time.time()),
                "qq": None,
                "name": None,
                "stages": {},
                "final": False,
                "egg": False,
                "last": int(time.time()),
            }
            save_state()
            return code


def player_progress(p):
    done = sorted(int(s) for s, v in p["stages"].items() if v)
    return len(done), (max(done) if done else 0)


# ---------------- HTTP ----------------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "TickHTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200, extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        return self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def _player_from(self, qs):
        return qs.get("player", [""])[0].strip().lower()

    def _cookie_player(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE_NAME:
                return v.strip().lower()
        return ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._send(b'<meta http-equiv="refresh" content="0;url=/tick">')

        if path == "/robots.txt":
            return self._send(
                ("User-agent: *\n"
                 "Disallow: /secret\n"
                 "\n"
                 "# 苏桁说：真正的入口，藏在不被注意的地方。\n"),
                "text/plain; charset=utf-8",
            )

        if path == "/static/tick.png":
            png = STATIC_DIR / "tick.png"
            if png.exists():
                return self._send(png.read_bytes(), "image/png")
            return self._send(b"not found", "text/plain", 404)

        if path == "/join":
            return self._handle_join(qs)

        if path == "/hidden":
            return self._handle_hidden(qs)

        if path in PAGES:
            return self._send(PAGES[path].encode())

        if path == "/check":
            return self._handle_check(qs)

        if path == "/final":
            return self._handle_final(qs)

        if path == "/admin":
            return self._handle_admin(qs)

        if path == "/api/progress":
            return self._handle_api_progress(qs)

        if path == "/api/bind":
            return self._handle_api_bind(qs)

        if path == "/api/stats":
            return self._handle_api_stats(qs)

        if path == "/api/egg":
            return self._handle_api_egg(qs)

        self._send(b"404 Not Found", "text/plain", 404)

    def _handle_join(self, qs):
        code = qs.get("code", [""])[0].strip().lower()
        with LOCK:
            if code:
                if code not in STATE["players"]:
                    return self._send(page("绑定码无效", "<div class='box'><p class='err'>这个绑定码不存在。</p><p><a href='/join'>重新领取</a></p></div>").encode())
                count, _ = player_progress(STATE["players"][code])
                extra = f"<p>已绑定 QQ：{STATE['players'][code]['qq'] or '未绑定'} ｜ 已通关 {count}/8 关</p>"
                fresh = False
            else:
                code = new_player()
                extra = ""
                fresh = True
        body = f"""<div class="box">
<p class="frag">你的绑定码：{code}</p>
<p>把它记住，然后按下面 3 步走：</p>
<ol>
<li>回到群里，@汐月 发送 <code>/bind {code}</code>（绑定你的 QQ 身份）；</li>
<li><b>私聊</b>汐月，发送 <code>/tick</code> 查看玩法说明；</li>
<li>卡关时私聊汐月 <code>/hint N</code> 要提示（每关提示需要通关前一关）。</li>
</ol>
{extra}
<p style="color:#6b7683">绑定码丢失？再访问 /join 输入绑定码即可恢复。</p>
</div>
<a href="/tick" style="font-size:13px">← 返回第 1 关</a>"""
        return self._send(
            page("玩家中心", body).encode(),
            extra_headers={f"Set-Cookie": f"{COOKIE_NAME}={code}; Path=/; Max-Age=2592000"},
        )

    def _handle_check(self, qs):
        try:
            stage = int(qs.get("stage", ["0"])[0])
            ans = qs.get("ans", [""])[0].strip().lower()
        except ValueError:
            return self._send("参数错误", "text/plain")
        player = self._player_from(qs) or self._cookie_player()
        if stage not in STAGE_ANSWERS:
            return self._send("没有这一关。", "text/plain")
        if not player or player not in STATE["players"]:
            return self._send(
                "<span class='err'>请先到 <a href='/join'>/join</a> 领取绑定码</span>，再回来确认答案。",
                "text/html; charset=utf-8",
            )
        if ans != STAGE_ANSWERS[stage]:
            pre = f"（需先完成第 {stage-1} 关）" if stage > 1 else "（无需前置关卡）"
            return self._send(
                f"<span class='err'>❌ 不对哦。</span> 卡住了？提示走私聊：汐月那边发送 <code>/hint {stage}</code>{pre}。",
                "text/html; charset=utf-8",
            )
        with LOCK:
            p = STATE["players"][player]
            p["stages"][str(stage)] = True
            p["last"] = int(time.time())
            count, _ = player_progress(p)
            save_state()
        if stage == 8:
            nxt = "恭喜，8 个碎片齐了！<a href='/final'>去 /final 拼接访问码</a>"
        else:
            nxt = f"<a href='{NEXT_PAGE[stage]}'>前往下一关 →</a>"
        return self._send(
            f"<span class='ok'>✅ 对钩！碎片 {stage} 已确认。</span>（进度 {count}/8）{nxt}",
            "text/html; charset=utf-8",
        )

    def _handle_final(self, qs):
        key = qs.get("key", [""])[0].strip().lower()
        player = self._player_from(qs) or self._cookie_player()
        if key == FINAL_KEY:
            with LOCK:
                note = ""
                if player and player in STATE["players"]:
                    p = STATE["players"][player]
                    p["final"] = True
                    p["last"] = int(time.time())
                    note = f"<p style='color:#6b7683'>玩家 {player}{'（' + str(p['qq']) + '）' if p['qq'] else ''} 已通关。</p>"
                    save_state()
            body = f"""<div class="box"><h2 style="margin-top:0">✅ 对钩！</h2>
<p>访问码验证通过。苏桁留给你的话：</p>
<pre>{FLAG}</pre>
<p style="color:#6b7683">「谢谢你来接我回家。」 —— 苏桁</p>{note}</div>
<div class="box"><p style="font-size:13px;color:#6b7683">
彩蛋：苏桁说过，这串十六进制不是随机数——它是他一句<b>四个字真心话</b>的摘要。
猜出那句话，去 <code>/hidden</code> 认领，你会看到隐藏结局。</p></div>"""
            return self._send(page("终局", body).encode())
        if not player or player not in STATE["players"]:
            return self._send(
                page("终局", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码，否则拿不到 flag 记录。</p></div>").encode()
            )
        body = f"""<div class="box"><p class="err">❌ 访问码错误。</p>
<p>提示走私聊：汐月那边发送 <code>/hint 8</code>（需先完成前 7 关）。</p></div>
<div class="box"><p class="frag">你正在寻找碎片 8。</p>
<p>每一页的右下角都有一个小签名，把它的内容填进来。</p></div>"""
        return self._send(page("碎片 8 · 签名", body, check_stage=8).encode())

    def _handle_hidden(self, qs):
        phrase = qs.get("phrase", [""])[0].strip()
        player = self._player_from(qs) or self._cookie_player()
        if not player or player not in STATE["players"]:
            return self._send(
                page("隐藏结局", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码。</p></div>").encode()
            )
        if hashlib.md5(phrase.encode("utf-8")).hexdigest() != FLAG_INNER:
            return self._send(
                page("隐藏结局", "<div class='box'><p class='err'>❌ 不是这句话。</p><p>四个字，再想想。</p></div>").encode()
            )
        with LOCK:
            p = STATE["players"][player]
            p["egg"] = True
            p["last"] = int(time.time())
            save_state()
        body = f"""<div class="box"><p class="ok">✅ 你找到了那句真心话。</p>
<p>苏桁写的一封信，收件人是汐月：</p>
<pre>{HIDDEN_LETTER}</pre>
<p style="color:#6b7683">—— 隐藏结局 · 解锁</p></div>
<a href="/tick" style="font-size:13px">← 返回第 1 关</a>"""
        return self._send(page("隐藏结局 · 苏桁的信", body).encode())

    def _handle_admin(self, qs):
        if qs.get("pass", [""])[0] != ADMIN_TOKEN:
            return self._send(page("拒绝访问", "<div class='box'><p class='err'>口令错误。</p></div>").encode(), code=403)
        with LOCK:
            rows = sorted(STATE["players"].items(), key=lambda kv: kv[1]["last"], reverse=True)
        lines = []
        for code, p in rows:
            count, mx = player_progress(p)
            cells = "".join(
                f"<td class='{"done" if p["stages"].get(str(i)) else "todo"}'>{"✓" if p["stages"].get(str(i)) else "·"}</td>"
                for i in range(1, 9)
            )
            lines.append(
                f"<tr><td>{code}</td><td>{p['qq'] or '—'}</td><td>{p['name'] or '—'}</td>"
                f"<td>{count}/8</td>{cells}<td class='{"done" if p["final"] else "todo"}'>{"✓" if p["final"] else "·"}</td>"
                f"<td class='{"done" if p.get("egg") else "todo"}'>{"✓" if p.get("egg") else "·"}</td>"
                f"<td>{time.strftime('%m-%d %H:%M', time.localtime(p['last']))}</td></tr>"
            )
        head = ("<tr><th>绑定码</th><th>QQ</th><th>昵称</th><th>进度</th>"
                + "".join(f"<th>{i}</th>" for i in range(1, 9))
                + "<th>终局</th><th>彩蛋</th><th>最后活跃</th></tr>")
        body = f"""<div class="box">
<p>玩家总数：{len(rows)} ｜ 通关终局：{sum(1 for _, p in rows if p['final'])} ｜ 找到彩蛋：{sum(1 for _, p in rows if p.get('egg'))}</p>
<table>{head}{''.join(lines)}</table>
<p style="font-size:12px;color:#6b7683">API: /api/stats?secret=…</p>
</div>"""
        return self._send(page("进度面板 · GM", body).encode())

    def _handle_api_progress(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._json({"ok": False, "err": "player not found"})
            count, mx = player_progress(p)
            return self._json({
                "ok": True,
                "player": player,
                "qq": p["qq"],
                "count": count,
                "max": mx,
                "stages": [int(s) for s in p["stages"] if p["stages"][s]],
                "final": p["final"],
                "egg": p.get("egg", False),
            })

    def _handle_api_bind(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        qq = qs.get("qq", [""])[0].strip()
        name = qs.get("name", [""])[0].strip()[:30]
        if not player or not qq:
            return self._json({"ok": False, "err": "missing player/qq"})
        with LOCK:
            if player not in STATE["players"]:
                return self._json({"ok": False, "err": "player not found"})
            p = STATE["players"][player]
            p["qq"] = qq
            if name:
                p["name"] = name
            p["last"] = int(time.time())
            save_state()
            return self._json({"ok": True})

    def _handle_api_stats(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        with LOCK:
            return self._json(STATE)

    def _handle_api_egg(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._json({"ok": False, "err": "player not found"})
            p["egg"] = True
            p["last"] = int(time.time())
            save_state()
            return self._json({"ok": True})


def main():
    import sys
    global PORT
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    load_state()
    build_static_pages()
    if not (STATIC_DIR / "tick.png").exists():
        print(f"[警告] 缺少 {STATIC_DIR / 'tick.png'}，请先运行 make_assets.py")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[对钩计划] http://0.0.0.0:{PORT}/tick  后台面板 /admin?pass=<ADMIN_TOKEN>")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ζ 计划 (Project ZETA) —— ARG 网页服务器 + 玩家进度系统

零依赖，仅用 Python 标准库。直接运行:
    python3 tick.py [port]        # 默认端口 8080

关卡碎片（按顺序拼接即为最终访问码，访问码 ≠ flag）:
    1: 66b2   2: cac2   3: 5690   4: 7ada
    5: 4f1e   6: 9999   7: 0888   8: 83d2

一次性提示码系统:
    每关页面按玩家动态签发 3 层提示码 + 记忆库/凭证/彩蛋码（每人每码唯一）。
    码自生成起 CODE_TTL 秒有效、用一次即焚；私聊汐月 /submit 0x<码> 统一兑换。
    后台 /admin 输入泄露的码可定位泄密者。

路由:
    /zeta /secret /stage3~7   关卡页（含玩家专属提示码）
    /join                 领取/恢复绑定码（写 cookie tick_player）
    /check                校验答案并记录进度
    /final                终局（成功页签发彩蛋码）
    /hidden               隐藏关卡：md5(短语) == flag 内串时解锁隐藏结局
    /admin?pass=<口令>    管理员进度面板 + 泄密码解码
    /api/redeem           提示码兑付（插件调用，secret 鉴权）
    /api/progress /api/bind /api/finished /api/decode /api/stats
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

CODE_TTL = 600  # 一次性提示码自生成起 10 分钟有效

FINAL_KEY = "66b2cac256907ada4f1e9999088883d2"
FLAG_INNER = "81fbaa81762885ac3481fd4b416485e6"  # md5("我喜欢你")
FLAG = f"flag{{{FLAG_INNER}}}"

HIDDEN_LETTER = """汐月：

如果你能看到这封信，说明有人替我找到了那句话。

我研究黎曼 ζ 函数研究了很久。所有人都说它神秘、深不可测——但我最喜欢的是 ζ(-1) = -1/12：连 1+2+3+… 这样发散的级数，都能有一个确定的答案。数学家管这叫解析延拓。我只想说，有些话，我延拓了很多年，才敢写下来。

我喜欢你。

谢谢你替我守护这些秘密到现在。剩下的路，交给你了。

—— 苏桁"""

STAGE_ANSWERS = {
    1: "66b2",
    2: "cac2",
    3: "5690",
    4: "7ada",
    5: "4f1e",
    6: "9999",
    7: "0888",
    8: "83d2",
}

# 每关 3 层提示：第一层(轻)/第二层(方法)/第三层(答案)
HINT_TEXTS = {
    1: [
        "苏桁说真正的入口藏在不被注意的地方——试试右键查看网页源代码。",
        "源代码的 HTML 注释里有一串十六进制：36 36 62 32，把它们转成 ASCII 字符。",
        "0x36='6'，0x36='6'，0x62='b'，0x32='2'，连起来是 66b2。",
    ],
    2: [
        "服务器礼仪：先去访问 /robots.txt 看看。",
        "/robots.txt 会指向 /secret，那里有一串 base64：Y2FjMg==",
        "把 Y2FjMg== 做 base64 解码，得到 cac2。",
    ],
    3: [
        "去 WolframAlpha 搜索 zeta(3)，看它的十进制展开。",
        "ζ(3) = 1.20205690315959…，取小数点后第 5~8 位。",
        "第 5~8 位是 5690。",
    ],
    4: [
        "那张图比看上去多了一点东西——用文本编辑器打开它。",
        "PNG 文件的信息块 tEXt 里藏着内容，用文本/十六进制编辑器搜 7ada 试试。",
        "搜索 7ada：答案就是 7ada。",
    ],
    5: [
        "这一关要问汐月自己。私聊她，用下方「专属提示码」区的记忆库开启码。",
        "汐月的记忆库是她的秘密：私聊发送 /submit 0x<记忆库开启码>（需完成前 4 关）。",
        "/submit 0x<记忆库开启码> 会告诉你四个字符：4f1e。",
    ],
    6: [
        "和 π 有关。去网上找一个能搜索 π 数字的工具。",
        "费曼点：π 小数里第一次连续出现 6 个 9 的地方。用 π 数字检索网站查。",
        "那 6 个 9 从第 762 位开始，取前 4 个：9999。",
    ],
    7: [
        "这一关要问汐月。私聊她，用下方「专属提示码」区的凭证码。",
        "口令在汐月那里：私聊发送 /submit 0x<凭证码>（需完成前 6 关）。",
        "/submit 0x<凭证码> 会告诉你碎片七：0888。",
    ],
    8: [
        "留意每一个页面的右下角。",
        "每页右下角有个不起眼的小签名 ◆ 83d2。",
        "签名是 83d2。",
    ],
}

HINT_LABELS = ["第一层", "第二层", "第三层"]

SECRET_TEXTS = {
    "mem": "记忆库……（信号很不稳定）我只记得四个字符：4、F、1、E。对，4f1e。别问我为什么记得这个，苏桁说那是打开他记忆库的钥匙。",
    "cred": "……凭证核对中。校验通过。碎片七：0888。拿去吧，别说是我给的。",
    "egg": "（汐月很久没有说话。）……苏桁写给我的信，他说从没说出口的话，都在这里了。\n\n" + HIDDEN_LETTER,
}

SECRET_GATES = {"mem": 4, "cred": 6, "egg": None}  # 需要的通关数；egg 只在终局成功页签发

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
<title>{title} · ζ 计划</title><style>{PAGE_CSS}</style></head>
<body>
<h1>ζ 计划 <span style="font-size:13px;color:#6b7683">/ Project ZETA</span></h1>
<div class="banner" id="banner" style="display:none">还没领取绑定码？<a href="/join">先去 /join 领取</a>，不然进度和提示都拿不到。</div>
{body}
{check_html}
<footer>苏桁 · ζ(s) = Σ 1/nˢ
<span class="sign">◆ 83d2</span></footer>
<script>
if(!document.cookie.match(/tick_player=/)){{document.getElementById('banner').style.display='';}}
</script>
</body></html>"""


STAGE_BODIES = {
    1: """
<div class="box">
<p>苏桁，你的大学数学系同学，主攻黎曼 ζ 函数与数论——那是一个连 1+2+3+… 都能等于 -1/12 的世界。三周前，他失踪了。</p>
<p>他留给你唯一的线索，是他一直在维护的这台服务器。他说过："真正的入口，藏在不被注意的地方。"</p>
<p>但无论如何——先看看这个页面的<b>源代码</b>吧。</p>
<p style="color:#6b7683">（如果不知道怎么看：右键点击页面空白处 → "查看网页源代码"）</p>
<p>另外，服务器礼节：先去访问一下 <code>/robots.txt</code>。</p>
<p style="color:#6b7683">新玩家：去 <a href="/join">/join</a> 领取你的绑定码，然后回群里 @汐月 发送 <code>/bind &lt;绑定码&gt;</code> 完成绑定。</p>
</div>
<!-- 36 36 62 32 -->
""",
    2: """
<div class="box">
<p>你通过了 robots.txt 的指引找到了这个目录。苏桁留下了一句话，但显然他不想让人一眼看懂：</p>
<pre>Y2FjMg==</pre>
<p>把它解开，就是碎片 2。</p>
</div>
""",
    3: """
<div class="box">
<p>苏桁的草稿纸上只有一行字：</p>
<pre>ζ(3) = 1.20205690315959…</pre>
<p>旁边用红笔写着：「阿培里常数。无理数的证明，人类等了 200 年。别手算，去找一个会算它的网站。」</p>
<p>求：ζ(3) 小数点后<b>第 5~8 位</b>，那就是碎片 3。</p>
<p style="color:#6b7683">（WolframAlpha、sympy、各种在线计算器都行）</p>
</div>
""",
    4: """
<div class="box">
<p>苏桁的收藏里有一张他手绘的 ζ 函数草图：<a href="/static/zeta.png">ζ 草图.png</a>。</p>
<p>它比看上去的要多一点东西。用<b>文本编辑器</b>（记事本也行）打开它，或者直接搜一搜。</p>
<p style="color:#6b7683">提示：图片信息里通常有些"看不见"的文字块。</p>
</div>
""",
    5: """
<div class="box">
<p>苏桁的 AI「汐月」还活着。苏桁把最重要的一串字符锁在了汐月的记忆库里。</p>
<p>要打开它，你需要一个<b>记忆库开启码</b>——它在下方「专属提示码」区域。</p>
<p>拿到后<b>私聊</b>汐月：<code>/submit 0x&lt;记忆库开启码&gt;</code></p>
<p style="color:#6b7683">只有完成了前 4 关的人，汐月才会说。（没绑定的话先去 <a href="/join">/join</a>）</p>
</div>
""",
    6: """
<div class="box">
<p>苏桁在一本书的扉页抄了一句话，关于 π：</p>
<pre>「在 π 的小数展开里，第一次连续出现 6 个 9 的地方，
  被叫作费曼点——费曼说，他想背到那里，然后向朋友炫耀：
  '九九九九九九，如此下去，直到最后。'」</pre>
<p>求：那 6 个 9。取前 4 个，就是碎片 6。</p>
<p style="color:#6b7683">（网上有 π 数字检索工具，输入 999999 就能找到它的位置）</p>
</div>
""",
    7: """
<div class="box">
<p>汐月最近变得敏感多疑。她只认一句"口令"——苏桁当年和她约定的暗语。</p>
<p>要拿到口令，你需要一个<b>凭证码</b>——它在下方「专属提示码」区域。</p>
<p>拿到后<b>私聊</b>汐月：<code>/submit 0x&lt;凭证码&gt;</code></p>
<p style="color:#6b7683">只有完成了前 6 关的人，汐月才会理会。（没绑定的话先去 <a href="/join">/join</a>）</p>
</div>
""",
}


def code_label(entry):
    """把一次性码记录翻译成可读标签。"""
    kind = entry["kind"]
    if kind == "h":
        return f"第{entry['stage']}关·{HINT_LABELS[entry['level']]}"
    return {"mem": "记忆库", "cred": "凭证", "egg": "彩蛋"}.get(kind, kind)


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
                "stage_ts": {},
                "final": False,
                "final_ts": None,
                "egg": False,
                "egg_ts": None,
                "hintcodes": {},
                "last": int(time.time()),
            }
            save_state()
            return code


def player_progress(p):
    done = sorted(int(s) for s, v in p["stages"].items() if v)
    return len(done), (max(done) if done else 0)


def issue_code(p: dict, kind: str, stage: int, level: int | None) -> str:
    """签发/复用一枚一次性码（每人每码唯一，自生成起 CODE_TTL 秒有效）。"""
    now = int(time.time())
    codes = p.setdefault("hintcodes", {})
    for code, e in codes.items():
        if (e["kind"], e.get("stage"), e.get("level")) == (kind, stage, level) \
                and not e.get("used") and now - e["gen"] <= CODE_TTL:
            return code
    while True:
        code = secrets.token_hex(3)[:5]
        if code not in codes:
            break
    codes[code] = {"kind": kind, "stage": stage, "level": level, "gen": now, "used": False}
    return code


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

    def _hint_box(self, stage: int, player: str):
        """本关专属提示码区域。"""
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return """<div class="box"><p class="frag">专属提示码</p>
<p>领取绑定码后，这里会显示你的专属提示码（每人每码唯一，用完即焚）。</p>
<p><a href="/join">去 /join 领取绑定码</a></p></div>"""
            codes = [issue_code(p, "h", stage, lv) for lv in range(3)]
            save_state()
            lines = "".join(
                f"<p>{HINT_LABELS[i]}：<code>/submit 0x{c}</code></p>" for i, c in enumerate(codes)
            )
            extra = ""
            if stage == 5:
                extra = f"<p style='color:#ffd479'>记忆库开启码：<code>/submit 0x{issue_code(p, 'mem', 5, None)}</code></p>"
                save_state()
            if stage == 7:
                extra = f"<p style='color:#ffd479'>凭证码：<code>/submit 0x{issue_code(p, 'cred', 7, None)}</code></p>"
                save_state()
            return f"""<div class="box"><p class="frag">专属提示码</p>
<p>私聊汐月发送对应指令兑换，每人每码只能用一次，自生成起 10 分钟有效（过期回本页刷新）。</p>
{lines}{extra}
<p style="font-size:12px;color:#6b7683">码是你一个人的，截图会被追责。</p></div>"""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._send(b'<meta http-equiv="refresh" content="0;url=/zeta">')

        if path == "/robots.txt":
            return self._send(
                ("User-agent: *\n"
                 "Disallow: /secret\n"
                 "\n"
                 "# 苏桁说：真正的入口，藏在不被注意的地方。\n"),
                "text/plain; charset=utf-8",
            )

        if path == "/static/zeta.png":
            png = STATIC_DIR / "zeta.png"
            if png.exists():
                return self._send(png.read_bytes(), "image/png")
            return self._send(b"not found", "text/plain", 404)

        if path == "/join":
            return self._handle_join(qs)

        if path == "/zeta":
            return self._send(self._stage_page(1).encode())
        if path == "/secret":
            return self._send(self._stage_page(2).encode())
        if path == "/stage3":
            return self._send(self._stage_page(3).encode())
        if path == "/stage4":
            return self._send(self._stage_page(4).encode())
        if path == "/stage5":
            return self._send(self._stage_page(5).encode())
        if path == "/stage6":
            return self._send(self._stage_page(6).encode())
        if path == "/stage7":
            return self._send(self._stage_page(7).encode())

        if path == "/check":
            return self._handle_check(qs)

        if path == "/final":
            return self._handle_final(qs)

        if path == "/hidden":
            return self._handle_hidden(qs)

        if path == "/admin":
            return self._handle_admin(qs)

        if path == "/api/redeem":
            return self._handle_api_redeem(qs)

        if path == "/api/progress":
            return self._handle_api_progress(qs)

        if path == "/api/bind":
            return self._handle_api_bind(qs)

        if path == "/api/decode":
            return self._handle_api_decode(qs)

        if path == "/api/events":
            return self._handle_api_events(qs)

        if path == "/api/stats":
            return self._handle_api_stats(qs)

        self._send(b"404 Not Found", "text/plain", 404)

    def _stage_page(self, stage: int):
        player = self._cookie_player()
        body = STAGE_BODIES[stage] + self._hint_box(stage, player)
        return page(f"碎片 {stage}", body, check_stage=stage)

    def _handle_join(self, qs):
        code = qs.get("code", [""])[0].strip().lower()
        with LOCK:
            if code:
                if code not in STATE["players"]:
                    return self._send(page("绑定码无效", "<div class='box'><p class='err'>这个绑定码不存在。</p><p><a href='/join'>重新领取</a></p></div>").encode())
                count, _ = player_progress(STATE["players"][code])
                extra = f"<p>已绑定 QQ：{STATE['players'][code]['qq'] or '未绑定'} ｜ 已通关 {count}/8 关</p>"
            else:
                code = new_player()
                extra = ""
        body = f"""<div class="box">
<p class="frag">你的绑定码：{code}</p>
<p>把它记住，然后按下面 3 步走：</p>
<ol>
<li>回到群里，@汐月 发送 <code>/bind {code}</code>（绑定你的 QQ 身份）；</li>
<li><b>私聊</b>汐月，发送 <code>/zeta</code> 查看玩法说明；</li>
<li>每关页面的「专属提示码」区域有你的提示码，私聊汐月 <code>/submit 0x&lt;码&gt;</code> 兑换
（每人每码只能用一次，10 分钟有效）。</li>
</ol>
{extra}
<p style="color:#6b7683">绑定码丢失？再访问 /join 输入绑定码即可恢复。</p>
</div>
<a href="/zeta" style="font-size:13px">← 返回第 1 关</a>"""
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
                f"<span class='err'>❌ 不对哦。</span> 卡住了？用本页下方的<b>专属提示码</b>，私聊汐月兑换（一次性）。{pre}",
                "text/html; charset=utf-8",
            )
        with LOCK:
            p = STATE["players"][player]
            now = int(time.time())
            p["stages"][str(stage)] = True
            p["stage_ts"][str(stage)] = now
            p["last"] = now
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
        player = self._cookie_player()
        if key == FINAL_KEY:
            with LOCK:
                note = ""
                egg_box = ""
                if player and player in STATE["players"]:
                    p = STATE["players"][player]
                    p["final"] = True
                    p["final_ts"] = int(time.time())
                    p["last"] = int(time.time())
                    ec = issue_code(p, "egg", 0, None)
                    save_state()
                    note = f"<p style='color:#6b7683'>玩家 {player}{'（' + str(p['qq']) + '）' if p['qq'] else ''} 已通关。</p>"
                    egg_box = f"""<div class="box"><p class="frag">隐藏结局开启码</p>
<p>私聊汐月发送 <code>/submit 0x{ec}</code>，读苏桁写给汐月的信。</p>
<p style="font-size:12px;color:#6b7683">另一个线索：这串十六进制 <code>{FLAG_INNER}</code> 是苏桁一句四个字真心话的摘要——猜出它，去 <code>/hidden</code> 认领。</p></div>"""
            body = f"""<div class="box"><h2 style="margin-top:0">✅ 对钩！</h2>
<p>访问码验证通过。苏桁留给你的话：</p>
<pre>{FLAG}</pre>
<p style="color:#6b7683">「谢谢你来接我回家。」 —— 苏桁</p>{note}</div>{egg_box}"""
            return self._send(page("终局", body).encode())
        if not player or player not in STATE["players"]:
            return self._send(
                page("终局", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码，否则拿不到 flag 记录。</p></div>").encode()
            )
        body = f"""<div class="box"><p class="err">❌ 访问码错误。</p>
<p>卡住了？第 8 关的专属提示码在下方（一次性）。</p></div>
<div class="box"><p class="frag">你正在寻找碎片 8。</p>
<p>每一页的右下角都有一个小签名，把它的内容填进来。</p></div>"""
        return self._send(page("碎片 8 · 签名", body + self._hint_box(8, player), check_stage=8).encode())

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
            p["egg_ts"] = int(time.time())
            p["last"] = int(time.time())
            save_state()
        body = f"""<div class="box"><p class="ok">✅ 你找到了那句真心话。</p>
<p>苏桁写的一封信，收件人是汐月：</p>
<pre>{HIDDEN_LETTER}</pre>
<p style="color:#6b7683">—— 隐藏结局 · 解锁</p></div>
<a href="/zeta" style="font-size:13px">← 返回第 1 关</a>"""
        return self._send(page("隐藏结局 · 苏桁的信", body).encode())

    def _handle_admin(self, qs):
        if qs.get("pass", [""])[0] != ADMIN_TOKEN:
            return self._send(page("拒绝访问", "<div class='box'><p class='err'>口令错误。</p></div>").encode(), code=403)
        decode_html = ""
        if qs.get("code", [""])[0]:
            import urllib.request
            code = qs.get("code", [""])[0].strip().lower()
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/decode?code={urllib.parse.quote(code)}&secret={ADMIN_TOKEN}")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
            except Exception:
                data = {"hits": []}
            if data.get("hits"):
                rows = "".join(
                    f"<tr><td>{h['player']}</td><td>{h['qq'] or '—'}</td><td>{h['label']}</td>"
                    f"<td>{h['time']}</td><td class='{"done" if h.get("valid") else "todo"}'>{"有效" if h.get("valid") else "已过期"}</td>"
                    f"<td class='{"done" if h.get("used") else "todo"}'>{"已用" if h.get("used") else "未用"}</td></tr>"
                    for h in data["hits"]
                )
                decode_html = f"""<div class="box"><p class="ok">一次性码 {code} 匹配到：</p>
<table><tr><th>绑定码</th><th>QQ</th><th>内容</th><th>签发时间</th><th>状态</th><th>使用</th></tr>{rows}</table></div>"""
            else:
                decode_html = f"<div class='box'><p class='err'>一次性码 {code} 无匹配。</p></div>"
        with LOCK:
            rows = sorted(STATE["players"].items(), key=lambda kv: kv[1]["last"], reverse=True)
        lines = []
        for code, p in rows:
            count, mx = player_progress(p)
            cells = "".join(
                f"<td class='{"done" if p["stages"].get(str(i)) else "todo"}'>{"✓" if p["stages"].get(str(i)) else "·"}</td>"
                for i in range(1, 9)
            )
            used = " ".join(code_label(e) for e in (p.get("hintcodes") or {}).values() if e.get("used")) or "—"
            lines.append(
                f"<tr><td>{code}</td><td>{p['qq'] or '—'}</td><td>{p['name'] or '—'}</td>"
                f"<td>{count}/8</td>{cells}<td class='{"done" if p["final"] else "todo"}'>{"✓" if p["final"] else "·"}</td>"
                f"<td class='{"done" if p.get("egg") else "todo"}'>{"✓" if p.get("egg") else "·"}</td>"
                f"<td style='font-size:11px'>{used}</td>"
                f"<td>{time.strftime('%m-%d %H:%M', time.localtime(p['last']))}</td></tr>"
            )
        head = ("<tr><th>绑定码</th><th>QQ</th><th>昵称</th><th>进度</th>"
                + "".join(f"<th>{i}</th>" for i in range(1, 9))
                + "<th>终局</th><th>彩蛋</th><th>已用码</th><th>最后活跃</th></tr>")
        body = f"""<div class="box">
<p>玩家总数：{len(rows)} ｜ 通关终局：{sum(1 for _, p in rows if p['final'])} ｜ 找到彩蛋：{sum(1 for _, p in rows if p.get('egg'))}</p>
<p style="font-size:12px;color:#6b7683">泄密追溯：输入截图里的 5 位一次性码，定位是哪个玩家、哪条内容、什么时间。</p>
<form method="get"><input type="hidden" name="pass" value="{ADMIN_TOKEN}">
<input type="text" name="code" placeholder="5 位一次性码" style="width:180px">
<button>解码</button></form></div>
{decode_html}
<div class="box">
<table>{head}{''.join(lines)}</table>
<p style="font-size:12px;color:#6b7683">API: /api/stats?secret=… ｜ /api/decode?code=…&secret=…</p>
</div>"""
        return self._send(page("进度面板 · GM", body).encode())

    # ---------- 插件 API ----------

    def _handle_api_redeem(self, qs):
        """一次性码兑付：/hint /记忆库 /凭证 /彩蛋 统一走这里。"""
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        code = qs.get("code", [""])[0].strip().lower()
        if code.startswith("0x"):
            code = code[2:]
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._json({"ok": False, "err": "player not found"})
            entry = (p.get("hintcodes") or {}).get(code)
            if not entry:
                return self._json({"ok": True, "status": "bad"})
            if entry.get("used"):
                return self._json({"ok": True, "status": "used"})
            if int(time.time()) - entry["gen"] > CODE_TTL:
                return self._json({"ok": True, "status": "expired"})
            now = int(time.time())
            kind, stage, level = entry["kind"], entry.get("stage"), entry.get("level")
            if kind == "h":
                _, mx = player_progress(p)
                if stage - 1 > mx:
                    return self._json({"ok": True, "status": "gated", "need": stage - 1})
                text = HINT_TEXTS[stage][level]
                label = f"第{stage}关·{HINT_LABELS[level]}"
            else:
                need = SECRET_GATES.get(kind)
                if need is not None:
                    _, mx = player_progress(p)
                    if mx < need:
                        return self._json({"ok": True, "status": "gated", "need": need})
                text = SECRET_TEXTS[kind]
                label = {"mem": "记忆库", "cred": "凭证", "egg": "彩蛋"}.get(kind, kind)
                if kind == "egg":
                    p["egg"] = True
                    p["egg_ts"] = now
            entry["used"] = True
            p["last"] = now
            save_state()
            return self._json({"ok": True, "status": "ok", "kind": kind, "stage": stage,
                               "label": label, "text": text})

    def _handle_api_progress(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._json({"ok": False, "err": "player not found"})
            count, mx = player_progress(p)
            used = [code_label(e) for e in (p.get("hintcodes") or {}).values() if e.get("used")]
            return self._json({
                "ok": True,
                "player": player,
                "qq": p["qq"],
                "count": count,
                "max": mx,
                "stages": [int(s) for s in p["stages"] if p["stages"][s]],
                "final": p["final"],
                "egg": p.get("egg", False),
                "used": used,
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

    def _handle_api_decode(self, qs):
        """GM 泄密追溯：输入一次性码，反查玩家/内容/时间。"""
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        code = qs.get("code", [""])[0].strip().lower()
        if code.startswith("0x"):
            code = code[2:]
        if len(code) != 5:
            return self._json({"ok": False, "err": "bad code"})
        now = int(time.time())
        hits = []
        with LOCK:
            for player, p in STATE["players"].items():
                for c, e in (p.get("hintcodes") or {}).items():
                    if c != code:
                        continue
                    hits.append({
                        "player": player,
                        "qq": p.get("qq"),
                        "label": code_label(e),
                        "time": time.strftime("%m-%d %H:%M", time.localtime(e["gen"])),
                        "valid": (now - e["gen"]) <= CODE_TTL,
                        "used": bool(e.get("used")),
                    })
        return self._json({"ok": True, "hits": hits})

    def _handle_api_events(self, qs):
        """供插件轮询：返回 after 之后的全部事件（逐关通关/终局/彩蛋），按时间排序。"""
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        try:
            after = int(qs.get("after", ["0"])[0])
        except ValueError:
            after = 0
        events = []
        with LOCK:
            for player, p in STATE["players"].items():
                qq, name = p.get("qq"), p.get("name")
                for st, ts in (p.get("stage_ts") or {}).items():
                    if ts > after:
                        events.append({"type": "stage", "player": player, "qq": qq, "name": name,
                                       "stage": int(st), "ts": ts})
                if p.get("final_ts") and p["final_ts"] > after:
                    events.append({"type": "final", "player": player, "qq": qq, "name": name,
                                   "created": p.get("created", 0), "final_ts": p["final_ts"],
                                   "egg": p.get("egg", False), "ts": p["final_ts"]})
                if p.get("egg_ts") and p["egg_ts"] > after:
                    events.append({"type": "egg", "player": player, "qq": qq, "name": name,
                                   "ts": p["egg_ts"]})
        events.sort(key=lambda e: e["ts"])
        return self._json({"ok": True, "events": events})

    def _handle_api_stats(self, qs):
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        with LOCK:
            return self._json(STATE)


def main():
    import sys
    global PORT
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    load_state()
    if not (STATIC_DIR / "zeta.png").exists():
        print(f"[警告] 缺少 {STATIC_DIR / 'zeta.png'}，请先运行 make_assets.py")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[ζ 计划] http://0.0.0.0:{PORT}/zeta  后台面板 /admin?pass=<ADMIN_TOKEN>")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

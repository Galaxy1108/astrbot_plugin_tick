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
    每关页面按玩家签发 3 层提示码 + 记忆库/彩蛋码（每人每码唯一）。
    码无时间限制、用完即焚、只认本人；发到群聊会被立即吊销（需重新生成/申请）。私聊汐月 /submit 0x<码> 统一兑换。
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

# 提示码规则：无时间限制、手动点击生成、用完即焚；发到群聊会被立即吊销（需重新生成/申请）
# 三层提示解锁策略：第1层等 5 分钟，第2层等 20 分钟（自首次查看本关起算），第3层需管理员审批
HINT_UNLOCK = {0: 300, 1: 1200, 2: None}

FINAL_KEY = None  # 每人一套碎片，最终访问码按玩家动态计算
FLAG_INNER = "81fbaa81762885ac3481fd4b416485e6"  # md5("我喜欢你")
FLAG = f"flag{{{FLAG_INNER}}}"
FAKE_FLAG = "flag{3e79be0507b8e8d29948be61e0432637}"  # md5("我喜欢你。")——假结局诱饵

# 每人碎片生成用常数
ZETA3_DIGITS = "2020569031595942853997381615114499907649862923404988"  # ζ(3) 小数位（50 位）
PI_DIGITS = ("1415926535897932384626433832795028841971693993751058209749445923078164062862"
             "0899862803482534211706798214808651328230664709384460955058223172535940812848111")  # π 小数位（160 位）
PNG_CODES = ["f7af", "ce8d", "2127", "ac16", "cb86", "e7f5", "8b26", "3e7c"]  # ζ 草图 tEXt t1~t8
MORSE_BASE = "0888"  # 录音笔摩斯；碎片7 = 每位加个人偏移(模10)

HIDDEN_LETTER = """汐月：

如果你能看到这封信，说明有人替我找到了那句话。

我研究黎曼 ζ 函数研究了很久。所有人都说它神秘、深不可测——但我最喜欢的是 ζ(-1) = -1/12：连 1+2+3+… 这样发散的级数，都能有一个确定的答案。数学家管这叫解析延拓。我只想说，有些话，我延拓了很多年，才敢写下来。

我喜欢你。

谢谢你替我守护这些秘密到现在。剩下的路，交给你了。

—— 苏桁"""

# 碎片不再有全局答案：每人一套（p["frags"]），/check 按个人校验。

# 每关 3 层提示（按玩家渲染，答案级提示含个人碎片）
HINT_LABELS = ["第一层", "第二层", "第三层"]


def hexbytes(frag: str) -> str:
    """把 4 位 hex 转成 ASCII 字节序列，如 '66b2' -> '36 36 62 32'。"""
    return " ".join(f"{ord(c):02x}" for c in frag)


def frag_reading(frag: str) -> str:
    """把 4 位 hex 转成口语读法，如 '83d2' -> '八三D二'。"""
    cn = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
    return "".join(cn.get(c, c.upper()) for c in frag)


def render_hint(p: dict, stage: int, level: int) -> str:
    """渲染第 stage 关第 level 层提示（含个人碎片参数）。"""
    import base64 as _b64
    f = p["frags"]
    m = p["frag_meta"]
    if stage == 1:
        return [
            "苏桁说真正的入口藏在不被注意的地方——试试右键查看网页源代码。",
            f"源代码的 HTML 注释里有一串十六进制：{hexbytes(f[0])}，把它们转成 ASCII 字符。",
            f"把 {hexbytes(f[0])} 转成 ASCII，连起来是 {f[0]}。",
        ][level]
    if stage == 2:
        b64 = _b64.b64encode(f[1].encode()).decode()
        return [
            "服务器礼仪：先去访问 /robots.txt 看看。",
            f"/robots.txt 会指向 /secret，那里有一串 base64：{b64}",
            f"把 {b64} 做 base64 解码，得到 {f[1]}。",
        ][level]
    if stage == 3:
        return [
            "去 WolframAlpha 搜索 zeta(3)，看它的十进制展开。",
            f"ζ(3) = 1.20205690315959…，取小数点后第 {m['p3']}~{m['p3'] + 3} 位。",
            f"第 {m['p3']}~{m['p3'] + 3} 位是 {f[2]}。",
        ][level]
    if stage == 4:
        return [
            "那张图比看上去多了一点东西——用文本编辑器打开它。",
            f"PNG 的 tEXt 信息块里有 8 个编号块（t1~t8），你的碎片在第 {m['p4']} 块。",
            f"第 {m['p4']} 块（t{m['p4']}）的内容就是 {f[3]}。",
        ][level]
    if stage == 5:
        return [
            "这一关要问汐月自己。私聊她，用下方「专属提示码」区的记忆库开启码。",
            "汐月的记忆库是她的秘密：私聊发送 /submit 0x<记忆库开启码>（需完成前 4 关）。她只记得前两个字符——另一半在服务器上的 /vault 里。",
            f"/submit 0x<记忆库开启码> 给你前两位；再去 /vault 按便签规则取后两位，拼成 {f[4]}。",
        ][level]
    if stage == 6:
        return [
            "和 π 有关。去网上找一个能搜索 π 数字的工具。",
            f"苏桁说，每个人的 π 都不一样。你的片段从 π 的小数点后第 {m['p6']} 位开始。",
            f"π 小数点后第 {m['p6']}~{m['p6'] + 3} 位是 {f[5]}。",
        ][level]
    if stage == 7:
        return [
            "把录音听/看几遍，数数「嘀」和「哒」——是有人在敲电报。",
            "摩斯电码：短音=点，长音=划。整段是 ----- ---.. ---.. ---..，即 0888。",
            f"摩斯解出 0888 后，每位数字加 {m['o7']}（模 10），得到 {f[6]}。",
        ][level]
    return [
        "网页上没有线索了。最后一个数字只有汐月知道——私聊她，用真心或证据打动她。",
        "直接要她不会给。证明自己：在私聊里准确说出你收集到的几个碎片编号（她会用工具核对），或者认真说一句心里话。",
        "在私聊里报出你记得的三四个碎片编号，再真诚地说一句心里话。她心里藏着的那串数字，会亲口念给你。",
    ][level]

SECRET_GATES = {"mem": 4, "egg": None}  # 需要的通关数；egg 只在终局成功页签发

def secret_text(kind: str, p: dict) -> str:
    """按玩家渲染秘密内容（记忆库只给前两位，另一半在 /vault）。"""
    if kind == "mem":
        f = p["frags"][4]
        return (f"记忆库……（信号很不稳定）我只记得开头的两个字符：{f[:2]}。"
                f"后面两个，苏桁说存在服务器上一个叫 vault 的页面里——那是他的保险库。")
    return "（汐月很久没有说话。）……苏桁写给我的信，他说从没说出口的话，都在这里了。\n\n" + HIDDEN_LETTER

NEXT_PAGE = {1: "/robots.txt", 2: "/stage3", 3: "/stage4", 4: "/stage5", 5: "/stage6", 6: "/stage7", 7: "/final"}
STAGE_PATHS = {1: "/zeta", 2: "/secret", 3: "/stage3", 4: "/stage4", 5: "/stage5", 6: "/stage6", 7: "/stage7", 8: "/final"}

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
    """渲染一个带统一头尾的页面。"""
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
<footer>苏桁 · ζ(s) = Σ 1/nˢ</footer>
<script>
if(!document.cookie.match(/tick_player=/)){{document.getElementById('banner').style.display='';}}
</script>
</body></html>"""


def stage_body(p: dict, stage: int) -> str:
    """按玩家渲染关卡正文（含个人碎片参数）。"""
    import base64 as _b64
    f = p["frags"]
    m = p["frag_meta"]
    if stage == 1:
        return f"""
<div class="box">
<p>苏桁，你的大学数学系同学，主攻黎曼 ζ 函数与数论——那是一个连 1+2+3+… 都能等于 -1/12 的世界。三周前，他失踪了。</p>
<p>他留给你唯一的线索，是他一直在维护的这台服务器。他说过："真正的入口，藏在不被注意的地方。"</p>
<p>但无论如何——先看看这个页面的<b>源代码</b>吧。</p>
<p style="color:#6b7683">（如果不知道怎么看：右键点击页面空白处 → "查看网页源代码"）</p>
<p>另外，服务器礼节：先去访问一下 <code>/robots.txt</code>。</p>
<p style="color:#6b7683">新玩家：去 <a href="/join">/join</a> 领取你的绑定码，然后回群里 @汐月 发送 <code>/bind &lt;绑定码&gt;</code> 完成绑定。</p>
</div>
<!-- {hexbytes(f[0])} -->
"""
    if stage == 2:
        b64 = _b64.b64encode(f[1].encode()).decode()
        return f"""
<div class="box">
<p>你通过了 robots.txt 的指引找到了这个目录。苏桁留下了一句话，但显然他不想让人一眼看懂：</p>
<pre>{b64}</pre>
<p>把它解开，就是碎片 2。</p>
</div>
"""
    if stage == 3:
        return f"""
<div class="box">
<p>苏桁的草稿纸上只有一行字：</p>
<pre>ζ(3) = 1.20205690315959…</pre>
<p>旁边用红笔写着：「阿培里常数。无理数的证明，人类等了 200 年。别手算，去找一个会算它的网站。」</p>
<p>苏桁给每个人都标了一个起始位。你的起始位是小数点后第 <b>{m['p3']}</b> 位。</p>
<p>求：ζ(3) 小数点后第 <b>{m['p3']}~{m['p3'] + 3}</b> 位，那就是碎片 3。</p>
<p style="color:#6b7683">（WolframAlpha、sympy、各种在线计算器都行）</p>
</div>
"""
    if stage == 4:
        return f"""
<div class="box">
<p>苏桁的收藏里有一张他手绘的 ζ 函数草图：<a href="/static/zeta.png">ζ 草图.png</a>。</p>
<p>它比看上去的要多一点东西——里面有 8 个编号的信息块（t1~t8）。</p>
<p>用<b>文本编辑器</b>（记事本也行）打开它，找到编号 <b>t{m['p4']}</b> 的块，那就是碎片 4。</p>
<p style="color:#6b7683">提示：图片信息里通常有些"看不见"的文字块。</p>
</div>
"""
    if stage == 5:
        return """
<div class="box">
<p>苏桁的 AI「汐月」还活着。苏桁把最重要的一串字符锁进了汐月的记忆库里——但记忆库的钥匙分成了两半。</p>
<p>要打开它，你需要一个<b>记忆库开启码</b>——它在下方「专属提示码」区域。</p>
<p>拿到后<b>私聊</b>汐月：<code>/submit 0x&lt;记忆库开启码&gt;</code>，她会给你一半。</p>
<p>另一半：汐月提到过，苏桁把备份藏在一个叫<b>「保险库」</b>的页面里——路径是它的英文名。</p>
<p style="color:#6b7683">只有完成了前 4 关的人，汐月才会说。（没绑定的话先去 <a href="/join">/join</a>）</p>
</div>
"""
    if stage == 6:
        return f"""
<div class="box">
<p>苏桁在一本书的扉页抄了一句话，关于 π：</p>
<pre>「在 π 的小数展开里，第一次连续出现 6 个 9 的地方，
  被叫作费曼点——费曼说，他想背到那里，然后向朋友炫耀：
  '九九九九九九，如此下去，直到最后。'」</pre>
<p>他在页脚又补了一句：<b>「每个人的 π，都不一样。」</b></p>
<p>你的片段，从 π 的小数点后第 <b>{m['p6']}</b> 位开始，取 4 位，就是碎片 6。</p>
<p style="color:#6b7683">（网上有 π 数字检索工具，直接查第 {m['p6']} 位起的内容）</p>
</div>
"""
    return """
<div class="box">
<p>苏桁的旧录音笔里只留下一段沙沙声：<a href="/static/beep.wav">录音.wav</a>（7 秒）。</p>
<p>有人说那是他最后的密码。用耳朵听，或者用 Audacity 看波形。</p>
<p style="color:#6b7683">（滴、滴——像是有人在敲电报。）</p>
</div>
""" + f"""
<div class="box">
<p>摩斯电码解出的四位数是共享的：0888。</p>
<p>但苏桁给每个人都加了一把偏移锁——你的偏移量是 <b>{m['o7']}</b>。</p>
<p>把 0888 的<b>每一位</b>数字都加上 {m['o7']}（超过 9 就减 10），得到的就是碎片 7。</p>
</div>
"""


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
            frags, meta = gen_frags()
            STATE["players"][code] = {
                "created": int(time.time()),
                "qq": None,
                "name": None,
                "stages": {},
                "stage_ts": {},
                "hint_gen": {},
                "hint_req": {},
                "unlocks": {},
                "hintcodes": {},
                "frags": frags,
                "frag_meta": meta,
                "final": False,
                "final_ts": None,
                "fake": False,
                "fake_ts": None,
                "egg": False,
                "egg_ts": None,
                "last": int(time.time()),
            }
            save_state()
            return code


def gen_frags():
    """每人一套固定碎片（加入时生成，永不改变）：f1/f2/f5/f8 随机 hex，
    f3 取 ζ(3) 个人位置、f6 取 π 个人位置、f4 取 PNG 个人块号、f7 摩斯基数+个人偏移。
    另生成第 5 关保险库便签：6 字符串，第 a/b 位是碎片 5 的后两位，其余为干扰。"""
    f1, f2, f5, f8 = (secrets.token_hex(2) for _ in range(4))
    p3 = secrets.randbelow(20) + 1
    f3 = ZETA3_DIGITS[p3 - 1: p3 + 3]
    p6 = secrets.randbelow(120) + 1
    f6 = PI_DIGITS[p6 - 1: p6 + 3]
    p4 = secrets.randbelow(8) + 1
    f4 = PNG_CODES[p4 - 1]
    o7 = secrets.randbelow(10)
    f7 = "".join(str((int(c) + o7) % 10) for c in MORSE_BASE)
    va = secrets.randbelow(5) + 1
    vb = secrets.randbelow(5 - va) + va + 1
    pool = [f5[2], f5[3]] + [secrets.choice("0123456789abcdef") for _ in range(4)]
    v5 = list(pool[:4])
    v5.insert(va - 1, f5[2])
    v5.insert(vb - 1, f5[3])
    return [f1, f2, f3, f4, f5, f6, f7, f8], {
        "p3": p3, "p6": p6, "p4": p4, "o7": o7,
        "v5": "".join(v5), "v5a": va, "v5b": vb,
    }


def ensure_frags(p: dict) -> None:
    """老玩家/新玩家补发个人碎片。"""
    if not p.get("frags"):
        frags, meta = gen_frags()
        p["frags"], p["frag_meta"] = frags, meta


def player_progress(p):
    done = sorted(int(s) for s, v in p["stages"].items() if v)
    return len(done), (max(done) if done else 0)


def issue_code(p: dict, kind: str, stage: int, level: int | None) -> str:
    """签发/复用一枚提示码（每人每码唯一，无时间限制；被吊销后重新生成）。"""
    codes = p.setdefault("hintcodes", {})
    for code, e in codes.items():
        if (e["kind"], e.get("stage"), e.get("level")) == (kind, stage, level) \
                and not e.get("used") and not e.get("revoked"):
            return code
    while True:
        code = secrets.token_hex(3)[:5]
        if code not in codes:
            break
    codes[code] = {"kind": kind, "stage": stage, "level": level,
                   "gen": int(time.time()), "used": False, "revoked": False}
    return code


def code_line(p: dict, kind: str, stage: int, level: int | None, gen_url: str) -> str:
    """渲染一枚码的状态：未生成→按钮；已生成→显示；已用/已吊销→提示。"""
    for code, e in p.setdefault("hintcodes", {}).items():
        if (e["kind"], e.get("stage"), e.get("level")) == (kind, stage, level):
            if e.get("used"):
                return f"<code>/submit 0x{code}</code>（已使用）"
            if e.get("revoked"):
                return f"<span style='color:#ff6b6b'>已吊销</span> <a href='{gen_url}'>重新生成</a>"
            return f"<code>/submit 0x{code}</code>"
    return f"<a href='{gen_url}'>点击生成提示码</a>"


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
        """本关专属提示码区域：全部手动生成；第1层等5分钟、第2层等20分钟、第3层需审批。"""
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return """<div class="box"><p class="frag">专属提示码</p>
<p>领取绑定码后，这里可以手动生成你的专属提示码。</p>
<p><a href="/join">去 /join 领取绑定码</a></p></div>"""
            now = int(time.time())
            first = p.setdefault("hint_gen", {}).get(str(stage))
            if first is None:
                first = now
                p["hint_gen"][str(stage)] = now
            lines = []
            for lv in range(3):
                gen_url = f"/generate?stage={stage}&lv={lv}"
                wait = HINT_UNLOCK.get(lv)
                if wait is not None:
                    unlock_at = first + wait
                    if now >= unlock_at:
                        lines.append(f"<p>{HINT_LABELS[lv]}：{code_line(p, 'h', stage, lv, gen_url)}</p>")
                    else:
                        mins = max(1, (unlock_at - now + 59) // 60)
                        lines.append(f"<p>{HINT_LABELS[lv]}：<span style='color:#6b7683'>解锁中，还需约 {mins} 分钟</span></p>")
                else:
                    req = (p.get("hint_req") or {}).get(str(stage))
                    if req and req.get("status") == "approved":
                        lines.append(f"<p>{HINT_LABELS[lv]}：{code_line(p, 'h', stage, lv, gen_url)}（已通过审批）</p>")
                    elif req and req.get("status") == "pending":
                        lines.append(f"<p>{HINT_LABELS[lv]}：<span style='color:#ffd479'>已提交申请，等待管理员审批</span></p>")
                    elif req and req.get("status") == "rejected":
                        lines.append(f"<p>{HINT_LABELS[lv]}：<span style='color:#ff6b6b'>申请被驳回</span> <a href='/request?stage={stage}'>重新申请</a></p>")
                    else:
                        lines.append(f"<p>{HINT_LABELS[lv]}：<a href='/request?stage={stage}'>点击申请（需管理员审批）</a></p>")
            save_state()
            extra = ""
            if stage == 5:
                extra = f"<p style='color:#ffd479'>记忆库开启码：{code_line(p, 'mem', 5, None, '/generate?stage=5&kind=mem')}</p>"
                save_state()
            return f"""<div class="box"><p class="frag">专属提示码</p>
<p>提示码<b>手动生成</b>：第 1 层等 5 分钟、第 2 层等 20 分钟后可点「生成」，第 3 层申请后由管理员审批。</p>
<p>码无时间限制、用完即焚、只认本人——发到群聊会被立即吊销，需重新生成/申请。</p>
{''.join(lines)}{extra}
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

        if path == "/static/beep.wav":
            wav = STATIC_DIR / "beep.wav"
            if wav.exists():
                return self._send(wav.read_bytes(), "audio/wav")
            return self._send(b"not found", "text/plain", 404)

        if path == "/join":
            return self._handle_join(qs)

        if path == "/request":
            return self._handle_request(qs)

        if path == "/generate":
            return self._handle_generate(qs)

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

        if path == "/vault":
            return self._handle_vault(qs)

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

        if path == "/api/revoke":
            return self._handle_api_revoke(qs)

        if path == "/api/events":
            return self._handle_api_events(qs)

        if path == "/api/verify":
            return self._handle_api_verify(qs)

        if path == "/api/stats":
            return self._handle_api_stats(qs)

        self._send(b"404 Not Found", "text/plain", 404)

    def _stage_page(self, stage: int):
        player = self._cookie_player()
        body = ""
        with LOCK:
            p = STATE["players"].get(player)
            if p:
                ensure_frags(p)
                save_state()
                body = stage_body(p, stage)
        return page(f"碎片 {stage}", body + self._hint_box(stage, player), check_stage=stage)

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

    def _handle_generate(self, qs):
        """手动生成提示码。已使用的码不可再生成；被吊销的码可重新生成。"""
        player = self._cookie_player()
        kind = qs.get("kind", ["h"])[0]
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._send(page("生成", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码。</p></div>").encode())
            now = int(time.time())
            if kind == "h":
                try:
                    stage = int(qs.get("stage", ["0"])[0])
                    lv = int(qs.get("lv", ["0"])[0])
                except ValueError:
                    return self._send("参数错误", "text/plain")
                if stage not in (1, 2, 3, 4, 5, 6, 7, 8) or lv not in (0, 1, 2):
                    return self._send("参数错误", "text/plain")
                wait = HINT_UNLOCK.get(lv)
                if wait is not None:
                    first = p.setdefault("hint_gen", {}).get(str(stage))
                    if first is None:
                        first = now
                        p["hint_gen"][str(stage)] = now
                    if now - first < wait:
                        mins = max(1, (wait - (now - first) + 59) // 60)
                        body = f"""<div class="box"><p class="err">还没到时间。</p>
<p>{HINT_LABELS[lv]}还需约 {mins} 分钟解锁，过会儿再来点「生成」。</p>
<p><a href="{STAGE_PATHS[stage]}">← 返回本关</a></p></div>"""
                        return self._send(page("生成", body).encode())
                else:
                    req = (p.get("hint_req") or {}).get(str(stage))
                    if not (req and req.get("status") == "approved"):
                        body = f"""<div class="box"><p class="err">未通过审批。</p>
<p>{HINT_LABELS[lv]}需要管理员审批通过后才能生成，<a href="/request?stage={stage}">去申请</a>。</p>
<p><a href="{STAGE_PATHS[stage]}">← 返回本关</a></p></div>"""
                        return self._send(page("生成", body).encode())
                issue_code(p, "h", stage, lv)
                save_state()
                return self._redirect(STAGE_PATHS[stage])
            if kind == "mem":
                issue_code(p, "mem", 5, None)
                save_state()
                return self._redirect("/stage5")
            if kind == "egg":
                if not p.get("final"):
                    return self._send(page("生成", "<div class='box'><p class='err'>彩蛋码需要先通关终局。</p></div>").encode())
                issue_code(p, "egg", 0, None)
                save_state()
                return self._redirect("/final?key=" + FINAL_KEY)
        return self._send("参数错误", "text/plain")

    def _redirect(self, path: str):
        self.send_response(302)
        self.send_header("Location", path)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None

    def _handle_request(self, qs):
        """第 3 层提示申请（需管理员在 /admin 审批）。"""
        player = self._cookie_player()
        try:
            stage = int(qs.get("stage", ["0"])[0])
        except ValueError:
            return self._send("参数错误", "text/plain")
        if stage not in (1, 2, 3, 4, 5, 6, 7, 8):
            return self._send("没有这一关。", "text/plain")
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._send(page("申请", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码。</p></div>").encode())
            req = (p.get("hint_req") or {}).get(str(stage))
            if req and req.get("status") == "pending":
                body = f"""<div class="box"><p class="frag">申请已提交</p>
<p>第 {stage} 关的第三层提示申请正在等待管理员审批，稍后再来刷新本页。</p>
<p><a href="{STAGE_PATHS[stage]}">← 返回本关</a></p></div>"""
                return self._send(page("申请", body).encode())
            p.setdefault("hint_req", {})[str(stage)] = {"ts": int(time.time()), "status": "pending"}
            p["last"] = int(time.time())
            save_state()
        body = f"""<div class="box"><p class="frag">申请已提交</p>
<p>第 {stage} 关的第三层提示申请已发出，管理员审批通过后，刷新本关页面即可看到提示码。</p>
<p><a href="{STAGE_PATHS[stage]}">← 返回本关</a></p></div>"""
        return self._send(page("申请", body).encode())

    def _handle_check(self, qs):
        try:
            stage = int(qs.get("stage", ["0"])[0])
            ans = qs.get("ans", [""])[0].strip().lower()
        except ValueError:
            return self._send("参数错误", "text/plain")
        player = self._player_from(qs) or self._cookie_player()
        if stage not in (1, 2, 3, 4, 5, 6, 7, 8):
            return self._send("没有这一关。", "text/plain")
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._send(
                    "<span class='err'>请先到 <a href='/join'>/join</a> 领取绑定码</span>，再回来确认答案。",
                    "text/html; charset=utf-8",
                )
            ensure_frags(p)
            if ans != p["frags"][stage - 1]:
                pre = f"（需先完成第 {stage-1} 关）" if stage > 1 else "（无需前置关卡）"
                return self._send(
                    f"<span class='err'>❌ 不对哦。</span> 卡住了？用本页下方的<b>专属提示码</b>，私聊汐月兑换（一次性）。{pre}",
                    "text/html; charset=utf-8",
                )
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
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._send(
                    page("终局", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码，否则拿不到 flag 记录。</p></div>").encode()
                )
            ensure_frags(p)
            fake_key = "".join(p["frags"][:7])
            true_key = "".join(p["frags"])
            if key == true_key:
                now = int(time.time())
                p["final"] = True
                p["final_ts"] = now
                p["last"] = now
                save_state()
                note = f"<p style='color:#6b7683'>玩家 {player}{'（' + str(p['qq']) + '）' if p['qq'] else ''} 已通关。</p>"
                egg_box = f"""<div class="box"><p class="frag">隐藏结局开启码</p>
<p>{code_line(p, 'egg', 0, None, '/generate?kind=egg')}</p>
<p style="font-size:12px;color:#6b7683">生成后私聊汐月发送 <code>/submit 0x&lt;码&gt;</code>，读苏桁写给汐月的信。</p>
<p style="font-size:12px;color:#6b7683">另一个线索：这串十六进制 <code>{FLAG_INNER}</code> 是苏桁一句四个字真心话的摘要——猜出它，去 <code>/hidden</code> 认领。</p></div>"""
                body = f"""<div class="box"><h2 style="margin-top:0">✅ 对钩！</h2>
<p>访问码验证通过。苏桁留给你的话：</p>
<pre>{FLAG}</pre>
<p style="color:#6b7683">「谢谢你来接我回家。」 —— 苏桁</p>{note}</div>{egg_box}"""
                return self._send(page("真结局", body).encode())
            if key == fake_key:
                now = int(time.time())
                p["fake"] = True
                p["fake_ts"] = now
                p["last"] = now
                save_state()
                body = f"""<div class="box"><h2 style="margin-top:0">对钩……？</h2>
<p>访问码验证通过。苏桁留给你的话：</p>
<pre>{FAKE_FLAG}</pre>
<p style="color:#6b7683">「……？」 —— 苏桁</p></div>
<div class="box"><p class="err">你总觉得哪里不对。</p>
<p>七个碎片拼出的，只是一半的故事。苏桁不会把最重要的秘密放在网页上——</p>
<p>最后一块碎片，只存在于汐月的心里。私聊她，用真心或证据打动她。</p></div>"""
                return self._send(page("假结局", body).encode())
        body = f"""<div class="box"><p class="err">❌ 访问码错误。</p>
<p>提示：前七个碎片拼起来是「假结局」；真正的结局需要第八块碎片。</p>
<p>卡住了？第 8 关的专属提示码在下方（一次性）。</p></div>
<div class="box"><p class="frag">你正在寻找碎片 8。</p>
<p>网页上已经没有线索了。最后一个数字只有汐月知道——私聊她，用真心或证据打动她。</p></div>"""
        return self._send(page("碎片 8 · 真相", body + self._hint_box(8, player), check_stage=8).encode())

    def _handle_vault(self, qs):
        """第 5 关保险库：按便签规则从干扰字符里取碎片 5 的后两位。"""
        player = self._cookie_player()
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._send(page("vault", "<div class='box'><p class='err'>请先到 <a href='/join'>/join</a> 领取绑定码。</p></div>").encode())
            ensure_frags(p)
            m = p["frag_meta"]
            body = f"""<div class="box">
<p>苏桁的便签，贴在保险库的门上：</p>
<pre>{m['v5']}</pre>
<p>便签背面写着：<b>取第 {m['v5a']} 个和第 {m['v5b']} 个字符</b>。</p>
<p>把这两个字符接在汐月给你的前两位后面，就是碎片 5。</p>
<p style="font-size:12px;color:#6b7683">（每个玩家的便签都不一样——这扇门只认你。）</p>
</div>
<a href="/stage5" style="font-size:13px">← 返回第 5 关</a>"""
        return self._send(page("vault · 保险库", body).encode())

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
        flash = ""
        with LOCK:
            if qs.get("approve") or qs.get("reject"):
                target = (qs.get("approve") or qs.get("reject") or [""])[0]
                try:
                    stage = int(qs.get("stage", ["0"])[0])
                except ValueError:
                    stage = 0
                p = STATE["players"].get(target)
                if p and stage in (1, 2, 3, 4, 5, 6, 7, 8):
                    if qs.get("approve"):
                        issue_code(p, "h", stage, 2)
                        p.setdefault("hint_req", {})[str(stage)] = {
                            "ts": int(time.time()), "status": "approved", "approved_ts": int(time.time())}
                        flash = f"<div class='box'><p class='ok'>已批准 {target} 的第 {stage} 关第三层提示。</p></div>"
                    else:
                        p.setdefault("hint_req", {})[str(stage)] = {"ts": int(time.time()), "status": "rejected"}
                        flash = f"<div class='box'><p class='err'>已驳回 {target} 的第 {stage} 关申请。</p></div>"
                    save_state()
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
                    f"<td>{h['time']}</td><td class='{"done" if h.get("used") else "todo"}'>{"已用" if h.get("used") else "未用"}</td>"
                    f"<td class='{"err" if h.get("revoked") else "done"}'>{"已吊销" if h.get("revoked") else "正常"}</td></tr>"
                    for h in data["hits"]
                )
                decode_html = f"""<div class="box"><p class="ok">一次性码 {code} 匹配到：</p>
<table><tr><th>绑定码</th><th>QQ</th><th>内容</th><th>签发时间</th><th>使用</th><th>吊销</th></tr>{rows}</table></div>"""
            else:
                decode_html = f"<div class='box'><p class='err'>一次性码 {code} 无匹配。</p></div>"
        with LOCK:
            rows = sorted(STATE["players"].items(), key=lambda kv: kv[1]["last"], reverse=True)
            pending = []
            for player, p in STATE["players"].items():
                for st, r in (p.get("hint_req") or {}).items():
                    if r.get("status") == "pending":
                        pending.append((player, p, int(st), r))
        pending_html = ""
        if pending:
            prow = "".join(
                f"<tr><td>{player}</td><td>{p.get('qq') or '—'}</td><td>{p.get('name') or '—'}</td>"
                f"<td>{st}</td><td>{time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}</td>"
                f"<td><a href='/admin?pass={ADMIN_TOKEN}&approve={player}&stage={st}' style='color:#6ee7a0'>批准</a> "
                f"<a href='/admin?pass={ADMIN_TOKEN}&reject={player}&stage={st}' style='color:#ff6b6b'>驳回</a></td></tr>"
                for player, p, st, r in pending
            )
            pending_html = f"""<div class="box"><p class="frag">第三层提示审批（{len(pending)} 个待处理）</p>
<table><tr><th>绑定码</th><th>QQ</th><th>昵称</th><th>关卡</th><th>申请时间</th><th>操作</th></tr>{prow}</table></div>"""
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
        body = f"""{flash}{pending_html}<div class="box">
<p>玩家总数：{len(rows)} ｜ 通关真结局：{sum(1 for _, p in rows if p['final'])} ｜ 到达假结局：{sum(1 for _, p in rows if p.get('fake'))} ｜ 找到彩蛋：{sum(1 for _, p in rows if p.get('egg'))}</p>
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
        """一次性码兑付：/submit 统一走这里。码归属校验：只认本人名下生成的码。"""
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
            ensure_frags(p)
            entry = (p.get("hintcodes") or {}).get(code)
            if not entry:
                return self._json({"ok": True, "status": "bad"})
            if entry.get("used"):
                return self._json({"ok": True, "status": "used"})
            if entry.get("revoked"):
                return self._json({"ok": True, "status": "revoked"})
            now = int(time.time())
            kind, stage, level = entry["kind"], entry.get("stage"), entry.get("level")
            if kind == "h":
                wait = HINT_UNLOCK.get(level)
                if wait is not None:
                    first = (p.get("hint_gen") or {}).get(str(stage), 0)
                    if now - first < wait:
                        return self._json({"ok": True, "status": "notyet",
                                           "wait": wait - (now - first)})
                else:
                    req = (p.get("hint_req") or {}).get(str(stage))
                    if not (req and req.get("status") == "approved"):
                        return self._json({"ok": True, "status": "notyet", "wait": 0})
                _, mx = player_progress(p)
                if stage - 1 > mx:
                    return self._json({"ok": True, "status": "gated", "need": stage - 1})
                text = render_hint(p, stage, level)
                label = f"第{stage}关·{HINT_LABELS[level]}"
            else:
                need = SECRET_GATES.get(kind)
                if need is not None:
                    _, mx = player_progress(p)
                    if mx < need:
                        return self._json({"ok": True, "status": "gated", "need": need})
                text = secret_text(kind, p)
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
            ensure_frags(p)
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
                "fake": p.get("fake", False),
                "egg": p.get("egg", False),
                "used": used,
                "frags": p["frags"],
            })

    def _handle_api_verify(self, qs):
        """LLM 工具用：核对某玩家声称收集到的碎片（前七关）正确数量。"""
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        player = self._player_from(qs)
        keys = [k.strip().lower() for k in qs.get("keys", [""])[0].split(",") if k.strip()]
        with LOCK:
            p = STATE["players"].get(player)
            if not p:
                return self._json({"ok": False, "err": "player not found"})
            ensure_frags(p)
            match = sum(1 for k in keys if k in p["frags"][:7])
            return self._json({"ok": True, "match": match, "total": 7})

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
                        "used": bool(e.get("used")),
                        "revoked": bool(e.get("revoked")),
                    })
        return self._json({"ok": True, "hits": hits})

    def _handle_api_revoke(self, qs):
        """群聊泄码时由插件调用：吊销该码；若为第 3 层提示，退回待审批（需重新申请）。"""
        if qs.get("secret", [""])[0] != ADMIN_TOKEN:
            return self._json({"ok": False, "err": "bad secret"}, 403)
        code = qs.get("code", [""])[0].strip().lower()
        if code.startswith("0x"):
            code = code[2:]
        now = int(time.time())
        found = False
        with LOCK:
            for player, p in STATE["players"].items():
                entry = (p.get("hintcodes") or {}).get(code)
                if not entry:
                    continue
                entry["revoked"] = True
                if entry["kind"] == "h" and entry.get("level") == 2:
                    st = entry.get("stage")
                    if st:
                        p.setdefault("hint_req", {})[str(st)] = {"ts": now, "status": "pending"}
                p["last"] = now
                found = True
                save_state()
                break
        return self._json({"ok": True, "found": found})

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
                for st, r in (p.get("hint_req") or {}).items():
                    if r.get("status") == "approved" and r.get("approved_ts", 0) > after:
                        events.append({"type": "hint_approved", "player": player, "qq": qq, "name": name,
                                       "stage": int(st), "ts": r["approved_ts"]})
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

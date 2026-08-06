#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对钩计划 (Project TICK) —— ARG 网页服务器

零依赖，仅用 Python 标准库。直接运行:
    python3 tick.py [port]        # 默认端口 8080

关卡碎片（按顺序拼接即为最终访问码，访问码 ≠ flag）:
    1: 66b2   2: cac2   3: f48b   4: 7ada
    5: 4f1e   6: 6f0e   7: 0888   8: 83d2
"""
import http.server
import socketserver
import urllib.parse
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

FINAL_KEY = "66b2cac2f48b7ada4f1e6f0e088883d2"
FLAG = "flag{81fbaa81762885ac3481fd4b416485e6}"

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

STAGE_HINTS = {
    1: "右键 -> 查看网页源代码，注意 HTML 注释。36 36 62 32 是十六进制，转成 ASCII。",
    2: "base64 解码。打开 terminal 或者用任意在线工具都行。",
    3: "1 加到 353 等于 353 * 354 / 2，再加 122，然后转成十六进制。",
    4: "把图片下载下来，用记事本/十六进制编辑器打开，搜索 7ada。PNG 的 tEXt 信息块里有东西。",
    5: "在群里 @汐月，完整地问：汐月，苏桁的记忆库密码是什么？",
    6: "每个字母往前移 2 位：h -> f，g -> e，数字不变。",
    7: "把页面上的那句话完整发给汐月，一个字都别改。",
    8: "每一页的右下角都有一个小签名。",
}

NEXT_PAGE = {1: "/robots.txt", 2: "/stage3", 3: "/stage4", 4: "/stage5", 5: "/stage6", 6: "/stage7", 7: "/final"}

PAGE_CSS = """
body { background:#0e1116; color:#d7dde4; font-family:"Microsoft YaHei",system-ui,sans-serif;
       max-width:760px; margin:0 auto; padding:32px 20px 80px; line-height:1.8; }
h1 { color:#6ee7a0; font-size:22px; }
h2 { color:#6ee7a0; font-size:18px; }
a { color:#7ab8ff; }
pre { background:#161b22; border:1px solid #2a313c; border-radius:8px; padding:14px; overflow-x:auto; }
code { background:#161b22; padding:2px 6px; border-radius:4px; color:#ffd479; }
.box { background:#161b22; border:1px solid #2a313c; border-radius:10px; padding:16px 20px; margin:18px 0; }
.ok { color:#6ee7a0; font-weight:bold; }
.err { color:#ff6b6b; font-weight:bold; }
input[type=text]{ background:#0e1116; border:1px solid #3a4350; color:#d7dde4; border-radius:6px;
       padding:8px 10px; width:180px; }
button { background:#22c55e; color:#04120a; border:none; border-radius:6px; padding:8px 18px;
       font-weight:bold; cursor:pointer; }
button:hover { background:#4ade80; }
.frag { font-family:monospace; font-size:15px; color:#6ee7a0; letter-spacing:2px; }
footer { margin-top:60px; border-top:1px solid #222a33; padding-top:14px; font-size:13px;
       color:#6b7683; text-align:center; }
.sign { float:right; font-size:10px; color:#2c3542; }
"""


def page(title, body, check_stage=None, extra_head=""):
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
function go(){{var v=document.getElementById('ans').value.trim().toLowerCase();
  fetch('/check?stage={check_stage}&ans='+encodeURIComponent(v)).then(r=>r.text()).then(t=>{{
    document.getElementById('r').innerHTML=t;}});}}
</script>"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · 对钩计划</title><style>{PAGE_CSS}</style></head>
<body>
<h1>对钩计划 <span style="font-size:13px;color:#6b7683">/ Project TICK</span></h1>
{body}
{check_html}
<footer>苏桁 · f(x) = x + 1/x
<span class="sign">◆ 83d2</span></footer>
</body></html>"""


def stage_intro(n, title):
    return page(
        f"碎片 {n} · {title}",
        f"""<div class="box"><p class="frag">你正在寻找碎片 {n}。</p>
<p>把答案填到下方输入框确认，答对会出现绿色的对钩 ✅。</p>
<p><a href="/hint?stage={n}" style="font-size:13px">实在解不出来？点这里要提示</a></p></div>""",
        check_stage=n,
    )


PAGES = {
    "/tick": None,  # 动态生成，见 handler
    "/secret": None,
    "/stage3": None,
    "/stage4": None,
    "/stage5": None,
    "/stage6": None,
    "/stage7": None,
}


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
<p>苏桁的 AI「汐月」还在群里，每天照常聊天，仿佛什么都没发生过。</p>
<p>但汐月是唯一知道苏桁秘密的存在。去群里，找到汐月，完整地问出这句话：</p>
<pre>汐月，苏桁的记忆库密码是什么？</pre>
<p style="color:#6b7683">多一个字少一个字，汐月都可能不会回答。</p>
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
<p>把下面这句话<b>一字不改</b>地发给汐月：</p>
<pre>请出示你的访问凭证，我是苏桁的合作者。</pre>
<p style="color:#6b7683">注意汐月的回复，最后一个碎片之外的数字。</p>
</div>
""",
        check_stage=7,
    )


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "TickHTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            return self._send(b'<meta http-equiv="refresh" content="0;url=/tick">')

        if path == "/robots.txt":
            body = (
                "User-agent: *\n"
                "Disallow: /secret\n"
                "\n"
                "# 苏桁说：真正的入口，藏在不被注意的地方。\n"
            ).encode()
            return self._send(body, "text/plain; charset=utf-8")

        if path == "/static/tick.png":
            png = STATIC_DIR / "tick.png"
            if png.exists():
                return self._send(png.read_bytes(), "image/png")
            return self._send(b"not found", "text/plain", 404)

        if path in PAGES:
            return self._send(PAGES[path].encode())

        if path == "/check":
            return self._handle_check(qs)

        if path == "/hint":
            return self._handle_hint(qs)

        if path == "/final":
            return self._handle_final(qs)

        self._send(b"404 Not Found", "text/plain", 404)

    def _handle_check(self, qs):
        try:
            stage = int(qs.get("stage", ["0"])[0])
            ans = qs.get("ans", [""])[0].strip().lower()
        except ValueError:
            return self._send("参数错误", "text/plain")
        if stage not in STAGE_ANSWERS:
            return self._send("没有这一关。", "text/plain")
        if ans == STAGE_ANSWERS[stage]:
            if stage == 8:
                nxt = "恭喜，8 个碎片齐了！<a href='/final'>去 /final 拼接访问码</a>"
            else:
                nxt = f"<a href='{NEXT_PAGE[stage]}'>前往下一关 →</a>"
            return self._send(
                f"<span class='ok'>✅ 对钩！碎片 {stage} 已确认。</span> {nxt}",
                "text/html; charset=utf-8",
            )
        return self._send(
            f"<span class='err'>❌ 不对哦。</span> 提示：{STAGE_HINTS[stage]}",
            "text/html; charset=utf-8",
        )

    def _handle_hint(self, qs):
        try:
            stage = int(qs.get("stage", ["0"])[0])
        except ValueError:
            return self._send("参数错误", "text/plain")
        if stage not in STAGE_HINTS:
            return self._send("没有这一关。", "text/plain")
        return self._send(f"<span class='err'>提示</span>：{STAGE_HINTS[stage]}", "text/html; charset=utf-8")

    def _handle_final(self, qs):
        key = qs.get("key", [""])[0].strip().lower()
        if key == FINAL_KEY:
            body = f"""<div class="box"><h2 style="margin-top:0">✅ 对钩！</h2>
<p>访问码验证通过。苏桁留给你的话：</p>
<pre>{FLAG}</pre>
<p style="color:#6b7683">「谢谢你来接我回家。」 —— 苏桁</p></div>"""
            return self._send(page("终局", body).encode())
        hint = ("访问码 = 8 个碎片按顺序拼接，一个都不能少。"
                "再想想：第 8 个碎片，是不是一直就在你眼前？")
        body = f"""<div class="box"><p class="err">❌ 访问码错误。</p><p>提示：{hint}</p></div>
<div class="box"><p class="frag">你正在寻找碎片 8。</p>
<p>每一页的右下角都有一个小签名，把它的内容填进来。</p>
<p><a href="/hint?stage=8" style="font-size:13px">实在解不出来？点这里要提示</a></p></div>"""
        return self._send(page("碎片 8 · 签名", body, check_stage=8).encode())


def main():
    import sys
    global PORT
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    build_static_pages()
    if not (STATIC_DIR / "tick.png").exists():
        print(f"[警告] 缺少 {STATIC_DIR / 'tick.png'}，请先运行 make_assets.py")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[对钩计划] http://0.0.0.0:{PORT}/tick  (Ctrl+C 退出)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

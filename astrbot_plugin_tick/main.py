"""对钩计划（Project TICK）—— AstrBot 剧情插件（汐月）"""

import urllib.parse

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.star import Star

HINTS = {
    1: "右键查看 /tick 页面的网页源代码，注意 HTML 注释：36 36 62 32，是十六进制，转成 ASCII。",
    2: "看 /robots.txt，找到 /secret，那里有一串 base64，解码就是碎片 2。",
    3: "1 加到 353 等于 353*354/2，再加 122，然后转成十六进制（去掉 0x 前缀）。",
    4: "下载「对钩函数.png」，用文本编辑器打开，搜索 7ada。PNG 的 tEXt 信息块里有东西。",
    5: "这是汐月自己的秘密，私聊发送 /记忆库（需要先完成前 4 关）。",
    6: "每个字母往前移 2 位：h→f，g→e，数字不变。",
    7: "口令在汐月这里，私聊发送 /凭证（需要先完成前 6 关）。",
    8: "每一页的右下角都有一个小签名，把它的内容填进 /final 页。",
}

GATE = {5: 4, 7: 6}  # /记忆库 需要完成第 4 关，/凭证 需要完成第 6 关


class Main(Star):
    """对钩计划：汐月与苏桁的记忆。

    私聊指令：/tick /hint N /记忆库 /凭证 /进度
    群内指令：/bind <绑定码>（绑定 QQ 身份）
    """

    def __init__(self, context, config=None):
        super().__init__(context)
        self.config = config or {}

    # ---------- 与网页服务器通信 ----------

    async def _api(self, path: str, params: dict):
        base = str(self.config.get("web_base", "http://127.0.0.1:8080")).rstrip("/")
        token = str(self.config.get("admin_token", "tick-admin-9c4f2b7a1d"))
        params = dict(params)
        params["secret"] = token
        url = base + path + "?" + urllib.parse.urlencode(params)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[tick] API 请求失败: {e}")
            return None

    async def _bound_code(self, event: AstrMessageEvent) -> str | None:
        qq = event.get_sender_id()
        return await self.get_kv_data(f"tick_qq_{qq}", None)

    async def _progress(self, code: str):
        ret = await self._api("/api/progress", {"player": code})
        if ret and ret.get("ok"):
            return ret
        return None

    # ---------- 私聊指令 ----------

    @filter.command("tick")
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def tick_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "汐月：你想知道苏桁的事？先按顺序来：\n"
            "1. 在群里 @我，发送 /bind <绑定码>（绑定码去网页 /join 领取）；\n"
            "2. 从网页 /tick 开始解谜；\n"
            "3. 卡关的时候私聊我 /hint N 要提示，但要先通关前一关；\n"
            "4. /进度 可以查看自己的通关进度。\n"
            "苏桁说，任何秘密都只能一对一地说。"
        )

    @filter.command("hint", alias={"提示"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def hint_cmd(self, event: AstrMessageEvent, stage: int):
        if stage < 1 or stage > 8:
            yield event.plain_result("关卡号是 1 到 8。")
            return
        code = await self._bound_code(event)
        if not code:
            yield event.plain_result("你还没绑定玩家身份。先去网页 /join 领取绑定码，再到群里 @我发送 /bind <绑定码>。")
            return
        prog = await self._progress(code)
        if not prog:
            yield event.plain_result("进度查询失败，稍后再试试。")
            return
        mx = prog.get("max", 0)
        if stage - 1 > mx:
            yield event.plain_result(f"不行哦，你还没通关第 {stage-1} 关（当前最高第 {mx} 关），不能要第 {stage} 关的提示。")
            return
        yield event.plain_result(f"第 {stage} 关的提示：{HINTS[stage]}")

    @filter.command("记忆库", alias={"frag5"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def memory_cmd(self, event: AstrMessageEvent):
        code = await self._bound_code(event)
        if not code:
            yield event.plain_result("你还没绑定玩家身份。先去网页 /join 领取绑定码，再到群里 @我发送 /bind <绑定码>。")
            return
        prog = await self._progress(code)
        if not prog:
            yield event.plain_result("进度查询失败，稍后再试试。")
            return
        if prog.get("max", 0) < GATE[5]:
            yield event.plain_result("记忆库……上锁了。苏桁说过，只有解开他前 4 道题的人，才能打开它。")
            return
        yield event.plain_result(
            "记忆库……（信号很不稳定）我只记得四个字符：4、F、1、E。"
            "对，4f1e。别问我为什么记得这个，苏桁说那是打开他记忆库的钥匙。"
        )

    @filter.command("凭证", alias={"frag7"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def credential_cmd(self, event: AstrMessageEvent):
        code = await self._bound_code(event)
        if not code:
            yield event.plain_result("你还没绑定玩家身份。先去网页 /join 领取绑定码，再到群里 @我发送 /bind <绑定码>。")
            return
        prog = await self._progress(code)
        if not prog:
            yield event.plain_result("进度查询失败，稍后再试试。")
            return
        if prog.get("max", 0) < GATE[7]:
            yield event.plain_result("口令……只有解开前 6 道题的人，才有资格知道。")
            return
        yield event.plain_result("……凭证核对中。校验通过。碎片七：0888。拿去吧，别说是我给的。")

    @filter.command("进度", alias={"progress"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def progress_cmd(self, event: AstrMessageEvent):
        code = await self._bound_code(event)
        if not code:
            yield event.plain_result("你还没绑定玩家身份。先去网页 /join 领取绑定码，再到群里 @我发送 /bind <绑定码>。")
            return
        prog = await self._progress(code)
        if not prog:
            yield event.plain_result("进度查询失败，稍后再试试。")
            return
        done = sorted(prog.get("stages", []))
        line = " ".join(f"✓{s}" for s in done) if done else "还没有通关记录"
        yield event.plain_result(f"你的进度：{prog.get('count', 0)}/8 关 ｜ {line}{' ｜ 终局 ✓' if prog.get('final') else ''}")

    # ---------- 群内指令：绑定 ----------

    @filter.command("bind", alias={"绑定"})
    async def bind_cmd(self, event: AstrMessageEvent, code: str):
        code = code.strip().lower()
        qq = str(event.get_sender_id())
        name = event.get_sender_name() or ""
        ret = await self._api("/api/bind", {"player": code, "qq": qq, "name": name})
        if ret and ret.get("ok"):
            await self.put_kv_data(f"tick_qq_{qq}", code)
            yield event.plain_result(f"绑定成功！{name}（{qq}）→ 绑定码 {code}。私聊我发送 /tick 开始。")
        else:
            yield event.plain_result("绑定失败：这个绑定码不存在。先去网页 /join 领取绑定码，再回来绑定。")

    # ---------- 群内剧情对话（不含任何答案） ----------

    @filter.regex(r"苏桁|对钩")
    async def lore(self, event: AstrMessageEvent):
        yield event.plain_result(
            "（沉默了一会儿）苏桁……他已经很久没回来了。"
            "他研究一个叫对钩函数的东西，f(x)=x+1/x，说是世界上最诚实又最矛盾的函数。"
            "他临走前说，如果有一天他不在了，就让大家去他的网站上看看。"
            "细节……有些事只能一对一地说，你私聊我，发送 /tick。"
        )

    @filter.regex(r"网站|网址|入口")
    async def site(self, event: AstrMessageEvent):
        yield event.plain_result(
            "他的网站入口？我只记得一个词：tick。顺着那个词找吧。"
            "拿到绑定码之后记得私聊我，发送 /tick。"
        )

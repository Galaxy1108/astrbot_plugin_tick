"""ζ 计划（Project ZETA）—— AstrBot 剧情插件（汐月）

一次性码兑付机制：每关页面按玩家签发专属提示码（每人每码唯一，10 分钟有效，用完即焚）。
私聊指令全部以码为凭证，由网页 /api/redeem 统一兑付：
    /hint 0x<码>     兑换本关 3 层提示之一（需通关前一关）
    /记忆库 0x<码>    第 5 关（需完成前 4 关）
    /凭证 0x<码>      第 7 关（需完成前 6 关）
    /彩蛋 0x<码>      隐藏结局（终局页签发）
群内（包括 @）发送这些指令一律无效、不消耗码；群内只保留剧情与 /bind。
玩家通关后，插件向指定群聊推送通关播报。
"""

import asyncio
import urllib.parse

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Plain
from astrbot.api.star import Star

POLL_INTERVAL = 30  # 秒


class Main(Star):
    """ζ 计划：汐月与苏桁的记忆。

    私聊指令：/zeta /hint 0x码 /记忆库 0x码 /凭证 0x码 /彩蛋 0x码 /进度
    群内指令：/bind <绑定码>
    """

    def __init__(self, context, config=None):
        super().__init__(context)
        self.config = config or {}
        self._poll_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def terminate(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None

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

    async def _call(self, event: AstrMessageEvent, path: str, params: dict):
        """带上玩家身份调用网页 API；返回 (ret, err_msg)。"""
        code = await self._bound_code(event)
        if not code:
            return None, "你还没绑定玩家身份。先去网页 /join 领取绑定码，再到群里 @我发送 /bind <绑定码>。"
        params["player"] = code
        ret = await self._api(path, params)
        if ret is None:
            return None, "汐月的信号不稳定，稍后再试试。"
        return ret, None

    @staticmethod
    def _norm(code: str) -> str:
        code = code.strip().lower()
        return code[2:] if code.startswith("0x") else code

    # ---------- 私聊指令（一次性码兑付） ----------

    @filter.command("zeta", alias={"tick"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def zeta_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "汐月：你想知道苏桁的事？先按顺序来：\n"
            "1. 在群里 @我，发送 /bind <绑定码>（绑定码去网页 /join 领取）；\n"
            "2. 从网页 /zeta 开始解谜；\n"
            "3. 每关页面的「专属提示码」区有 3 层提示码，私聊我 /hint 0x<码> 兑换"
            "（每人每码只能用一次，10 分钟有效）；\n"
            "4. 第 5 关用 /记忆库 0x<码>，第 7 关用 /凭证 0x<码>，通关后的 /彩蛋 0x<码> 是另一个故事；\n"
            "5. /进度 查看自己的通关进度。\n"
            "苏桁说，秘密只能一对一地说，说了就没了。"
        )

    async def _redeem(self, event: AstrMessageEvent, code: str, what: str):
        if not event.is_private_chat():
            yield event.plain_result(f"{what}的事，只能在私聊里说。")
            return
        ret, err = await self._call(event, "/api/redeem", {"code": self._norm(code)})
        if err:
            yield event.plain_result(err)
            return
        status = ret.get("status")
        if status == "ok":
            tail = f"（{ret['label']}，已使用）" if ret.get("label") else ""
            yield event.plain_result(ret["text"] + "\n" + tail if tail else ret["text"])
        elif status == "gated":
            yield event.plain_result(f"不行哦，你还没通关第 {ret['need']} 关，这个码还不能用。")
        elif status == "expired":
            yield event.plain_result("这个码过期了。回到网页上对应关卡，刷新页面重新领取。")
        elif status == "used":
            yield event.plain_result("这个码已经用过了（一次性），它不会再出现了。")
        else:
            yield event.plain_result("这不是有效的码。检查一下有没有抄错，或者回网页重新领取。")

    @filter.command("hint", alias={"提示"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def hint_cmd(self, event: AstrMessageEvent, code: str):
        async for r in self._redeem(event, code, "提示"):
            yield r

    @filter.command("记忆库", alias={"frag5"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def memory_cmd(self, event: AstrMessageEvent, code: str):
        async for r in self._redeem(event, code, "记忆库"):
            yield r

    @filter.command("凭证", alias={"frag7"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def credential_cmd(self, event: AstrMessageEvent, code: str):
        async for r in self._redeem(event, code, "凭证"):
            yield r

    @filter.command("彩蛋", alias={"hidden"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def egg_cmd(self, event: AstrMessageEvent, code: str):
        async for r in self._redeem(event, code, "彩蛋"):
            yield r

    @filter.command("进度", alias={"progress"})
    @filter.event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def progress_cmd(self, event: AstrMessageEvent):
        if not event.is_private_chat():
            yield event.plain_result("你的进度，私聊里才能看。")
            return
        ret, err = await self._call(event, "/api/progress", {})
        if err:
            yield event.plain_result(err)
            return
        done = sorted(ret.get("stages", []))
        line = " ".join(f"✓{s}" for s in done) if done else "还没有通关记录"
        used = ret.get("used", [])
        used_line = (" ｜ 已用：" + "、".join(used)) if used else ""
        egg = " ｜ 彩蛋 ✓" if ret.get("egg") else ""
        yield event.plain_result(
            f"你的进度：{ret.get('count', 0)}/8 关 ｜ {line}{used_line}{' ｜ 终局 ✓' if ret.get('final') else ''}{egg}"
        )

    # ---------- 群内指令：绑定 ----------

    @filter.command("bind", alias={"绑定"})
    async def bind_cmd(self, event: AstrMessageEvent, code: str):
        self._remember_group(event)
        code = code.strip().lower()
        qq = str(event.get_sender_id())
        name = event.get_sender_name() or ""
        ret = await self._api("/api/bind", {"player": code, "qq": qq, "name": name})
        if ret and ret.get("ok"):
            await self.put_kv_data(f"tick_qq_{qq}", code)
            yield event.plain_result(f"绑定成功！{name}（{qq}）→ 绑定码 {code}。私聊我发送 /zeta 开始。")
        else:
            yield event.plain_result("绑定失败：这个绑定码不存在。先去网页 /join 领取绑定码，再回来绑定。")

    # ---------- 群内拦截：敏感指令在群里一律无效（不消耗任何码） ----------

    @filter.regex(r"^(记忆库|凭证|彩蛋|hint|提示|进度|zeta|tick)\b")
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def group_block(self, event: AstrMessageEvent):
        self._remember_group(event)
        yield event.plain_result(
            "这些指令只能在私聊里使用，在群里说了是无效的（也不会消耗你的码）。"
            "想聊剧情的话，随时可以 @我。"
        )

    # ---------- 群内剧情对话（不含任何答案/提示） ----------

    @filter.regex(r"苏桁|ζ|黎曼")
    async def lore(self, event: AstrMessageEvent):
        self._remember_group(event)
        yield event.plain_result(
            "（沉默了一会儿）苏桁……他已经很久没回来了。"
            "他研究黎曼 ζ 函数——那个连 1+2+3+… 都等于 -1/12 的世界。"
            "他临走前说，如果有一天他不在了，就让大家去他的网站上看看。"
            "细节……有些事只能一对一地说，你私聊我，发送 /zeta。"
        )

    @filter.regex(r"网站|网址|入口")
    async def site(self, event: AstrMessageEvent):
        self._remember_group(event)
        yield event.plain_result(
            "他的网站入口？我只记得一个词：zeta。顺着那个词找吧。"
            "拿到绑定码之后记得私聊我，发送 /zeta。"
        )

    # ---------- 通关播报（轮询网页 /api/finished） ----------

    def _remember_group(self, event: AstrMessageEvent) -> None:
        """记住指定群的会话标识（umo），供通关播报使用。"""
        if event.is_private_chat():
            return
        ng = str(self.config.get("notify_group", "") or "")
        if ng and str(event.get_group_id() or "") != ng:
            return
        self._group_umo = event.unified_msg_origin

    async def _notify_finished(self) -> None:
        umo = getattr(self, "_group_umo", None)
        if not umo:
            return
        last = await self.get_kv_data("tick_notify_last", 0)
        ret = await self._api("/api/finished", {"after": last})
        if not ret or not ret.get("ok"):
            return
        new_last = last
        for e in ret.get("finished", []):
            ts = e.get("final_ts", 0)
            if ts <= last:
                continue
            new_last = max(new_last, ts)
            dur = max(1, ts - (e.get("created") or ts))
            qq = e.get("qq") or e.get("player")
            name = e.get("name") or qq
            egg = "已找到彩蛋" if e.get("egg") else "彩蛋未找到"
            minutes = dur // 60
            hours = minutes // 60
            dur_text = f"{hours} 小时 {minutes % 60} 分" if hours else f"{minutes} 分钟"
            text = (
                f"通关播报：{name}（{qq}）完成了「ζ 计划」全部 8 关！\n"
                f"耗时：{dur_text} ｜ {egg}"
            )
            try:
                await self.context.send_message(umo, MessageChain(chain=[Plain(text)]))
            except Exception as e:
                logger.error(f"[tick] 通关播报发送失败: {e}")
        await self.put_kv_data("tick_notify_last", new_last)

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._notify_finished()
            except Exception as e:
                logger.error(f"[tick] 轮询失败: {e}")
            await asyncio.sleep(POLL_INTERVAL)

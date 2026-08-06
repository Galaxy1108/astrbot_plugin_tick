from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Star


class Main(Star):
    """对钩计划（Project TICK）剧情插件：汐月与苏桁的记忆。

    在群里问汐月关于「苏桁」「记忆库」的话题，会触发剧情回复。
    关键词必须完整匹配，多字少字都不会触发。
    """

    @filter.regex(r"记忆库.{0,6}密码|苏桁.{0,8}记忆库|记忆库.{0,8}苏桁")
    async def memory_code(self, event: AstrMessageEvent):
        yield event.plain_result(
            "记忆库……（信号很不稳定）我只记得四个字符：4、F、1、E。"
            "对，4f1e。别问我为什么记得这个，苏桁说那是打开他记忆库的钥匙。"
        )

    @filter.regex(r"请出示你的访问凭证")
    async def credential(self, event: AstrMessageEvent):
        yield event.plain_result(
            "……凭证核对中。校验通过。碎片七：0888。拿去吧，别说是我给的。"
        )

    @filter.regex(r"苏桁|对钩")
    async def lore(self, event: AstrMessageEvent):
        yield event.plain_result(
            "（沉默了一会儿）苏桁……他已经很久没回来了。"
            "他研究一个叫对钩函数的东西，f(x)=x+1/x，说是世界上最诚实又最矛盾的函数。"
            "他临走前说，如果有一天他不在了，就让大家去他的网站上看看。"
            "我记不全网址，只知道好像和 tick 有关。"
        )

    @filter.regex(r"网站|网址|入口")
    async def site(self, event: AstrMessageEvent):
        yield event.plain_result(
            "他的网站入口？我只记得一个词：tick。顺着那个词找吧。"
            "服务器不就在眼前吗。"
        )

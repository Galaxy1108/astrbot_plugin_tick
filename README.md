# 对钩计划 (Project TICK) — ARG

一个给 OI 选手 / 新手准备的解谜 ARG。目标：收集 8 个十六进制碎片，拼出访问码，换取

```
flag{81fbaa81762885ac3481fd4b416485e6}
```

**背景**：数学系学生苏桁研究对钩函数 f(x)=x+1/x 后失踪。他的 AI「汐月」还在群里照常聊天。玩家通过他的服务器和他留下的谜题，拼出访问码。

## 组成

| 路径 | 说明 |
|------|------|
| `astrbot_plugin_tick/` | AstrBot 插件（汐月的剧情回复，可从 GitHub 安装） |
| `server/tick.py` | ARG 网页服务器（零依赖，Python 标准库） |
| `server/make_assets.py` | PNG tEXt 隐写注入脚本 |
| `server/static/tick.png` | 已注入碎片 `85ac` 的对钩函数图 |

## 关卡一览（答案 = 碎片）

| 关 | 答案 | 玩法 | 载体 |
|----|------|------|------|
| 1 | `81fb` | 查看首页源码，`38 31 66 62` hex→ASCII | `/tick` 注释 |
| 2 | `aa81` | `robots.txt` → `/secret` → base64 `YWE4MQ==` | `/robots.txt` `/secret` |
| 3 | `7628` | 求和 1..123 再加 2 | `/stage3` |
| 4 | `85ac` | 下载 PNG，文本/十六进制编辑器搜 `85ac`（tEXt 块） | `/static/tick.png` |
| 5 | `3481` | 群里问汐月「记忆库密码」 | 汐月 |
| 6 | `fd4b` | 凯撒前移 2：`hf4d` | `/stage6` |
| 7 | `4164` | 把凭证口令发给汐月 | 汐月 |
| 8 | `85e6` | 每页右下角小签名 | 所有页面 |

**访问码**：`81fbaa81762885ac3481fd4b416485e6` → 访问 `/final?key=<访问码>` 得到 flag。

每关页面带答案输入框（`/check` 校验，答对亮对钩 ✅）、`/hint` 提示接口。

## 插件安装（AstrBot 管理面板）

插件市场 → 手动安装 → GitHub 仓库地址：

```
https://github.com/Galaxy1108/astrbot_plugin_tick
```

或直接把 `astrbot_plugin_tick/` 整个目录复制到 AstrBot 数据目录 `data/plugins/` 下，然后在管理面板重载插件。

触发词（完整匹配，多字少字都不触发）：

| 说 | 汐月回 |
|----|--------|
| 汐月，苏桁的记忆库密码是什么？ | ……3481 |
| 请出示你的访问凭证，我是苏桁的合作者。 | 碎片七：4164 |
| 提到「苏桁」/「对钩」 | 剧情背景 + 网站线索 |
| 提到「网站」/「网址」/「入口」 | 指向 tick |

## 服务器部署（tick.py）

```powershell
# 拷贝 server/ 目录到服务器（如 C:\tick-arg\），然后：
cd C:\tick-arg
Start-Process -FilePath "C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -ArgumentList "tick.py","8080" -WindowStyle Hidden
```

或使用 pm2：`pm2 start tick.py --interpreter python -- 8080`。

**防火墙**：
- Windows 防火墙：`netsh advfirewall firewall add rule name="tick-arg" dir=in action=allow protocol=TCP localport=8080`
- **阿里云安全组：入方向开放 TCP 8080**（这是第二层防火墙，必须在 ECS 控制台操作）

访问入口：`http://<公网IP>:8080/tick`

## 验证

```bash
# 每关答案
for a in 81fb aa81 7628 85ac 3481 fd4b 4164 85e6; do
  curl -s "http://localhost:8080/check?stage=N&ans=$a"
done
# 终局
curl "http://localhost:8080/final?key=81fbaa81762885ac3481fd4b416485e6"
```

## 再生成素材

```bash
python3 make_assets.py <输入png> <输出png> <碎片>
```
